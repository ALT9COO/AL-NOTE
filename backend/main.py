"""FastAPI 엔트리포인트 — CORS, 예외 핸들러, 라우터 등록."""

from __future__ import annotations

import logging
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai_engine import AIEngineError, ai_status
from config import STATUSES, settings
from database import SessionLocal, init_db
from routers import (
    admin_router,
    auth_router,
    calendar_router,
    meeting_router,
    task_router,
)

_SECRET_RE = re.compile(
    r"(key=)[^&\s]+|(Authorization:\s*Bearer\s+)\S+|((?:api[_-]?key|token|secret)=)[^&\s]+",
    re.IGNORECASE,
)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        redacted = _SECRET_RE.sub(lambda m: (m.group(1) or m.group(2) or m.group(3) or "") + "***", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger().addFilter(_RedactFilter())
# passlib 1.7.4 는 bcrypt>=4.1 의 버전 조회에 실패하며 경고를 남긴다 (동작에는 영향 없음).
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)
logger = logging.getLogger("ainote")

_AI_STATUS_TTL = 20.0
_ai_status_cache: tuple[float, dict] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("DB 초기화 완료")
    if settings.jwt_secret.startswith("change-me"):
        logger.warning("JWT_SECRET 이 기본값입니다. backend/.env 에서 긴 무작위 문자열로 바꾸세요.")
    if not settings.has_openai:
        logger.warning("OPENAI_API_KEY 미설정 — AI 기능은 데모(mock) 응답으로 동작합니다.")
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="업무 관리 · AI 회의 요약 · 자동 진행률 업데이트 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|(\d{1,3}\.){3}\d{1,3})(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AIEngineError)
async def ai_engine_error_handler(request: Request, exc: AIEngineError) -> JSONResponse:
    logger.error("AI 엔진 오류: %s", exc)
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "요청 형식이 올바르지 않습니다.", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("처리되지 않은 오류: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "서버 내부 오류가 발생했습니다."},
    )


app.include_router(auth_router.router)
app.include_router(task_router.router)
app.include_router(task_router.analytics_router)
app.include_router(meeting_router.router)
app.include_router(admin_router.router)
app.include_router(calendar_router.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    global _ai_status_cache
    now = time.monotonic()
    cached = _ai_status_cache
    if cached is None or now - cached[0] > _AI_STATUS_TTL:
        with SessionLocal() as db:
            _ai_status_cache = (now, ai_status(db))
        cached = _ai_status_cache
    return {"status": "ok", "statuses": STATUSES, "ai": cached[1]}
