"""환경 변수 및 애플리케이션 전역 설정 (Pydantic v2 Settings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

STATUSES: list[str] = ["할당", "진행중", "이슈 발생", "완료"]

# 칸반 이동 시 자동 보정할 상태만 넣는다. "이슈 발생"은 기존 진행률을 유지한다.
STATUS_DEFAULT_PROGRESS: dict[str, int] = {
    "할당": 0,
    "진행중": 50,
    "완료": 100,
}

ROLES: list[str] = ["ADMIN", "LEADER", "MEMBER"]

# --------------------------------------------------------------------------- #
# AI 프로바이더 메타데이터
#   settings 탭에서 OpenAI · Anthropic · Google 중 하나를 골라 연동한다.
#   price 는 1M 토큰당 USD 기준 추정 단가 (사용량 화면의 예상 비용 계산용).
# --------------------------------------------------------------------------- #
AI_PROVIDERS: dict[str, dict] = {
    "openai": {
        "label": "OpenAI",
        "description": "GPT-4o 계열 · Whisper 음성 전사까지 단일 키로 지원",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
        "default_model": "gpt-4o",
        "supports_stt": True,
        "key_hint": "sk-...",
        "console_url": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "description": "Claude Sonnet 계열 · 긴 회의록 요약에 강점",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ],
        "default_model": "claude-3-5-sonnet-latest",
        "supports_stt": False,
        "key_hint": "sk-ant-...",
        "console_url": "https://console.anthropic.com/settings/keys",
    },
    "google": {
        "label": "Google Gemini",
        "description": "Gemini Flash 계열 · 오디오 입력으로 음성 전사까지 지원",
        # 무료 등급 키로도 호출되는 모델 위주. pro 계열은 유료 등급이라야 쿼터가 열린다.
        "models": [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-3.1-pro-preview",
            "gemini-pro-latest",
        ],
        "default_model": "gemini-3.5-flash",
        "supports_stt": True,
        "key_hint": "AIza...",
        "console_url": "https://aistudio.google.com/app/apikey",
    },
}

# 1M 토큰당 USD 추정 단가 (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-3-7-sonnet-latest": (3.00, 15.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "gemini-3.6-flash": (0.40, 2.50),
    "gemini-3.5-flash": (0.30, 2.50),
    "gemini-3.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-flash-latest": (0.30, 2.50),
    "gemini-3.1-pro-preview": (1.25, 10.00),
    "gemini-pro-latest": (1.25, 10.00),
}

DEFAULT_PRICING: tuple[float, float] = (1.00, 3.00)

# 앱이 받는 음성 업로드 한도. Whisper 자체는 25MB 이지만 Gemini Files API 는
# 그보다 큰 회의 녹음을 처리할 수 있다 (압축 m4a/mp3 기준 수 시간).
MAX_AUDIO_MB = 200
MAX_AUDIO_BYTES = MAX_AUDIO_MB * 1024 * 1024
WHISPER_AUDIO_BYTES = 25 * 1024 * 1024

# --------------------------------------------------------------------------- #
# Microsoft Graph (Outlook / Microsoft 365 캘린더 · 메일)
#   위임(delegated) 권한으로 각 구성원이 자기 계정을 연결한다.
#   Calendars.ReadWrite 는 읽기를 포함하며 일정 생성에 필요하다.
#   Mail.Send 는 연결된 계정으로 메일 발송에 필요하다.
#   테넌트 정책에 따라 관리자 동의가 한 번 필요할 수 있다.
# --------------------------------------------------------------------------- #
MS_SCOPES: list[str] = [
    "openid",
    "profile",
    "offline_access",
    "User.Read",
    "Calendars.ReadWrite",
    "Mail.Send",
]
MS_AUTHORITY = "https://login.microsoftonline.com"
MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MS_TIMEZONE = "Asia/Seoul"


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """모델별 추정 단가로 호출 비용(USD)을 계산한다."""
    price_in, price_out = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return round(
        (prompt_tokens / 1_000_000) * price_in + (completion_tokens / 1_000_000) * price_out, 6
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "AL Note API"
    database_url: str = f"sqlite:///{BASE_DIR / 'ainote.db'}"

    # Auth
    jwt_secret: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12
    remember_token_expire_days: int = 14
    encryption_key: str = ""

    # CORS
    # 3000 포트가 점유된 경우 Next.js 가 3001 로 뜨므로 함께 허용한다.
    cors_origins: str = (
        "https://localhost:3001,https://127.0.0.1:3001,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # AI — .env 값은 초기 기본값이며, 설정 화면에서 저장한 값(DB)이 우선한다.
    openai_api_key: str = ""
    openai_text_model: str = "gpt-4o"
    openai_stt_model: str = "whisper-1"
    anthropic_api_key: str = ""
    google_api_key: str = ""
    allow_mock_ai: bool = Field(
        default=True, description="API 키가 없을 때 목업 응답으로 동작"
    )

    # Microsoft Graph — 사용자별 캘린더 연동용 Azure AD 앱.
    # .env 값은 초기 기본값이며, 설정 화면(ADMIN)에서 저장한 값(DB)이 우선한다.
    ms_client_id: str = ""
    ms_client_secret: str = ""
    ms_tenant_id: str = "common"
    ms_redirect_uri: str = "https://localhost:3001/api/calendar/callback"
    # 다른 PC에서 접속할 때 쓸 공개 주소. 비우면 서버 LAN IP 를 자동으로 쓴다.
    public_base_url: str = ""
    # OAuth 콜백 처리 후 사용자를 돌려보낼 프런트엔드 주소 (localhost 전용 폴백)
    frontend_url: str = "https://localhost:3001"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    def env_key(self, provider: str) -> str:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
        }.get(provider, "")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
