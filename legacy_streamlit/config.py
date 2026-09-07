"""환경 변수 및 애플리케이션 전역 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _get(key: str, default: str = "") -> str:
    """환경변수 우선, 없으면 Streamlit secrets 에서 값을 찾는다."""
    value = os.getenv(key)
    if value:
        return value
    try:  # secrets.toml 이 없으면 streamlit 이 예외를 던지므로 방어
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


def _get_bool(key: str, default: bool = False) -> bool:
    raw = _get(key, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


STATUSES: list[str] = ["시작전", "진행중", "검토필요", "완료"]

STATUS_COLORS: dict[str, str] = {
    "시작전": "#94a3b8",
    "진행중": "#3b82f6",
    "검토필요": "#f59e0b",
    "완료": "#22c55e",
}

# 상태 변경 시 자동으로 맞춰줄 기본 진행률
STATUS_DEFAULT_PROGRESS: dict[str, int] = {
    "시작전": 0,
    "진행중": 50,
    "검토필요": 90,
    "완료": 100,
}

ROLES: list[str] = ["ADMIN", "LEADER", "MEMBER"]

ROLE_LABELS: dict[str, str] = {
    "ADMIN": "관리자",
    "LEADER": "팀장",
    "MEMBER": "팀원",
}

SUPPORTED_AUDIO = ["mp3", "m4a", "wav", "mp4", "mpeg", "mpga", "webm"]


@dataclass(frozen=True)
class Settings:
    app_title: str = field(default_factory=lambda: _get("APP_TITLE", "AI Note - 업무 관리 대시보드"))
    db_url: str = field(default_factory=lambda: _get("DB_URL", f"sqlite:///{BASE_DIR / 'ainote.db'}"))

    llm_provider: str = field(default_factory=lambda: _get("LLM_PROVIDER", "openai").lower())
    openai_api_key: str = field(default_factory=lambda: _get("OPENAI_API_KEY"))
    openai_text_model: str = field(default_factory=lambda: _get("OPENAI_TEXT_MODEL", "gpt-4o-mini"))
    openai_stt_model: str = field(default_factory=lambda: _get("OPENAI_STT_MODEL", "whisper-1"))

    gemini_api_key: str = field(default_factory=lambda: _get("GEMINI_API_KEY"))
    gemini_text_model: str = field(default_factory=lambda: _get("GEMINI_TEXT_MODEL", "gemini-1.5-flash"))

    allow_mock_ai: bool = field(default_factory=lambda: _get_bool("ALLOW_MOCK_AI", True))

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_llm(self) -> bool:
        return self.has_gemini if self.llm_provider == "gemini" else self.has_openai

    @property
    def has_stt(self) -> bool:
        # STT 는 OpenAI Whisper 만 사용
        return self.has_openai


settings = Settings()
