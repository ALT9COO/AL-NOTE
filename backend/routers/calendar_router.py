"""Microsoft 365 캘린더 연동 — 사용자별 OAuth 연결 · 일정 조회 · (ADMIN) Azure 앱 설정.

일정/토큰 관련 엔드포인트는 모두 '본인 것만' 다룬다. 관리자라도 남의 캘린더는 볼 수 없다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

import calendar_service as cal
from auth import CurrentUser, DbSession, require_roles, visible_meetings, visible_users
from config import MS_SCOPES, settings
from database import CalendarApp, CalendarConnection, User
from secret_box import seal
from schemas import (
    CalendarAppOut,
    CalendarAppUpdate,
    CalendarConnectionOut,
    CalendarEventCreate,
    CalendarEventCreated,
    CalendarEventOut,
    CalendarEventsResponse,
    CalendarLoginUrl,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

AdminUser = Depends(require_roles("ADMIN"))
STATE_TTL_MINUTES = 10


# --------------------------------------------------------------------------- #
# 공통 헬퍼
# --------------------------------------------------------------------------- #
def _mask_secret(value: str) -> str:
    if not value:
        return ""
    return f"{value[:3]}{'•' * 8}{value[-3:]}" if len(value) > 8 else "•" * len(value)


def _connection_out(row: CalendarConnection | None, app: cal.GraphApp) -> CalendarConnectionOut:
    if row is None or not row.refresh_token:
        return CalendarConnectionOut(connected=False, app_configured=app.configured)
    missing = cal.missing_graph_scopes(row)
    have = cal.granted_scopes(row.scopes)
    return CalendarConnectionOut(
        connected=True,
        app_configured=app.configured,
        provider=row.provider,
        account_name=row.account_name,
        account_email=row.account_email,
        needs_reauth=row.needs_reauth,
        connected_at=row.created_at,
        last_synced_at=row.last_synced_at,
        last_sync_ok=row.last_sync_ok,
        last_sync_message=row.last_sync_message or "",
        event_count=row.event_count,
        can_write=cal.WRITE_SCOPE in have,
        can_mail=cal.MAIL_SCOPE in have,
        missing_scopes=missing,
    )


def _require_connection(user: CurrentUser, db: DbSession) -> tuple[CalendarConnection, cal.GraphApp]:
    app = cal.app_config(db)
    row = db.get(CalendarConnection, user.user_id)
    if row is None or not row.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="연결된 Microsoft 계정이 없습니다. 회의실에서 Outlook을 연결하세요.",
        )
    return row, app


def _sign_state(user_id: str, redirect_uri: str, frontend_origin: str) -> str:
    payload = {
        "sub": user_id,
        "purpose": "ms-calendar",
        "redirect_uri": redirect_uri,
        "frontend_origin": frontend_origin,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _read_state(state: str) -> dict[str, str]:
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise cal.CalendarError("인증 요청이 만료되었습니다. 다시 시도하세요.") from exc
    if payload.get("purpose") != "ms-calendar" or not payload.get("sub"):
        raise cal.CalendarError("잘못된 인증 요청입니다.")
    user_id = str(payload["sub"])
    redirect_uri = str(payload.get("redirect_uri") or "")
    frontend_origin = str(payload.get("frontend_origin") or "")
    if redirect_uri and not frontend_origin:
        frontend_origin = cal.frontend_origin_from_redirect(redirect_uri)
    return {
        "user_id": user_id,
        "redirect_uri": redirect_uri,
        "frontend_origin": frontend_origin,
    }


def _browser_origin(request: Request) -> str:
    """브라우저가 연 공개 주소. Next 프록시의 Host(127.0.0.1) 는 쓰지 않는다."""
    found: list[str] = []

    def add(value: str | None) -> None:
        origin = cal.origin_from_value((value or "").strip())
        host = urlparse(origin).hostname if origin else None
        if origin and origin not in found and not cal.is_unusable_host(host):
            found.append(origin)

    add(request.headers.get("x-alnote-origin"))
    add(request.headers.get("origin"))
    referer = (request.headers.get("referer") or "").strip()
    referer_origin = cal.origin_from_value(referer)
    if referer_origin:
        host = urlparse(referer_origin).hostname or ""
        if "microsoftonline.com" not in host and "live.com" not in host:
            add(referer_origin)
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if host and proto in ("http", "https"):
        add(f"{proto}://{host}")

    lan = [item for item in found if not cal.is_loopback_host(urlparse(item).hostname)]
    return (lan or found or [""])[0]


def _front_redirect(
    status_value: str,
    message: str = "",
    *,
    frontend_origin: str | None = None,
) -> RedirectResponse:
    raw = (frontend_origin or "").strip().rstrip("/")
    host = urlparse(raw).hostname if raw else None
    if not raw or cal.is_loopback_host(host) or cal.is_unusable_host(host):
        raw = cal.canonical_public_origin()
    query = urlencode({"calendar": status_value, **({"msg": message} if message else {})})
    return RedirectResponse(f"{raw}/meetings?{query}")


# --------------------------------------------------------------------------- #
# 내 연결 상태
# --------------------------------------------------------------------------- #
@router.get("/connection", response_model=CalendarConnectionOut)
def get_connection(user: CurrentUser, db: DbSession) -> CalendarConnectionOut:
    return _connection_out(db.get(CalendarConnection, user.user_id), cal.app_config(db))


@router.get("/login-url", response_model=CalendarLoginUrl)
def login_url(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    redirect_uri: str | None = Query(default=None, max_length=300),
    origin: str | None = Query(default=None, max_length=300),
) -> CalendarLoginUrl:
    """Microsoft 로그인 페이지 주소를 만들어 준다 (프런트에서 이 주소로 이동)."""
    app = cal.app_config(db)
    if not app.configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Azure 앱이 아직 등록되지 않았습니다. 설정 → 캘린더 연동에서 클라이언트 ID·시크릿을 입력하세요.",
        )
    try:
        resolved_redirect = cal.pick_redirect_uri(
            redirect_uri,
            origin,
            _browser_origin(request),
            fallback=cal.canonical_public_origin(),
        )
    except cal.CalendarError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    frontend_origin = cal.frontend_origin_from_redirect(resolved_redirect)
    existing = db.get(CalendarConnection, user.user_id)
    missing = cal.missing_graph_scopes(existing) if existing and existing.refresh_token else []
    url = cal.build_auth_url(
        app,
        _sign_state(user.user_id, resolved_redirect, frontend_origin),
        redirect_uri=resolved_redirect,
        login_hint=existing.account_email if existing else "",
        prompt="consent" if missing else "select_account",
    )
    print(f"[calendar] OAuth redirect_uri={resolved_redirect} origin={frontend_origin}")
    return CalendarLoginUrl(url=url, expires_in=STATE_TTL_MINUTES * 60)


@router.get("/callback", include_in_schema=False)
def oauth_callback(
    request: Request,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """Microsoft 로그인 후 돌아오는 지점. 토큰을 저장하고 회의실 화면으로 되돌려 보낸다."""
    browser_origin = _browser_origin(request)
    if error:
        try:
            dest = cal.pick_redirect_uri(browser_origin, fallback=settings.frontend_url)
            dest = cal.frontend_origin_from_redirect(dest)
        except cal.CalendarError:
            dest = browser_origin or settings.frontend_url
        return _front_redirect("error", error_description or error, frontend_origin=dest)
    if not code or not state:
        dest = browser_origin or settings.frontend_url
        return _front_redirect("error", "인증 응답이 올바르지 않습니다.", frontend_origin=dest)

    try:
        state_data = _read_state(state)
        user_id = state_data["user_id"]
        resolved_redirect = state_data["redirect_uri"] or settings.ms_redirect_uri
        frontend_origin = cal.frontend_origin_from_redirect(
            cal.pick_redirect_uri(
                browser_origin,
                state_data["frontend_origin"],
                resolved_redirect,
                fallback=cal.canonical_public_origin(),
            )
        )
    except cal.CalendarError as exc:
        dest = browser_origin or settings.frontend_url
        return _front_redirect("error", str(exc), frontend_origin=dest)

    user = db.get(User, user_id)
    if user is None:
        return _front_redirect("error", "사용자를 찾을 수 없습니다.", frontend_origin=frontend_origin)

    app = cal.app_config(db)
    try:
        tokens = cal.exchange_code(app, code, redirect_uri=resolved_redirect)
        profile = cal.fetch_profile(tokens.get("access_token", ""))
    except cal.CalendarError as exc:
        return _front_redirect("error", str(exc), frontend_origin=frontend_origin)

    row = db.get(CalendarConnection, user_id) or CalendarConnection(user_id=user_id)
    row.provider = "msgraph"
    row.account_name = profile["name"]
    row.account_email = profile["email"]
    cal.apply_tokens(row, tokens)
    row.last_synced_at = datetime.now()
    row.last_sync_ok = True
    row.last_sync_message = "계정을 연결했습니다."
    db.add(row)
    db.commit()

    return _front_redirect("connected", profile["email"], frontend_origin=frontend_origin)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(user: CurrentUser, db: DbSession) -> None:
    row = db.get(CalendarConnection, user.user_id)
    if row is not None:
        db.delete(row)
        db.commit()


@router.post("/sync", response_model=CalendarConnectionOut)
def sync_connection(user: CurrentUser, db: DbSession) -> CalendarConnectionOut:
    app = cal.app_config(db)
    row = db.get(CalendarConnection, user.user_id)
    if row is None or not row.refresh_token:
        raise HTTPException(status_code=404, detail="연결된 Microsoft 계정이 없습니다.")

    try:
        token = cal.ensure_access_token(db, row, app)
        events = cal.fetch_events(token, days_back=1, days_ahead=30)
        row.last_sync_ok = True
        row.last_sync_message = f"일정 {len(events)}건을 동기화했습니다."
        row.event_count = len(events)
    except cal.ReauthRequired as exc:
        row.needs_reauth = True
        row.last_sync_ok = False
        row.last_sync_message = str(exc)
    except cal.CalendarError as exc:
        row.last_sync_ok = False
        row.last_sync_message = str(exc)
    row.last_synced_at = datetime.now()
    db.commit()
    return _connection_out(row, app)


# --------------------------------------------------------------------------- #
# 일정 조회
# --------------------------------------------------------------------------- #
@router.get("/events", response_model=CalendarEventsResponse)
def list_events(
    user: CurrentUser,
    db: DbSession,
    days_back: int = Query(default=1, ge=0, le=180),
    days_ahead: int = Query(default=14, ge=1, le=90),
    sample: bool = Query(default=False, description="연동 전 미리보기용 샘플 일정"),
) -> CalendarEventsResponse:
    app = cal.app_config(db)
    row = db.get(CalendarConnection, user.user_id)
    today = date.today()
    window = (today - timedelta(days=days_back), today + timedelta(days=days_ahead))

    if sample:
        raw_events = cal.sample_events()
    elif row is None or not row.refresh_token:
        return CalendarEventsResponse(
            connection=_connection_out(row, app),
            range_start=window[0],
            range_end=window[1],
            events=[],
        )
    else:
        try:
            token = cal.ensure_access_token(db, row, app)
            raw_events = cal.fetch_events(token, days_back=days_back, days_ahead=days_ahead)
        except cal.ReauthRequired as exc:
            row.needs_reauth = True
            row.last_sync_ok = False
            row.last_sync_message = str(exc)
            row.last_synced_at = datetime.now()
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        except cal.CalendarError as exc:
            row.last_sync_ok = False
            row.last_sync_message = str(exc)
            row.last_synced_at = datetime.now()
            db.commit()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        row.last_sync_ok = True
        row.last_sync_message = f"일정 {len(raw_events)}건"
        row.last_synced_at = datetime.now()
        row.event_count = len(raw_events)
        db.commit()

    members = visible_users(db, user)
    keys = {item["event_key"] for item in raw_events}
    # 열람 권한이 있는 회의록만 '저장됨' 으로 표시한다.
    saved = {m.event_key: m for m in visible_meetings(db, user) if m.event_key in keys}

    events = [
        CalendarEventOut(
            **item,
            matched_user_ids=cal.match_internal_users(
                item["attendees"], item["organizer"], members
            ),
            meeting_id=saved[item["event_key"]].meeting_id if item["event_key"] in saved else None,
            meeting_title=saved[item["event_key"]].title if item["event_key"] in saved else None,
        )
        for item in raw_events
    ]

    return CalendarEventsResponse(
        connection=_connection_out(row, app),
        range_start=window[0],
        range_end=window[1],
        events=events,
        sample=sample,
    )


@router.post("/events", response_model=CalendarEventCreated)
def create_event(
    payload: CalendarEventCreate, user: CurrentUser, db: DbSession
) -> CalendarEventCreated:
    """연결된 본인 Outlook 캘린더에 일정을 만든다. 남의 캘린더에는 쓰지 않는다."""
    row, app = _require_connection(user, db)
    if cal.WRITE_SCOPE in cal.missing_graph_scopes(row):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="캘린더 쓰기 권한이 없습니다. Microsoft 계정을 다시 연결해 Calendars.ReadWrite 동의를 받으세요.",
        )
    try:
        token = cal.ensure_access_token(db, row, app)
        created = cal.create_event(
            token,
            title=payload.title,
            start=payload.start,
            end=payload.end,
            location=payload.location,
            body=payload.body,
            attendees=[item.model_dump() for item in payload.attendees],
        )
    except cal.ReauthRequired as exc:
        row.needs_reauth = True
        row.last_sync_ok = False
        row.last_sync_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except cal.CalendarError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return CalendarEventCreated(**created)


# --------------------------------------------------------------------------- #
# Azure 앱 설정 (ADMIN)
# --------------------------------------------------------------------------- #
def _app_out(db) -> CalendarAppOut:
    row = db.get(CalendarApp, 1)
    app = cal.app_config(db)
    return CalendarAppOut(
        configured=app.configured,
        source=app.source,
        client_id=app.client_id,
        tenant_id=app.tenant_id,
        redirect_uri=app.redirect_uri,
        suggested_redirect_uris=cal.suggested_redirect_uris(app),
        client_secret_masked=_mask_secret(app.client_secret),
        scopes=MS_SCOPES,
        updated_by=row.updated_by if row else None,
        updated_at=row.updated_at if row else None,
    )


@router.get("/app", response_model=CalendarAppOut)
def get_app(db: DbSession, _: User = AdminUser) -> CalendarAppOut:
    return _app_out(db)


@router.put("/app", response_model=CalendarAppOut)
def save_app(payload: CalendarAppUpdate, db: DbSession, admin: User = AdminUser) -> CalendarAppOut:
    row = db.get(CalendarApp, 1) or CalendarApp(app_id=1)
    row.client_id = payload.client_id.strip()
    row.tenant_id = payload.tenant_id.strip() or "common"
    row.redirect_uri = payload.redirect_uri.strip() or settings.ms_redirect_uri
    # 빈 문자열은 '변경 없음', 공백 하나는 '삭제' 로 취급한다.
    if payload.client_secret:
        row.client_secret = "" if payload.client_secret.isspace() else seal(payload.client_secret.strip())
    row.updated_by = admin.user_id
    db.add(row)
    db.commit()
    return _app_out(db)


@router.delete("/app", status_code=status.HTTP_204_NO_CONTENT)
def delete_app(db: DbSession, _: User = AdminUser) -> None:
    """앱 등록 정보를 지우고 모든 사용자의 연결을 해제한다."""
    row = db.get(CalendarApp, 1)
    if row is not None:
        db.delete(row)
    for conn in db.query(CalendarConnection).all():
        db.delete(conn)
    db.commit()
