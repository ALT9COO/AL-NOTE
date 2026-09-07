"""멀티 프로바이더 AI 엔진 — OpenAI · Anthropic Claude · Google Gemini.

활성 프로바이더는 설정 화면(api_settings 테이블)에서 지정하며, 모든 호출은
api_usage 테이블에 토큰·비용·지연시간으로 기록되어 실시간 사용량 화면에 노출된다.
"""

from __future__ import annotations

import base64
import difflib
import io
import json
import logging
import mimetypes
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger("ainote")

from config import (
    AI_PROVIDERS,
    STATUS_DEFAULT_PROGRESS,
    STATUSES,
    WHISPER_AUDIO_BYTES,
    estimate_cost,
    settings,
)
from secret_box import reveal

REQUEST_TIMEOUT = 120.0
STT_TIMEOUT = 600.0
GEMINI_INLINE_MAX_BYTES = 15 * 1024 * 1024


class AIEngineError(RuntimeError):
    """AI 호출 실패 (라우터에서 502 로 변환)."""


@dataclass
class ProviderConfig:
    provider: str
    label: str
    api_key: str
    model: str
    supports_stt: bool

    @property
    def ready(self) -> bool:
        return bool(self.api_key)


@dataclass
class LlmResult:
    text: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# --------------------------------------------------------------------------- #
# 프로바이더 설정 조회 · 사용량 기록
# --------------------------------------------------------------------------- #
def _setting_rows(db) -> dict[str, Any]:
    if db is None:
        return {}
    try:
        from sqlalchemy import select

        from database import ApiSetting

        return {row.provider: row for row in db.scalars(select(ApiSetting)).all()}
    except Exception:  # noqa: BLE001 — 설정 테이블 문제로 본 기능이 막히면 안 된다
        return {}


def _stored_key(row) -> str:
    return reveal(getattr(row, "api_key", None)) if row is not None else ""


def active_config(db=None) -> ProviderConfig:
    """활성 프로바이더 설정. DB 값이 없으면 .env 기본값(OpenAI)으로 폴백."""
    rows = _setting_rows(db)
    row = next((r for r in rows.values() if r.is_active and _stored_key(r)), None)
    if row is None:
        row = next((r for r in rows.values() if r.is_active), None)

    provider = row.provider if row else "openai"
    meta = AI_PROVIDERS.get(provider, AI_PROVIDERS["openai"])
    api_key = _stored_key(row) or settings.env_key(provider)
    model = (row.text_model if row else "") or meta["default_model"]

    return ProviderConfig(
        provider=provider,
        label=meta["label"],
        api_key=api_key,
        model=model,
        supports_stt=bool(meta["supports_stt"]),
    )


def stt_config(db=None) -> ProviderConfig:
    """음성 전사 엔진. OpenAI Whisper 가 있으면 그걸 쓰고, 없으면 Gemini 오디오 입력을 쓴다."""
    rows = _setting_rows(db)

    openai_row = rows.get("openai")
    openai_key = _stored_key(openai_row) or settings.openai_api_key
    if openai_key:
        return ProviderConfig(
            provider="openai",
            label="OpenAI Whisper",
            api_key=openai_key,
            model=settings.openai_stt_model,
            supports_stt=True,
        )

    google_row = rows.get("google")
    google_key = _stored_key(google_row) or settings.env_key("google")
    google_meta = AI_PROVIDERS["google"]
    google_model = (google_row.text_model if google_row else "") or google_meta["default_model"]
    return ProviderConfig(
        provider="google",
        label="Google Gemini",
        api_key=google_key,
        model=google_model,
        supports_stt=True,
    )


def record_usage(
    db,
    *,
    provider: str,
    model: str,
    feature: str,
    status: str = "success",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    error_message: str = "",
    user_id: str | None = None,
) -> None:
    """AI 호출 1건을 사용량 로그에 남긴다. 기록 실패가 본 기능을 막지 않도록 방어한다."""
    try:
        from database import ApiUsage, SessionLocal

        total = prompt_tokens + completion_tokens
        entry = ApiUsage(
            provider=provider,
            model=model,
            feature=feature,
            status=status,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=estimate_cost(model, prompt_tokens, completion_tokens)
            if status == "success"
            else 0.0,
            latency_ms=latency_ms,
            error_message=(error_message or "")[:500],
            user_id=user_id,
        )
        if db is not None:
            db.add(entry)
            db.commit()
        else:  # 라우터 밖에서 호출된 경우 독립 세션으로 기록
            with SessionLocal() as session:
                session.add(entry)
                session.commit()
    except Exception:  # noqa: BLE001
        if db is not None:
            db.rollback()


def ai_status(db=None) -> dict[str, Any]:
    cfg = active_config(db)
    stt = stt_config(db)
    return {
        "provider": cfg.provider,
        "provider_label": cfg.label,
        "llm_ready": cfg.ready,
        "stt_ready": stt.ready,
        "mock_mode": settings.allow_mock_ai and not cfg.ready,
        "text_model": cfg.model,
        "stt_model": stt.model,
    }


# --------------------------------------------------------------------------- #
# 프로바이더별 호출 구현
# --------------------------------------------------------------------------- #
def _openai_chat(cfg: ProviderConfig, system: str, user: str, json_mode: bool, temperature: float) -> LlmResult:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise AIEngineError("openai 패키지가 설치되어 있지 않습니다.") from exc

    client = OpenAI(api_key=cfg.api_key, timeout=REQUEST_TIMEOUT)
    kwargs: dict[str, Any] = {
        "model": cfg.model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    completion = client.chat.completions.create(**kwargs)
    usage = getattr(completion, "usage", None)
    return LlmResult(
        text=completion.choices[0].message.content or "",
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


def _anthropic_chat(cfg: ProviderConfig, system: str, user: str, json_mode: bool, temperature: float) -> LlmResult:
    import httpx

    prompt = user if not json_mode else f"{user}\n\n반드시 JSON 오브젝트 하나만 출력하세요."
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": cfg.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise AIEngineError(_http_error("Anthropic", response))

    data = response.json()
    text = "".join(block.get("text", "") for block in data.get("content", []))
    usage = data.get("usage", {})
    return LlmResult(
        text=text,
        prompt_tokens=int(usage.get("input_tokens", 0) or 0),
        completion_tokens=int(usage.get("output_tokens", 0) or 0),
    )


_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _gemini_busy_message(status_code: int | None) -> str | None:
    if status_code in (429, 503):
        return (
            "Gemini 서버가 일시적으로 혼잡합니다. API 키는 연결되어 있습니다. "
            "잠시 후 다시 시도해 주세요."
        )
    return None


def _gemini_generate_content(
    api_key: str,
    model: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    delays: tuple[float, ...] = (0.0, 2.0, 5.0),
):
    """Gemini generateContent. 429/503 등 일시 오류는 짧게 재시도한다."""
    import httpx

    last_response = None
    last_error: Exception | None = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            last_response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                headers={"content-type": "application/json"},
                json=payload,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            last_error = exc
            logger.warning("Gemini generateContent timeout model=%s", model)
            continue
        except httpx.RequestError as exc:
            last_error = exc
            logger.warning("Gemini generateContent network error model=%s: %s", model, exc)
            continue
        if last_response.status_code < 400:
            return last_response
        if last_response.status_code not in _RETRYABLE_STATUS:
            return last_response
        logger.warning(
            "Gemini generateContent retryable model=%s status=%s",
            model,
            last_response.status_code,
        )
    if last_response is not None:
        return last_response
    raise AIEngineError(f"Google Gemini 연결 실패: {last_error}")


def _google_chat(cfg: ProviderConfig, system: str, user: str, json_mode: bool, temperature: float) -> LlmResult:
    generation: dict[str, Any] = {"temperature": temperature}
    if json_mode:
        generation["responseMimeType"] = "application/json"

    response = _gemini_generate_content(
        cfg.api_key,
        cfg.model,
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation,
        },
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise AIEngineError(
            _gemini_busy_message(response.status_code) or _http_error("Google Gemini", response)
        )

    data = response.json()
    candidates = data.get("candidates") or []
    text = ""
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
    usage = data.get("usageMetadata", {})
    return LlmResult(
        text=text,
        prompt_tokens=int(usage.get("promptTokenCount", 0) or 0),
        completion_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
    )


def _http_error(label: str, response) -> str:
    try:
        payload = response.json()
        detail = payload.get("error", {})
        message = detail.get("message") if isinstance(detail, dict) else str(detail)
    except Exception:  # noqa: BLE001
        message = response.text[:200]
    return f"{label} API 오류 ({response.status_code}): {message or '알 수 없는 오류'}"


_DISPATCH = {
    "openai": _openai_chat,
    "anthropic": _anthropic_chat,
    "google": _google_chat,
}


def call_llm(
    system: str,
    user: str,
    *,
    feature: str,
    json_mode: bool = False,
    temperature: float = 0.2,
    db=None,
    user_id: str | None = None,
    cfg: ProviderConfig | None = None,
) -> str:
    """활성 프로바이더로 LLM 을 호출하고 사용량을 기록한 뒤 텍스트를 돌려준다."""
    cfg = cfg or active_config(db)
    if not cfg.ready:
        raise AIEngineError(f"{cfg.label} API 키가 설정되지 않았습니다. 설정 → API 연동에서 등록하세요.")

    handler = _DISPATCH.get(cfg.provider)
    if handler is None:
        raise AIEngineError(f"지원하지 않는 프로바이더입니다: {cfg.provider}")

    started = time.perf_counter()
    try:
        result = handler(cfg, system, user, json_mode, temperature)
    except AIEngineError as exc:
        record_usage(
            db,
            provider=cfg.provider,
            model=cfg.model,
            feature=feature,
            status="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_message=str(exc),
            user_id=user_id,
        )
        raise
    except Exception as exc:  # noqa: BLE001
        record_usage(
            db,
            provider=cfg.provider,
            model=cfg.model,
            feature=feature,
            status="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_message=str(exc),
            user_id=user_id,
        )
        raise AIEngineError(f"{cfg.label} 호출 실패: {exc}") from exc

    record_usage(
        db,
        provider=cfg.provider,
        model=cfg.model,
        feature=feature,
        status="success",
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=int((time.perf_counter() - started) * 1000),
        user_id=user_id,
    )
    return result.text.strip()


def test_connection(cfg: ProviderConfig, db=None, user_id: str | None = None) -> dict[str, Any]:
    """설정 화면의 '연결 테스트' — 최소 토큰으로 실제 호출해 키 유효성을 확인한다."""
    started = time.perf_counter()
    try:
        text = call_llm(
            "You are a connection tester. Answer with the single word: OK",
            "연결 테스트입니다. 'OK' 한 단어만 답하세요.",
            feature="연결 테스트",
            temperature=0,
            db=db,
            user_id=user_id,
            cfg=cfg,
        )
    except AIEngineError as exc:
        return {
            "ok": False,
            "message": str(exc),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": cfg.model,
        }
    return {
        "ok": True,
        "message": f"{cfg.label} 응답 확인: {text[:60] or 'OK'}",
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "model": cfg.model,
    }


# --------------------------------------------------------------------------- #
# JSON 유틸
# --------------------------------------------------------------------------- #
def _extract_json(raw: str) -> dict[str, Any]:
    """코드펜스/잡텍스트가 섞여 있어도 JSON 오브젝트를 복구한다."""
    if not raw:
        raise AIEngineError("LLM 응답이 비어 있습니다.")

    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise AIEngineError("LLM 이 유효한 JSON 을 반환하지 않았습니다.")


# --------------------------------------------------------------------------- #
# 1) 음성 전사 — OpenAI Whisper 또는 Gemini 오디오 입력
# --------------------------------------------------------------------------- #
_AUDIO_MIME = {
    ".webm": "audio/webm",
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".mpeg": "audio/mp3",
    ".mp4": "audio/mp4",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".flac": "audio/flac",
}

STT_PROMPT = (
    "이 오디오를 한국어로 정확히 받아 적으세요.\n"
    "- 말한 내용만 출력합니다. 인사말·설명·마크다운은 넣지 마세요.\n"
    "- 화자가 구분되면 '이름: 내용' 형식을 쓰고, 이름이 없으면 '화자1:' 처럼 번호로 구분하세요.\n"
    "- 알아듣기 어려운 부분은 (불명)으로 표기하세요."
)


def _audio_mime(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in _AUDIO_MIME:
        return _AUDIO_MIME[suffix]
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed and guessed.startswith("audio/"):
        return guessed
    return "audio/webm"


def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "meeting.wav",
    language: str = "ko",
    db=None,
    user_id: str | None = None,
) -> str:
    if not audio_bytes:
        raise AIEngineError("오디오 데이터가 비어 있습니다.")

    cfg = stt_config(db)
    if not cfg.ready:
        if settings.allow_mock_ai:
            record_usage(
                db, provider="mock", model=cfg.model, feature="음성 전사", status="mock",
                user_id=user_id,
            )
            return _mock_transcript()
        raise AIEngineError(
            "음성 전사를 실행할 수 없습니다. 설정의 API 연동에서 OpenAI 또는 Google Gemini 키를 등록하세요."
        )

    started = time.perf_counter()
    used_model = cfg.model
    try:
        if cfg.provider == "google":
            text, prompt_tokens, completion_tokens, used_model = _gemini_transcribe(
                cfg, audio_bytes, filename
            )
        else:
            text = _whisper_transcribe(cfg, audio_bytes, filename, language)
            prompt_tokens = completion_tokens = 0
    except AIEngineError as exc:
        record_usage(
            db, provider=cfg.provider, model=used_model, feature="음성 전사", status="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_message=str(exc), user_id=user_id,
        )
        raise
    except Exception as exc:  # noqa: BLE001
        record_usage(
            db, provider=cfg.provider, model=used_model, feature="음성 전사", status="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_message=str(exc), user_id=user_id,
        )
        raise AIEngineError(f"음성 전사 호출 실패: {exc}") from exc

    record_usage(
        db, provider=cfg.provider, model=used_model, feature="음성 전사", status="success",
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        latency_ms=int((time.perf_counter() - started) * 1000), user_id=user_id,
    )
    return text


def _whisper_transcribe(
    cfg: ProviderConfig, audio_bytes: bytes, filename: str, language: str
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise AIEngineError("openai 패키지가 설치되어 있지 않습니다.") from exc

    if len(audio_bytes) > WHISPER_AUDIO_BYTES:
        raise AIEngineError(
            "OpenAI Whisper는 파일당 25MB까지입니다. "
            "더 긴 회의는 설정에서 Gemini로 바꾸거나, 파일을 압축해 주세요."
        )

    buffer = io.BytesIO(audio_bytes)
    buffer.name = filename or "meeting.wav"
    result = OpenAI(api_key=cfg.api_key, timeout=STT_TIMEOUT).audio.transcriptions.create(
        model=cfg.model,
        file=buffer,
        language=language,
        response_format="text",
    )
    return result if isinstance(result, str) else getattr(result, "text", str(result))


def _gemini_parse_transcript(response) -> tuple[str, int, int]:
    if response.status_code >= 400:
        raise AIEngineError(_http_error("Google Gemini STT", response))

    data = response.json()
    candidates = data.get("candidates") or []
    text = ""
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise AIEngineError("Gemini 가 전사 결과를 반환하지 않았습니다.")
    usage = data.get("usageMetadata", {})
    return (
        text,
        int(usage.get("promptTokenCount", 0) or 0),
        int(usage.get("candidatesTokenCount", 0) or 0),
    )


def _gemini_stt_models(preferred: str) -> list[str]:
    """설정된 모델 우선, 오디오를 받는 flash 계열로 폴백."""
    flash = [name for name in AI_PROVIDERS["google"]["models"] if "pro" not in name.lower()]
    ordered: list[str] = []
    for name in (preferred, *flash):
        if name and name not in ordered:
            ordered.append(name)
    return ordered[:4]


def _gemini_generate_audio(
    cfg: ProviderConfig, audio_part: dict
) -> tuple[str, int, int, str]:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": STT_PROMPT}, audio_part],
            }
        ],
        "generationConfig": {"temperature": 0},
    }
    last_response = None
    for model in _gemini_stt_models(cfg.model):
        response = _gemini_generate_content(
            cfg.api_key, model, payload, timeout=STT_TIMEOUT, delays=(0.0, 2.0)
        )
        last_response = response
        if response.status_code < 400:
            text, prompt_tokens, completion_tokens = _gemini_parse_transcript(response)
            if model != cfg.model:
                logger.info("Gemini STT fallback model=%s (preferred=%s)", model, cfg.model)
            return text, prompt_tokens, completion_tokens, model
        if response.status_code in (401, 403):
            break
        logger.warning(
            "Gemini STT model=%s failed status=%s, trying next",
            model,
            response.status_code,
        )
    busy = _gemini_busy_message(last_response.status_code if last_response is not None else None)
    raise AIEngineError(busy or _http_error("Google Gemini STT", last_response))


def _gemini_upload_file(api_key: str, audio_bytes: bytes, filename: str) -> tuple[str, str]:
    import httpx

    mime = _audio_mime(filename)
    display = Path(filename or "meeting").name
    start = httpx.post(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        params={"key": api_key},
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(audio_bytes)),
            "X-Goog-Upload-Header-Content-Type": mime,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": display}},
        timeout=60.0,
    )
    if start.status_code >= 400:
        raise AIEngineError(_http_error("Google Gemini 파일 업로드", start))
    upload_url = start.headers.get("x-goog-upload-url") or start.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise AIEngineError("Gemini 파일 업로드 URL을 받지 못했습니다.")

    uploaded = httpx.post(
        upload_url,
        headers={
            "Content-Length": str(len(audio_bytes)),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        content=audio_bytes,
        timeout=STT_TIMEOUT,
    )
    if uploaded.status_code >= 400:
        raise AIEngineError(_http_error("Google Gemini 파일 업로드", uploaded))

    info = (uploaded.json() or {}).get("file") or uploaded.json()
    name = info.get("name")
    uri = info.get("uri")
    if not name or not uri:
        raise AIEngineError("Gemini 가 업로드된 파일 정보를 반환하지 않았습니다.")

    for _ in range(90):
        state = (info.get("state") or "").upper()
        if state == "ACTIVE":
            return uri, mime
        if state == "FAILED":
            raise AIEngineError("Gemini 가 오디오 파일을 처리하지 못했습니다.")
        time.sleep(2)
        poll = httpx.get(
            f"https://generativelanguage.googleapis.com/v1beta/{name}",
            params={"key": api_key},
            timeout=30.0,
        )
        if poll.status_code >= 400:
            raise AIEngineError(_http_error("Google Gemini 파일 상태", poll))
        info = poll.json()
        uri = info.get("uri") or uri
    raise AIEngineError("Gemini 파일 처리가 너무 오래 걸립니다. 잠시 후 다시 시도해 주세요.")


def _gemini_delete_file(api_key: str, file_uri: str) -> None:
    import httpx

    name = file_uri.rsplit("/", 1)[-1]
    if not name:
        return
    try:
        httpx.delete(
            f"https://generativelanguage.googleapis.com/v1beta/files/{name}",
            params={"key": api_key},
            timeout=15.0,
        )
    except Exception:  # noqa: BLE001
        pass


def _gemini_transcribe(
    cfg: ProviderConfig, audio_bytes: bytes, filename: str
) -> tuple[str, int, int, str]:
    if len(audio_bytes) <= GEMINI_INLINE_MAX_BYTES:
        return _gemini_generate_audio(
            cfg,
            {
                "inlineData": {
                    "mimeType": _audio_mime(filename),
                    "data": base64.b64encode(audio_bytes).decode("ascii"),
                }
            },
        )

    uri, mime = _gemini_upload_file(cfg.api_key, audio_bytes, filename)
    try:
        return _gemini_generate_audio(cfg, {"fileData": {"mimeType": mime, "fileUri": uri}})
    finally:
        _gemini_delete_file(cfg.api_key, uri)


# --------------------------------------------------------------------------- #
# 2) 회의록 구조화 파싱
# --------------------------------------------------------------------------- #
PARSE_SYSTEM_PROMPT = """당신은 한국 기업의 회의록을 분석하는 전문 AI 비서입니다.
회의 전사(transcript)를 읽고 아래 규칙에 따라 JSON 오브젝트 하나만 출력하세요.

규칙:
1. 모든 텍스트는 한국어로 작성합니다.
2. status 는 반드시 ["할당", "진행중", "이슈 발생", "완료"] 중 하나입니다.
3. progress 는 0~100 사이 정수입니다. 기존 업무는 전사에 진행률·상태·이슈·담당·기한이
   명시된 경우에만 그 필드를 바꾸고, 언급이 없으면 해당 필드를 비우거나 생략합니다.
   추정치로 기존 업무의 진행률을 바꿔 넣지 마세요.
4. task_updates 에는 다음만 넣습니다.
   - 기존 업무: 전사에서 상태/진행률/이슈/담당/기한이 실제로 바뀐 항목만.
     task_id 는 "현재 업무 목록"의 값을 그대로 사용합니다.
     이름만 비슷하고 변경 근거가 없으면 넣지 마세요.
   - 신규 업무: 회의에서 새로 하기로 한 일, 후속 액션, 기존 목록에 없는 핵심 과제.
     task_id 는 "NEW" 로 두고 task_name 을 명확히 작성합니다.
   기존 업무와 이름이 애매하게만 비슷하면 기존 ID를 쓰지 말고 NEW 로 만드세요.
   현재 업무 목록을 관례적으로 전부 복사해 넣지 마세요.
5. action_items 에 넣은 후속은 반드시 task_updates 에도 task_id "NEW" 로 다시 넣습니다.
   (칸반에 업무로 반영하기 위함입니다.)
6. assignee 는 제공된 "구성원 목록"의 user_id 값을 사용합니다. 확실하지 않으면 빈 문자열("")로 둡니다.
7. 날짜는 YYYY-MM-DD 형식이며 알 수 없으면 빈 문자열("")로 둡니다.
8. 추측으로 사실을 만들지 말고 전사에 근거가 있는 내용만 담습니다.

출력 JSON 스키마:
{
  "meeting_title": "회의 제목",
  "summary_bullets": ["핵심 요약 3~6개"],
  "agenda_items": [{"topic": "안건명", "discussion": "논의 내용", "decision": "결정 사항"}],
  "action_items": [{"title": "액션 아이템", "assignee": "user_id 또는 빈 문자열", "due_date": "YYYY-MM-DD 또는 빈 문자열", "note": "비고"}],
  "task_updates": [{"task_id": "TASK-001 또는 NEW", "task_name": "업무명", "assignee": "user_id", "progress": 80, "status": "진행중", "issues": "이슈", "due_date": "YYYY-MM-DD 또는 빈 문자열"}],
  "risks": ["리스크 또는 지연 요인"]
}"""


def parse_meeting(
    transcript: str,
    tasks_context: list[dict[str, Any]],
    users_context: list[dict[str, Any]],
    meeting_date: date | None = None,
    db=None,
    user_id: str | None = None,
    event_title: str = "",
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    transcript = (transcript or "").strip()
    if not transcript:
        raise AIEngineError("전사 텍스트가 비어 있습니다.")

    cfg = active_config(db)
    if not cfg.ready:
        if settings.allow_mock_ai:
            record_usage(
                db, provider="mock", model="demo", feature="회의 파싱", status="mock",
                user_id=user_id,
            )
            return normalize_parsed(
                _mock_parsed(tasks_context), tasks_context, users_context
            )
        raise AIEngineError(f"{cfg.label} API 키가 설정되지 않았습니다.")

    calendar_hint = ""
    if event_title or attendees:
        calendar_hint = (
            "\n[캘린더 일정 정보]\n"
            f"- 회의 제목: {event_title or '(없음)'}\n"
            f"- 참석자: {', '.join(attendees or []) or '(없음)'}\n"
            "회의 제목은 위 캘린더 제목을 그대로 쓰고, 발언자 추정 시 참석자 명단을 우선 참고하세요.\n"
        )

    user_prompt = f"""[회의 일자] {(meeting_date or date.today()).isoformat()}
{calendar_hint}
[구성원 목록]
{json.dumps(users_context, ensure_ascii=False, indent=2)}

[현재 업무 목록]
{json.dumps(tasks_context, ensure_ascii=False, indent=2)}

[회의 전사]
\"\"\"
{transcript[:20000]}
\"\"\"

위 내용을 분석해 스키마에 맞는 JSON 만 출력하세요.
기존 업무는 값이 바뀐 것만, 회의의 핵심 후속은 NEW 업무로 넣으세요."""

    raw = call_llm(
        PARSE_SYSTEM_PROMPT,
        user_prompt,
        feature="회의 파싱",
        json_mode=True,
        temperature=0.2,
        db=db,
        user_id=user_id,
        cfg=cfg,
    )
    return normalize_parsed(_extract_json(raw), tasks_context, users_context)


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _title_key(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").casefold())


def _titles_close(left: str, right: str, cutoff: float = 0.85) -> bool:
    a, b = _title_key(left), _title_key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= cutoff


def _field_provided(item: dict[str, Any], key: str) -> bool:
    if key not in item:
        return False
    value = item.get(key)
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _change_note(current: dict[str, Any], proposed: dict[str, Any]) -> str:
    parts: list[str] = []
    if (current.get("status") or "") != proposed["status"]:
        parts.append(f"상태 {current.get('status') or '-'} → {proposed['status']}")
    if int(current.get("progress") or 0) != int(proposed["progress"]):
        parts.append(f"진행률 {int(current.get('progress') or 0)}% → {proposed['progress']}%")
    if (current.get("assigned_to") or "") != (proposed.get("assignee") or ""):
        parts.append("담당자 변경")
    if (current.get("issues") or "").strip() != (proposed.get("issues") or "").strip():
        parts.append("이슈 변경")
    if (current.get("due_date") or "") != (proposed.get("due_date") or ""):
        parts.append("기한 변경")
    if (current.get("task_name") or "").strip() != (proposed.get("task_name") or "").strip():
        parts.append("업무명 변경")
    return " · ".join(parts)


def normalize_parsed(
    data: dict[str, Any],
    tasks_context: list[dict[str, Any]],
    users_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM 출력값 검증/정규화 — 잘못된 상태값·진행률·담당자가 DB 로 흘러가지 않도록 방어."""
    task_by_id = {t["task_id"]: t for t in tasks_context}
    name_to_id = {t["task_name"]: t["task_id"] for t in tasks_context}
    valid_user_ids = {u["user_id"] for u in users_context}
    name_to_user = {u["user_name"]: u["user_id"] for u in users_context}

    def _match_task(item: dict[str, Any]) -> str:
        tid = str(item.get("task_id") or "").strip().upper()
        name = str(item.get("task_name") or "").strip()
        if tid in task_by_id:
            return tid
        if name in name_to_id:
            return name_to_id[name]
        # 애매한 유사 일치는 기존 업무에 억지로 붙이지 않는다.
        close = difflib.get_close_matches(name, list(name_to_id), n=1, cutoff=0.88)
        return name_to_id[close[0]] if close else "NEW"

    def _match_user(value: Any) -> str:
        raw = str(value or "").strip()
        if raw in valid_user_ids:
            return raw
        if raw in name_to_user:
            return name_to_user[raw]
        close = difflib.get_close_matches(raw, list(name_to_user), n=1, cutoff=0.7)
        return name_to_user[close[0]] if close else ""

    def _clean_date(value: Any) -> str:
        raw = str(value or "").strip()
        return raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else ""

    def _parse_progress(value: Any, fallback: int) -> int:
        try:
            return max(0, min(100, int(float(value))))
        except (TypeError, ValueError):
            return fallback

    def _overlay_existing(current: dict[str, Any], item: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
        status = str(item.get("status") or "").strip() if _field_provided(item, "status") else base["status"]
        if status not in STATUSES:
            status = str(current.get("status") or base["status"] or "진행중")
        progress = (
            _parse_progress(item.get("progress"), base["progress"])
            if _field_provided(item, "progress")
            else base["progress"]
        )
        assignee = (
            _match_user(item.get("assignee")) or base["assignee"]
            if _field_provided(item, "assignee")
            else base["assignee"]
        )
        issues = (
            str(item.get("issues") or "").strip()
            if _field_provided(item, "issues")
            else base["issues"]
        )
        due_date = (
            _clean_date(item.get("due_date"))
            if _field_provided(item, "due_date")
            else base["due_date"]
        )
        task_name = (
            str(item.get("task_name") or "").strip()
            if _field_provided(item, "task_name")
            else base["task_name"]
        ) or base["task_name"]
        return {
            "task_id": base["task_id"],
            "task_name": task_name,
            "assignee": assignee,
            "progress": progress,
            "status": status,
            "issues": issues,
            "due_date": due_date,
            "is_new": False,
            "change_note": "",
        }

    updates: list[dict[str, Any]] = []
    existing_updates: dict[str, dict[str, Any]] = {}
    for item in _as_list(data.get("task_updates")):
        if not isinstance(item, dict):
            continue
        task_id = _match_task(item)
        current = task_by_id.get(task_id, {})

        if task_id == "NEW" or not current:
            status = str(item.get("status") or "").strip()
            if status not in STATUSES:
                status = "할당"
            progress = _parse_progress(
                item.get("progress"), STATUS_DEFAULT_PROGRESS.get(status, 0)
            )
            proposed = {
                "task_id": "NEW",
                "task_name": str(item.get("task_name") or "").strip(),
                "assignee": _match_user(item.get("assignee")),
                "progress": progress,
                "status": status,
                "issues": str(item.get("issues") or "").strip(),
                "due_date": _clean_date(item.get("due_date")),
                "is_new": True,
                "change_note": "회의 후속으로 신규 등록",
            }
            if not proposed["task_name"]:
                continue
            if any(_titles_close(proposed["task_name"], u["task_name"]) for u in updates):
                continue
            updates.append(proposed)
            continue

        base = existing_updates.get(task_id) or {
            "task_id": task_id,
            "task_name": str(current.get("task_name") or ""),
            "assignee": current.get("assigned_to") or "",
            "progress": int(current.get("progress") or 0),
            "status": str(current.get("status") or "진행중"),
            "issues": str(current.get("issues") or "").strip(),
            "due_date": str(current.get("due_date") or ""),
            "is_new": False,
            "change_note": "",
        }
        existing_updates[task_id] = _overlay_existing(current, item, base)

    for task_id, proposed in existing_updates.items():
        current = task_by_id[task_id]
        note = _change_note(current, proposed)
        if not note:
            continue
        proposed["change_note"] = note
        updates.append(proposed)

    agenda_items = []
    for item in _as_list(data.get("agenda_items")):
        if isinstance(item, dict):
            agenda_items.append(
                {
                    "topic": str(item.get("topic") or "").strip(),
                    "discussion": str(item.get("discussion") or "").strip(),
                    "decision": str(item.get("decision") or "").strip(),
                }
            )
        elif isinstance(item, str):
            agenda_items.append({"topic": item, "discussion": "", "decision": ""})

    action_items = []
    for item in _as_list(data.get("action_items")):
        if isinstance(item, dict):
            action_items.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "assignee": _match_user(item.get("assignee")),
                    "due_date": _clean_date(item.get("due_date")),
                    "note": str(item.get("note") or "").strip(),
                }
            )
        elif isinstance(item, str):
            action_items.append({"title": item, "assignee": "", "due_date": "", "note": ""})

    for action in action_items:
        title = action.get("title") or ""
        if not title:
            continue
        if any(_titles_close(title, u["task_name"]) for u in updates):
            continue
        updates.append(
            {
                "task_id": "NEW",
                "task_name": title,
                "assignee": action.get("assignee") or "",
                "progress": 0,
                "status": "할당",
                "issues": action.get("note") or "",
                "due_date": action.get("due_date") or "",
                "is_new": True,
                "change_note": "액션 아이템에서 신규 업무로 반영",
            }
        )

    return {
        "meeting_title": str(data.get("meeting_title") or "제목 없는 회의").strip(),
        "summary_bullets": [
            str(x).strip() for x in _as_list(data.get("summary_bullets")) if str(x).strip()
        ],
        "agenda_items": agenda_items,
        "action_items": action_items,
        "task_updates": updates,
        "risks": [str(x).strip() for x in _as_list(data.get("risks")) if str(x).strip()],
    }


def summary_to_markdown(parsed: dict[str, Any]) -> str:
    lines = [f"# {parsed.get('meeting_title', '회의 요약')}", "", "## 핵심 요약"]
    lines += [f"- {b}" for b in parsed.get("summary_bullets", [])] or ["- (없음)"]

    if parsed.get("agenda_items"):
        lines += ["", "## 안건"]
        for i, item in enumerate(parsed["agenda_items"], start=1):
            lines.append(f"{i}. **{item.get('topic', '')}**")
            if item.get("discussion"):
                lines.append(f"   - 논의: {item['discussion']}")
            if item.get("decision"):
                lines.append(f"   - 결정: {item['decision']}")

    if parsed.get("action_items"):
        lines += ["", "## 액션 아이템"]
        for item in parsed["action_items"]:
            due = f" (기한: {item['due_date']})" if item.get("due_date") else ""
            owner = f" / 담당: {item['assignee']}" if item.get("assignee") else ""
            lines.append(f"- {item.get('title', '')}{owner}{due}")

    if parsed.get("task_updates"):
        lines += ["", "## 업무 업데이트"]
        for item in parsed["task_updates"]:
            lines.append(
                f"- `{item.get('task_id')}` {item.get('task_name')} → "
                f"{item.get('status')} ({item.get('progress')}%)"
                + (f" / 이슈: {item['issues']}" if item.get("issues") else "")
            )

    if parsed.get("risks"):
        lines += ["", "## 리스크"]
        lines += [f"- {r}" for r in parsed["risks"]]

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 3) 경영 요약 리포트
# --------------------------------------------------------------------------- #
REPORT_SYSTEM_PROMPT = """당신은 조직의 업무 현황을 경영진에게 보고하는 시니어 PMO 분석가입니다.
주어진 업무 데이터를 바탕으로 한국어 마크다운 보고서를 작성하세요.

반드시 아래 구조를 지키세요:
## 📌 총평
## ✅ 주요 성과
## ⚠️ 지연 및 병목
## 🚨 리스크 알림
## 🎯 다음 기간 권고 액션

작성 원칙:
- 데이터에 근거한 사실만 서술하고 숫자(진행률, 건수, 지연일)를 함께 제시합니다.
- 각 섹션은 3~5개의 불릿으로 간결하게 작성합니다.
- 담당자 이름과 업무 ID 를 명시해 실행 가능하게 씁니다.
- week_over_week 데이터가 있으면 총평·성과에서 전주 대비 증감(건수, 완료율, 평균 진행률)을 반드시 언급합니다.
- 업무별 전주 대비 목록은 시스템이 뒤에 붙이므로 작성하지 마세요."""


def generate_period_report(
    period_label: str,
    scope_label: str,
    stats: dict[str, Any],
    tasks: list[dict[str, Any]],
    db=None,
    user_id: str | None = None,
    weekly_compare: str = "",
) -> str:
    cfg = active_config(db)
    if not cfg.ready:
        if settings.allow_mock_ai:
            record_usage(
                db, provider="mock", model="demo", feature="경영 리포트", status="mock",
                user_id=user_id,
            )
            return _join_weekly(_mock_report(period_label, scope_label, stats, tasks), weekly_compare)
        raise AIEngineError(f"{cfg.label} API 키가 설정되지 않았습니다.")

    wow = stats.get("week_over_week")
    wow_note = ""
    if wow:
        wow_note = f"""
[전주 대비]
전주 {wow.get("last_period")} → 이번주 {wow.get("this_period")}
업무 수 {wow.get("last_total")}건 → {wow.get("this_total")}건
완료 {wow.get("last_completed")}건 → {wow.get("this_completed")}건
완료율 {wow.get("last_completion_rate")}% → {wow.get("this_completion_rate")}%
평균 진행률 {wow.get("last_avg_progress")}% → {wow.get("this_avg_progress")}%
지연 {wow.get("last_delayed")}건 → {wow.get("this_delayed")}건
"""

    user_prompt = f"""[보고 기간] {period_label}
[보고 범위] {scope_label}

[집계 지표]
{json.dumps(stats, ensure_ascii=False, indent=2)}
{wow_note}
[업무 상세]
{json.dumps(tasks[:120], ensure_ascii=False, indent=2)}

위 데이터를 바탕으로 경영진 보고용 마크다운 리포트를 작성하세요."""

    markdown = call_llm(
        REPORT_SYSTEM_PROMPT,
        user_prompt,
        feature="경영 리포트",
        temperature=0.3,
        db=db,
        user_id=user_id,
        cfg=cfg,
    )
    return _join_weekly(markdown, weekly_compare)


def _join_weekly(markdown: str, weekly_compare: str) -> str:
    extra = (weekly_compare or "").strip()
    if not extra:
        return markdown
    return markdown.rstrip() + "\n\n" + extra


# --------------------------------------------------------------------------- #
# Mock (API Key 없이 전체 플로우 시연)
# --------------------------------------------------------------------------- #
def _mock_transcript() -> str:
    return (
        "[데모 전사 — STT 키가 없어 생성된 샘플입니다]\n"
        "박팀장: 주간 회의 시작하겠습니다. 로그인 API 진행 상황부터 볼까요?\n"
        "이사원: 로그인 API 는 현재 80% 정도 완료했습니다. 리프레시 토큰 정책만 확정되면 이번 주 안에 끝납니다.\n"
        "박팀장: 좋습니다. 대시보드 UI 는요?\n"
        "최사원: 퍼블리싱은 끝났고 QA 만 남아서 검토 필요 상태입니다. 모바일 반응형에서 카드가 깨지는 이슈가 있습니다.\n"
        "박팀장: 이번 주 내로 처리해 주세요. 회의록 STT 파이프라인은 다음 주부터 이사원 님이 착수해 주시고,\n"
        "분기 로드맵 리뷰는 협력사 회신이 늦어져서 일정이 밀리고 있습니다."
    )


_MOCK_RULES: list[tuple[tuple[str, ...], dict[str, Any]]] = [
    (("로그인", "인증"), {"status": "진행중", "progress": 80, "issues": "리프레시 토큰 정책 확정 대기"}),
    (("대시보드", "퍼블리싱"), {"status": "이슈 발생", "progress": 95, "issues": "모바일 반응형 카드 깨짐 이슈"}),
    (("stt", "회의록"), {"status": "진행중", "progress": 10, "issues": ""}),
    (("로드맵",), {"status": "진행중", "progress": 45, "issues": "협력사 회신 지연으로 일정 지연"}),
]


def _mock_parsed(tasks_context: list[dict[str, Any]]) -> dict[str, Any]:
    """업무명 키워드로 매칭해 데모에서도 자연스러운 업데이트를 만든다."""
    updates = []
    for task in tasks_context:
        name = task["task_name"].lower()
        for keywords, preset in _MOCK_RULES:
            if any(keyword in name for keyword in keywords):
                updates.append(
                    {
                        "task_id": task["task_id"],
                        "task_name": task["task_name"],
                        "assignee": task.get("assigned_to") or "",
                        "due_date": "",
                        **preset,
                    }
                )
                break

    return {
        "meeting_title": "주간 업무 점검 회의 (데모)",
        "summary_bullets": [
            "로그인 API 개발이 80% 진행되어 금주 완료 예정",
            "대시보드 UI 퍼블리싱 완료, QA 검토 단계 진입",
            "회의록 STT 파이프라인 다음 주 착수 결정",
            "분기 로드맵 리뷰는 협력사 회신 지연으로 일정 지연",
        ],
        "agenda_items": [
            {
                "topic": "로그인 API 진행 점검",
                "discussion": "80% 완료, 리프레시 토큰 저장소 정책만 미확정",
                "decision": "금주 내 정책 확정 후 개발 마무리",
            },
            {
                "topic": "대시보드 UI QA",
                "discussion": "퍼블리싱 완료, 모바일 반응형 이슈 발견",
                "decision": "금주 내 반응형 이슈 수정",
            },
        ],
        "action_items": [
            {"title": "리프레시 토큰 정책 확정", "assignee": "", "due_date": "", "note": "보안팀 협의 필요"},
            {"title": "모바일 반응형 카드 레이아웃 수정", "assignee": "", "due_date": "", "note": ""},
        ],
        "task_updates": updates,
        "risks": ["협력사 회신 지연으로 분기 로드맵 리뷰 일정 지연 위험"],
    }


def _mock_report(
    period_label: str, scope_label: str, stats: dict[str, Any], tasks: list[dict[str, Any]]
) -> str:
    delayed = [t for t in tasks if t.get("is_delayed")]
    done = [t for t in tasks if t.get("status") == "완료"]
    lines = [
        "> ⚠️ 데모 모드 리포트입니다. `backend/.env` 에 OPENAI_API_KEY 를 설정하면 GPT-4o 가 실제 리포트를 생성합니다.",
        "",
        "## 📌 총평",
        f"- {scope_label} 기준 {period_label} 동안 총 {stats.get('total', 0)}건의 업무가 관리되었으며 평균 진행률은 {stats.get('avg_progress', 0)}% 입니다.",
        f"- 완료 {stats.get('완료', 0)}건 / 진행중 {stats.get('진행중', 0)}건 / 이슈 발생 {stats.get('이슈 발생', 0)}건 / 할당 {stats.get('할당', 0)}건 입니다.",
    ]
    wow = stats.get("week_over_week") or {}
    if wow:
        lines.append(
            f"- 전주({wow.get('last_period')}) 대비 업무 {wow.get('last_total')}건 → {wow.get('this_total')}건, "
            f"완료율 {wow.get('last_completion_rate')}% → {wow.get('this_completion_rate')}%, "
            f"평균 진행률 {wow.get('last_avg_progress')}% → {wow.get('this_avg_progress')}% 입니다."
        )
    lines += [
        "",
        "## ✅ 주요 성과",
    ]
    lines += [
        f"- `{t['task_id']}` {t['task_name']} 완료 (담당: {t.get('assignee_name', '-')})"
        for t in done[:5]
    ] or ["- 기간 내 완료된 업무가 없습니다."]
    lines += ["", "## ⚠️ 지연 및 병목"]
    lines += [
        f"- `{t['task_id']}` {t['task_name']} — 마감 {t.get('due_date', '-')} 초과, 진행률 {t.get('progress', 0)}%"
        for t in delayed[:5]
    ] or ["- 지연 업무가 없습니다."]
    lines += ["", "## 🚨 리스크 알림"]
    lines += [f"- `{t['task_id']}` {t.get('issues')}" for t in tasks if t.get("issues")][:5] or [
        "- 등록된 이슈가 없습니다."
    ]
    lines += [
        "",
        "## 🎯 다음 기간 권고 액션",
        "- 지연 업무의 마감일 재산정 및 담당자 리소스 재배분",
        "- 이슈 발생 상태 업무의 원인 정리 및 해소 마감일 설정",
        "- 미착수 업무의 착수일 확정",
    ]
    return "\n".join(lines)
