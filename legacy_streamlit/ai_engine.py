"""Whisper STT · LLM 회의록 파싱 · 기간별 요약 리포트 엔진."""

from __future__ import annotations

import difflib
import io
import json
import re
from datetime import date
from typing import Any

from config import STATUSES, STATUS_DEFAULT_PROGRESS, settings


class AIEngineError(RuntimeError):
    """AI 호출 실패 시 사용자에게 보여줄 예외."""


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #
def _openai_client():
    if not settings.has_openai:
        raise AIEngineError("OPENAI_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise AIEngineError("openai 패키지가 설치되어 있지 않습니다.") from exc
    return OpenAI(api_key=settings.openai_api_key)


def _gemini_model():
    if not settings.has_gemini:
        raise AIEngineError("GEMINI_API_KEY 가 설정되지 않았습니다.")
    try:
        import google.generativeai as genai
    except ImportError as exc:  # pragma: no cover
        raise AIEngineError("google-generativeai 패키지가 설치되어 있지 않습니다.") from exc
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(settings.gemini_text_model)


def ai_status() -> dict[str, Any]:
    """사이드바 등에 표시할 AI 연결 상태."""
    return {
        "provider": settings.llm_provider,
        "llm_ready": settings.has_llm,
        "stt_ready": settings.has_stt,
        "mock": settings.allow_mock_ai and not settings.has_llm,
    }


# --------------------------------------------------------------------------- #
# 공통 LLM 호출
# --------------------------------------------------------------------------- #
def _extract_json(raw: str) -> dict[str, Any]:
    """코드펜스/잡텍스트가 섞여 있어도 JSON 오브젝트를 최대한 복구한다."""
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


def _chat_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """JSON 강제 모드로 LLM 을 호출한다."""
    if settings.llm_provider == "gemini":
        model = _gemini_model()
        response = model.generate_content(
            f"{system_prompt}\n\n{user_prompt}",
            generation_config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        return _extract_json(response.text or "")

    client = _openai_client()
    completion = client.chat.completions.create(
        model=settings.openai_text_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _extract_json(completion.choices[0].message.content or "")


def _chat_text(system_prompt: str, user_prompt: str) -> str:
    if settings.llm_provider == "gemini":
        model = _gemini_model()
        response = model.generate_content(
            f"{system_prompt}\n\n{user_prompt}",
            generation_config={"temperature": 0.3},
        )
        return (response.text or "").strip()

    client = _openai_client()
    completion = client.chat.completions.create(
        model=settings.openai_text_model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (completion.choices[0].message.content or "").strip()


# --------------------------------------------------------------------------- #
# 1) STT
# --------------------------------------------------------------------------- #
def transcribe_audio(audio_bytes: bytes, filename: str = "meeting.wav", language: str = "ko") -> str:
    """OpenAI Whisper API 로 음성을 텍스트로 변환한다."""
    if not audio_bytes:
        raise AIEngineError("오디오 데이터가 비어 있습니다.")

    if not settings.has_stt:
        if settings.allow_mock_ai:
            return _mock_transcript()
        raise AIEngineError("OPENAI_API_KEY 가 없어 STT 를 실행할 수 없습니다.")

    client = _openai_client()
    buffer = io.BytesIO(audio_bytes)
    buffer.name = filename or "meeting.wav"
    try:
        result = client.audio.transcriptions.create(
            model=settings.openai_stt_model,
            file=buffer,
            language=language,
            response_format="text",
        )
    except Exception as exc:  # noqa: BLE001 - API 오류를 사용자 메시지로 변환
        raise AIEngineError(f"Whisper STT 호출 실패: {exc}") from exc

    return result if isinstance(result, str) else getattr(result, "text", str(result))


# --------------------------------------------------------------------------- #
# 2) 회의록 파싱
# --------------------------------------------------------------------------- #
PARSE_SYSTEM_PROMPT = """당신은 한국 기업의 회의록을 분석하는 전문 AI 비서입니다.
회의 전사(transcript)를 읽고, 아래 규칙에 따라 반드시 JSON 오브젝트 하나만 출력하세요.

규칙:
1. 모든 텍스트는 한국어로 작성합니다.
2. status 는 반드시 ["시작전", "진행중", "검토필요", "완료"] 중 하나입니다.
3. progress 는 0~100 사이 정수입니다. 언급이 없으면 status 기준 추정치를 넣습니다.
4. task_updates 에는 제공된 "현재 업무 목록"과 매칭되는 항목만 넣고, task_id 는 목록에 있는 값을 그대로 사용합니다.
   신규 업무로 보이면 task_id 를 "NEW" 로 지정하고 task_name 을 명확히 작성합니다.
5. assignee 는 제공된 "구성원 목록"의 user_id 값을 사용합니다. 확실하지 않으면 빈 문자열("")로 둡니다.
6. 날짜는 YYYY-MM-DD 형식이며 알 수 없으면 빈 문자열("")로 둡니다.
7. 추측으로 사실을 만들어내지 말고, 전사에 근거가 있는 내용만 담습니다.

출력 JSON 스키마:
{
  "meeting_title": "회의 제목",
  "summary_bullets": ["핵심 요약 3~6개"],
  "agenda_items": [
    {"topic": "안건명", "discussion": "논의 내용 요약", "decision": "결정 사항"}
  ],
  "action_items": [
    {"title": "액션 아이템", "assignee": "user_id 또는 빈 문자열", "due_date": "YYYY-MM-DD 또는 빈 문자열", "note": "비고"}
  ],
  "task_updates": [
    {"task_id": "TASK-001 또는 NEW", "task_name": "업무명", "assignee": "user_id", "progress": 80, "status": "진행중", "issues": "이슈/리스크", "due_date": "YYYY-MM-DD 또는 빈 문자열"}
  ],
  "risks": ["리스크 또는 지연 요인"]
}"""


def parse_meeting(
    transcript: str,
    tasks_context: list[dict[str, Any]],
    users_context: list[dict[str, Any]],
    meeting_date: date | None = None,
) -> dict[str, Any]:
    """전사 텍스트 → 구조화된 회의 요약/업무 업데이트 JSON."""
    transcript = (transcript or "").strip()
    if not transcript:
        raise AIEngineError("전사 텍스트가 비어 있습니다.")

    if not settings.has_llm:
        if settings.allow_mock_ai:
            return normalize_parsed(_mock_parsed(tasks_context, users_context), tasks_context, users_context)
        raise AIEngineError("LLM API Key 가 설정되지 않았습니다.")

    user_prompt = f"""[회의 일자] {(meeting_date or date.today()).isoformat()}

[구성원 목록]
{json.dumps(users_context, ensure_ascii=False, indent=2)}

[현재 업무 목록]
{json.dumps(tasks_context, ensure_ascii=False, indent=2)}

[회의 전사]
\"\"\"
{transcript[:20000]}
\"\"\"

위 내용을 분석해 스키마에 맞는 JSON 만 출력하세요."""

    data = _chat_json(PARSE_SYSTEM_PROMPT, user_prompt)
    return normalize_parsed(data, tasks_context, users_context)


def normalize_parsed(
    data: dict[str, Any],
    tasks_context: list[dict[str, Any]],
    users_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM 출력값을 앱에서 바로 쓸 수 있게 정규화/검증한다."""
    valid_task_ids = {t["task_id"]: t for t in tasks_context}
    name_to_id = {t["task_name"]: t["task_id"] for t in tasks_context}
    valid_user_ids = {u["user_id"] for u in users_context}
    name_to_user = {u["user_name"]: u["user_id"] for u in users_context}

    def _as_list(value: Any) -> list:
        if isinstance(value, list):
            return value
        if value in (None, ""):
            return []
        return [value]

    def _match_task(update: dict[str, Any]) -> str:
        tid = str(update.get("task_id") or "").strip().upper()
        if tid in valid_task_ids:
            return tid
        name = str(update.get("task_name") or "").strip()
        if name in name_to_id:
            return name_to_id[name]
        close = difflib.get_close_matches(name, list(name_to_id.keys()), n=1, cutoff=0.6)
        if close:
            return name_to_id[close[0]]
        return "NEW"

    def _match_user(value: Any) -> str:
        raw = str(value or "").strip()
        if raw in valid_user_ids:
            return raw
        if raw in name_to_user:
            return name_to_user[raw]
        close = difflib.get_close_matches(raw, list(name_to_user.keys()), n=1, cutoff=0.7)
        return name_to_user[close[0]] if close else ""

    def _clean_date(value: Any) -> str:
        raw = str(value or "").strip()
        return raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else ""

    updates: list[dict[str, Any]] = []
    for item in _as_list(data.get("task_updates")):
        if not isinstance(item, dict):
            continue
        task_id = _match_task(item)
        status = str(item.get("status") or "").strip()
        if status not in STATUSES:
            status = valid_task_ids.get(task_id, {}).get("status", "진행중")

        try:
            progress = int(float(item.get("progress", STATUS_DEFAULT_PROGRESS.get(status, 0))))
        except (TypeError, ValueError):
            progress = STATUS_DEFAULT_PROGRESS.get(status, 0)
        progress = max(0, min(100, progress))

        assignee = _match_user(item.get("assignee"))
        if not assignee and task_id in valid_task_ids:
            assignee = valid_task_ids[task_id].get("assigned_to") or ""

        updates.append(
            {
                "task_id": task_id,
                "task_name": str(item.get("task_name") or valid_task_ids.get(task_id, {}).get("task_name", "")).strip(),
                "assignee": assignee,
                "progress": progress,
                "status": status,
                "issues": str(item.get("issues") or "").strip(),
                "due_date": _clean_date(item.get("due_date")),
                "is_new": task_id == "NEW",
            }
        )

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

    return {
        "meeting_title": str(data.get("meeting_title") or "제목 없는 회의").strip(),
        "summary_bullets": [str(x).strip() for x in _as_list(data.get("summary_bullets")) if str(x).strip()],
        "agenda_items": agenda_items,
        "action_items": action_items,
        "task_updates": updates,
        "risks": [str(x).strip() for x in _as_list(data.get("risks")) if str(x).strip()],
    }


def summary_to_markdown(parsed: dict[str, Any]) -> str:
    """저장/표시용 마크다운 요약 생성."""
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
                f"- `{item['task_id']}` {item['task_name']} → {item['status']} ({item['progress']}%)"
                + (f" / 이슈: {item['issues']}" if item.get("issues") else "")
            )

    if parsed.get("risks"):
        lines += ["", "## 리스크"]
        lines += [f"- {r}" for r in parsed["risks"]]

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 3) 기간별 경영 요약 리포트
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
- 데이터에 근거한 사실만 서술하고, 숫자(진행률, 건수, 지연일)를 함께 제시합니다.
- 각 섹션은 3~5개의 불릿으로 간결하게 작성합니다.
- 담당자 이름과 업무 ID 를 명시해 실행 가능하게 씁니다."""


def generate_period_report(
    period_label: str,
    scope_label: str,
    stats: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> str:
    """주간/월간/연간 경영 요약 리포트 생성."""
    if not settings.has_llm:
        if settings.allow_mock_ai:
            return _mock_report(period_label, scope_label, stats, tasks)
        raise AIEngineError("LLM API Key 가 설정되지 않았습니다.")

    user_prompt = f"""[보고 기간] {period_label}
[보고 범위] {scope_label}

[집계 지표]
{json.dumps(stats, ensure_ascii=False, indent=2)}

[업무 상세]
{json.dumps(tasks[:120], ensure_ascii=False, indent=2)}

위 데이터를 바탕으로 경영진 보고용 마크다운 리포트를 작성하세요."""

    return _chat_text(REPORT_SYSTEM_PROMPT, user_prompt)


# --------------------------------------------------------------------------- #
# Mock (API Key 없이 전체 플로우 테스트용)
# --------------------------------------------------------------------------- #
def _mock_transcript() -> str:
    return (
        "[데모 전사 - OPENAI_API_KEY 미설정 상태에서 생성된 샘플입니다]\n"
        "박팀장: 자, 주간 회의 시작하겠습니다. 먼저 로그인 API 진행 상황부터 볼까요?\n"
        "이사원: 로그인 API는 현재 80% 정도 완료했습니다. 리프레시 토큰 정책만 확정되면 이번 주 안에 끝납니다.\n"
        "박팀장: 좋습니다. 대시보드 UI는요?\n"
        "최사원: 퍼블리싱은 다 끝났고 QA만 남아서 검토 필요 상태입니다. 모바일 반응형에서 카드가 깨지는 이슈가 하나 있습니다.\n"
        "박팀장: 그건 이번 주 내로 처리해 주세요. 회의록 STT 파이프라인은 다음 주부터 착수하는 걸로 하고,\n"
        "이사원 님이 맡아서 진행해 주세요. 분기 로드맵 리뷰는 협력사 회신이 늦어져서 일정이 밀리고 있습니다."
    )


def _mock_parsed(
    tasks_context: list[dict[str, Any]], users_context: list[dict[str, Any]]
) -> dict[str, Any]:
    updates = []
    presets = [("진행중", 80, "리프레시 토큰 정책 확정 대기"), ("검토필요", 95, "모바일 반응형 카드 깨짐 이슈"), ("진행중", 10, "")]
    for task, (status, progress, issues) in zip(tasks_context, presets):
        updates.append(
            {
                "task_id": task["task_id"],
                "task_name": task["task_name"],
                "assignee": task.get("assigned_to") or "",
                "progress": progress,
                "status": status,
                "issues": issues,
                "due_date": "",
            }
        )
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
        "> ⚠️ 데모 모드 리포트입니다. `.env` 에 API Key 를 설정하면 LLM 이 실제 리포트를 생성합니다.",
        "",
        "## 📌 총평",
        f"- {scope_label} 기준 {period_label} 동안 총 {stats.get('total', 0)}건의 업무가 관리되었으며 평균 진행률은 {stats.get('avg_progress', 0)}% 입니다.",
        f"- 완료 {stats.get('완료', 0)}건 / 진행중 {stats.get('진행중', 0)}건 / 검토필요 {stats.get('검토필요', 0)}건 / 시작전 {stats.get('시작전', 0)}건 입니다.",
        "",
        "## ✅ 주요 성과",
    ]
    lines += [f"- `{t['task_id']}` {t['task_name']} 완료 (담당: {t.get('assignee_name', '-')})" for t in done[:5]] or ["- 기간 내 완료된 업무가 없습니다."]
    lines += ["", "## ⚠️ 지연 및 병목"]
    lines += [
        f"- `{t['task_id']}` {t['task_name']} — 마감 {t.get('due_date', '-')} 초과, 진행률 {t.get('progress', 0)}%"
        for t in delayed[:5]
    ] or ["- 지연 업무가 없습니다."]
    lines += ["", "## 🚨 리스크 알림"]
    lines += [f"- `{t['task_id']}` {t.get('issues')}" for t in tasks if t.get("issues")][:5] or ["- 등록된 이슈가 없습니다."]
    lines += [
        "",
        "## 🎯 다음 기간 권고 액션",
        "- 지연 업무의 마감일 재산정 및 담당자 리소스 재배분",
        "- 검토필요 상태 업무의 리뷰어 지정 및 승인 마감일 설정",
        "- 미착수 업무의 착수일 확정",
    ]
    return "\n".join(lines)
