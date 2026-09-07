"""Microsoft Graph 캘린더 연동 — OAuth 토큰 교환/갱신, 일정 조회·생성, 메일 발송.

각 구성원이 자기 Microsoft 365 계정을 연결(위임 권한)하면 그 사용자의 캘린더를 읽고
일정을 만들며, 연결된 계정으로 메일을 보낼 수 있다.
조직 공통으로 Azure AD 앱 등록 1건(클라이언트 ID·시크릿)이 필요하며, 그 값은 ADMIN 이
설정 화면에서 입력하거나 backend/.env 로 넣는다.
"""

from __future__ import annotations

import html as html_lib
import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse, urlencode

import httpx

from config import MS_AUTHORITY, MS_GRAPH_BASE, MS_SCOPES, MS_TIMEZONE, settings
from database import CalendarApp, CalendarConnection
from secret_box import reveal, seal

HTTP_TIMEOUT = 20.0
MAX_EVENTS = 400
# 만료 직전 토큰은 미리 갱신한다.
REFRESH_MARGIN = timedelta(minutes=5)
WRITE_SCOPE = "Calendars.ReadWrite"
MAIL_SCOPE = "Mail.Send"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CALLBACK_PATH = "/api/calendar/callback"
DEFAULT_HTTPS_PORT = 3001


class CalendarError(RuntimeError):
    """캘린더 연동 실패 (라우터에서 400/502 로 변환)."""


class ReauthRequired(CalendarError):
    """리프레시 토큰이 만료·폐기됨 — 사용자가 다시 로그인해야 한다."""


# --------------------------------------------------------------------------- #
# Azure 앱 설정
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class GraphApp:
    client_id: str
    client_secret: str
    tenant_id: str
    redirect_uri: str
    source: str  # db · env · none

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    @property
    def authority(self) -> str:
        return f"{MS_AUTHORITY}/{self.tenant_id or 'common'}"

    @property
    def token_url(self) -> str:
        return f"{self.authority}/oauth2/v2.0/token"

    @property
    def authorize_url(self) -> str:
        return f"{self.authority}/oauth2/v2.0/authorize"


def _lan_ipv4_addresses() -> list[str]:
    found: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith(("127.", "169.254.", "0.")):
                continue
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def _local_hostnames() -> set[str]:
    names = {"localhost", "al-note.local"}
    try:
        names.add(socket.gethostname().lower())
    except OSError:
        pass
    try:
        fqdn = socket.getfqdn().lower().rstrip(".")
        if fqdn:
            names.add(fqdn)
            names.add(fqdn.split(".")[0])
    except OSError:
        pass
    return {item for item in names if item}


def is_allowed_redirect_uri(uri: str) -> bool:
    """사내 LAN·localhost 접속만 OAuth 리디렉션으로 허용한다."""
    parsed = urlparse((uri or "").strip())
    if parsed.scheme not in ("https", "http"):
        return False
    if parsed.path.rstrip("/") != CALLBACK_PATH:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in _local_hostnames() or host.endswith(".local") or host.endswith(".lan"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_unspecified or ip.is_multicast:
        return False
    return ip.is_private or ip.is_loopback


def normalize_redirect_uri(uri: str) -> str:
    """비-localhost 는 HTTPS 로 맞춘다. Azure 가 IP+HTTP 조합을 거절하기 때문이다."""
    parsed = urlparse((uri or "").strip())
    host = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "https").lower()
    if host not in ("localhost", "127.0.0.1") and scheme == "http":
        scheme = "https"
    port = parsed.port
    netloc = f"{host}:{port}" if port else host
    return f"{scheme}://{netloc}{CALLBACK_PATH}"


def is_loopback_host(host: str | None) -> bool:
    name = (host or "").lower().split("%")[0].strip("[]")
    if ":" in name and not name.replace(":", "").isdigit():
        name = name.split(":")[0]
    if name in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def is_unusable_host(host: str | None) -> bool:
    """브라우저가 열 수 없는 주소 (0.0.0.0 등 바인드 전용)."""
    name = (host or "").lower().split("%")[0].strip("[]")
    if ":" in name and not name.replace(":", "").isdigit():
        name = name.split(":")[0]
    if name in ("0.0.0.0", "::", ""):
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return ip.is_unspecified or ip.is_multicast


def origin_from_value(value: str | None) -> str:
    parsed = urlparse((value or "").strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def callback_uri_from_origin(origin: str | None) -> str:
    base = origin_from_value(origin) or (origin or "").rstrip("/")
    if not base:
        return ""
    if base.endswith(CALLBACK_PATH):
        return normalize_redirect_uri(base)
    return normalize_redirect_uri(f"{base}{CALLBACK_PATH}")


def frontend_origin_from_redirect(redirect_uri: str) -> str:
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    default_port = 443 if parsed.scheme == "https" else 80
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    if port == default_port:
        return f"{parsed.scheme}://{host_part}"
    return f"{parsed.scheme}://{host_part}:{port}"


def canonical_public_origin() -> str:
    """다른 PC가 쓰는 사내 주소. localhost/0.0.0.0 은 쓰지 않는다."""
    configured = (settings.public_base_url or "").strip().rstrip("/")
    if configured:
        host = urlparse(configured if "://" in configured else f"https://{configured}").hostname
        if host and not is_loopback_host(host) and not is_unusable_host(host):
            if "://" not in configured:
                return f"https://{configured}"
            return configured
    ips = _lan_ipv4_addresses()
    if ips:
        return f"https://{ips[0]}:{DEFAULT_HTTPS_PORT}"
    return settings.frontend_url.rstrip("/")


def pick_redirect_uri(*candidates: str | None, fallback: str = "") -> str:
    """LAN 주소를 localhost 보다 우선한다. 오리진·콜백 URI 모두 받는다."""
    allowed: list[str] = []
    extra_fallback = fallback
    if not extra_fallback:
        extra_fallback = canonical_public_origin()
    for candidate in [*candidates, extra_fallback, canonical_public_origin()]:
        raw = (candidate or "").strip()
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc and parsed.path.rstrip("/") in ("",):
            raw = f"{parsed.scheme}://{parsed.netloc}{CALLBACK_PATH}"
        try:
            normalized = normalize_redirect_uri(raw)
        except Exception:
            continue
        if is_allowed_redirect_uri(normalized) and normalized not in allowed:
            if not is_unusable_host(urlparse(normalized).hostname):
                allowed.append(normalized)
    lan = [
        item
        for item in allowed
        if not is_loopback_host(urlparse(item).hostname) and not is_unusable_host(urlparse(item).hostname)
    ]
    chosen = lan or allowed
    if not chosen:
        raise CalendarError(
            "리디렉션 URI 가 올바르지 않습니다. "
            f"주소창의 주소가 https://<서버IP>:{DEFAULT_HTTPS_PORT} 인지 확인하세요."
        )
    return chosen[0]


def suggested_redirect_uris(app: GraphApp) -> list[str]:
    """Azure 앱 등록에 넣을 URI 후보 목록."""
    hosts = ["localhost", "127.0.0.1", *_lan_ipv4_addresses(), *sorted(_local_hostnames())]
    uris = {f"https://{host}:{DEFAULT_HTTPS_PORT}{CALLBACK_PATH}" for host in hosts if host}
    if app.redirect_uri and is_allowed_redirect_uri(app.redirect_uri):
        uris.add(normalize_redirect_uri(app.redirect_uri))
    return sorted(uris)


def app_config(db=None) -> GraphApp:
    """DB 에 저장된 앱 등록 정보를 우선 사용하고, 없으면 .env 값으로 떨어진다."""
    row: CalendarApp | None = db.get(CalendarApp, 1) if db is not None else None
    if row is not None and row.client_id and row.client_secret:
        return GraphApp(
            client_id=row.client_id,
            client_secret=reveal(row.client_secret),
            tenant_id=row.tenant_id or "common",
            redirect_uri=row.redirect_uri or settings.ms_redirect_uri,
            source="db",
        )

    if settings.ms_client_id and settings.ms_client_secret:
        return GraphApp(
            client_id=settings.ms_client_id,
            client_secret=settings.ms_client_secret,
            tenant_id=settings.ms_tenant_id or "common",
            redirect_uri=settings.ms_redirect_uri,
            source="env",
        )

    return GraphApp(
        client_id=row.client_id if row else "",
        client_secret="",
        tenant_id=(row.tenant_id if row else "") or settings.ms_tenant_id or "common",
        redirect_uri=(row.redirect_uri if row else "") or settings.ms_redirect_uri,
        source="none",
    )


# --------------------------------------------------------------------------- #
# OAuth
# --------------------------------------------------------------------------- #
def granted_scopes(raw: str) -> set[str]:
    """토큰 응답의 scope 문자열을 짧은 권한 이름 집합으로 정규화한다."""
    names: set[str] = set()
    for part in (raw or "").split():
        names.add(part.rsplit("/", 1)[-1])
    return names


def missing_graph_scopes(conn: CalendarConnection | None) -> list[str]:
    have = granted_scopes(conn.scopes if conn else "")
    return [name for name in (WRITE_SCOPE, MAIL_SCOPE) if name not in have]


def build_auth_url(
    app: GraphApp,
    state: str,
    *,
    redirect_uri: str | None = None,
    login_hint: str = "",
    prompt: str = "select_account",
) -> str:
    resolved = redirect_uri or app.redirect_uri
    params = {
        "client_id": app.client_id,
        "response_type": "code",
        "redirect_uri": resolved,
        "response_mode": "query",
        "scope": " ".join(MS_SCOPES),
        "state": state,
        # 이미 동의한 사용자도 계정을 고를 수 있게 한다. 권한 추가 시에는 consent.
        "prompt": prompt or "select_account",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{app.authorize_url}?{urlencode(params)}"


# Azure 가 돌려주는 대표적인 실패 코드는 원인이 분명해서 한국어 조치 안내로 바꿔 준다.
AADSTS_HINTS: list[tuple[str, str]] = [
    (
        "AADSTS7000215",
        "클라이언트 비밀이 올바르지 않습니다. Azure → 인증서 및 비밀에서 '값(Value)' 열을 복사해야 합니다. "
        "'비밀 ID' 를 넣으면 이 오류가 납니다. 값은 생성 직후에만 볼 수 있으니, 못 봤다면 새 비밀을 만드세요.",
    ),
    (
        "AADSTS7000222",
        "클라이언트 비밀이 만료되었습니다. Azure → 인증서 및 비밀에서 새 비밀을 만들어 다시 저장하세요.",
    ),
    (
        "AADSTS50011",
        "리디렉션 URI 가 일치하지 않습니다. Azure 앱 등록의 '웹' 플랫폼에 설정 화면의 리디렉션 URI 를 "
        "문자 그대로 똑같이 등록하세요.",
    ),
    (
        "AADSTS700016",
        "클라이언트 ID 를 이 테넌트에서 찾을 수 없습니다. 애플리케이션(클라이언트) ID 와 테넌트 ID 를 확인하세요.",
    ),
    (
        "AADSTS900023",
        "테넌트 ID 가 올바르지 않습니다. 디렉터리(테넌트) ID 또는 common 을 입력하세요.",
    ),
    (
        "AADSTS65001",
        "관리자 동의가 필요합니다. Azure → API 사용 권한에서 'OO에 대한 관리자 동의 허용' 을 눌러 주세요.",
    ),
]


def _friendly_error(code: str, description: str) -> str:
    for marker, hint in AADSTS_HINTS:
        if marker in description or marker in code:
            return hint
    return f"토큰 발급 실패 ({code}): {description}"


def _token_request(app: GraphApp, data: dict[str, str], *, redirect_uri: str | None = None) -> dict[str, Any]:
    payload = {
        "client_id": app.client_id,
        "client_secret": app.client_secret,
        "redirect_uri": redirect_uri or app.redirect_uri,
        "scope": " ".join(MS_SCOPES),
        **data,
    }
    try:
        response = httpx.post(app.token_url, data=payload, timeout=HTTP_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        raise CalendarError(f"Microsoft 인증 서버에 연결하지 못했습니다: {exc}") from exc

    body = response.json() if response.content else {}
    if response.status_code >= 400:
        code = body.get("error", "")
        description = (body.get("error_description") or "").split("\r\n")[0]
        if code in ("invalid_grant", "interaction_required", "consent_required"):
            raise ReauthRequired(f"다시 로그인해야 합니다: {description or code}")
        raise CalendarError(_friendly_error(code, description or response.text[:200]))
    return body


def exchange_code(app: GraphApp, code: str, *, redirect_uri: str | None = None) -> dict[str, Any]:
    return _token_request(
        app, {"grant_type": "authorization_code", "code": code}, redirect_uri=redirect_uri
    )


def refresh_tokens(app: GraphApp, refresh_token: str) -> dict[str, Any]:
    return _token_request(
        app, {"grant_type": "refresh_token", "refresh_token": refresh_token}
    )


def apply_tokens(conn: CalendarConnection, tokens: dict[str, Any]) -> None:
    conn.access_token = seal(tokens.get("access_token", ""))
    # 리프레시 토큰은 회전될 수 있으나, 응답에 없으면 기존 값을 유지한다.
    if tokens.get("refresh_token"):
        conn.refresh_token = seal(tokens["refresh_token"])
    conn.token_expires_at = datetime.now() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    conn.scopes = tokens.get("scope", "")
    conn.needs_reauth = False


def ensure_access_token(db, conn: CalendarConnection, app: GraphApp) -> str:
    """만료가 임박했으면 갱신한 뒤 유효한 액세스 토큰을 돌려준다."""
    access = reveal(conn.access_token)
    refresh = reveal(conn.refresh_token)
    if not refresh and not access:
        raise ReauthRequired("연결된 Microsoft 계정이 없습니다.")

    expires_at = conn.token_expires_at or datetime.min
    if access and expires_at - REFRESH_MARGIN > datetime.now():
        return access

    try:
        tokens = refresh_tokens(app, refresh)
    except ReauthRequired:
        conn.needs_reauth = True
        conn.last_sync_ok = False
        conn.last_sync_message = "Microsoft 계정 재연결이 필요합니다."
        db.commit()
        raise

    apply_tokens(conn, tokens)
    db.commit()
    return reveal(conn.access_token)


# --------------------------------------------------------------------------- #
# Graph 호출
# --------------------------------------------------------------------------- #
def _graph_request(
    method: str,
    access_token: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict:
    try:
        response = httpx.request(
            method,
            f"{MS_GRAPH_BASE}{path}",
            params=params,
            json=json_body,
            timeout=HTTP_TIMEOUT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": f'outlook.timezone="{MS_TIMEZONE}"',
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise CalendarError(f"Microsoft Graph 호출 실패: {exc}") from exc

    if response.status_code == 401:
        raise ReauthRequired("Microsoft 계정 인증이 만료되었습니다. 다시 연결하세요.")
    if response.status_code == 403:
        if "sendMail" in path:
            raise CalendarError(
                "메일 보내기 권한이 없습니다. Azure 앱에 Mail.Send 를 추가하고 "
                "Microsoft 계정을 다시 연결하세요."
            )
        if method.upper() != "GET":
            raise CalendarError(
                "캘린더 쓰기 권한이 없습니다. Azure 앱에 Calendars.ReadWrite 를 추가하고 "
                "Microsoft 계정을 다시 연결하세요."
            )
        raise CalendarError(
            "캘린더 읽기 권한이 없습니다. Azure 앱에 Calendars.ReadWrite 권한이 있는지 확인하세요."
        )
    if response.status_code >= 400:
        detail = ""
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            detail = response.text[:200]
        raise CalendarError(f"Graph 응답 오류 ({response.status_code}): {detail}")
    if not response.content:
        return {}
    try:
        return response.json()
    except Exception:  # noqa: BLE001
        return {}


def _graph_get(access_token: str, path: str, params: dict[str, Any] | None = None) -> dict:
    return _graph_request("GET", access_token, path, params=params)


def _graph_post(access_token: str, path: str, json_body: dict[str, Any]) -> dict:
    return _graph_request("POST", access_token, path, json_body=json_body)


def _graph_datetime(value: datetime) -> dict[str, str]:
    naive = value.replace(tzinfo=None)
    return {"dateTime": naive.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": MS_TIMEZONE}


def markdown_to_html(md: str) -> str:
    """가벼운 마크다운 → HTML 변환 (리포트 메일용). 외부 패키지에 의존하지 않는다."""
    escaped = html_lib.escape(md or "")
    lines: list[str] = []
    in_list = False
    for line in escaped.splitlines():
        if line.startswith("- "):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{line[2:]}</li>")
            continue
        if in_list:
            lines.append("</ul>")
            in_list = False
        if line.startswith("### "):
            lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            lines.append(f"<h1>{line[2:]}</h1>")
        elif not line.strip():
            lines.append("<br/>")
        else:
            lines.append(f"<p>{line}</p>")
    if in_list:
        lines.append("</ul>")
    body = "\n".join(lines)
    body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body)
    body = re.sub(r"`(.+?)`", r"<code>\1</code>", body)
    return (
        '<div style="font-family:Segoe UI,sans-serif;line-height:1.55;color:#1f2937">'
        f"{body}</div>"
    )


def parse_emails(values: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in values:
        email = (raw or "").strip().lower()
        if not email:
            continue
        if not EMAIL_RE.match(email):
            raise CalendarError(f"이메일 형식이 올바르지 않습니다: {raw.strip()}")
        if email not in seen:
            seen.append(email)
    if not seen:
        raise CalendarError("수신자 이메일을 한 명 이상 입력하세요.")
    if len(seen) > 20:
        raise CalendarError("수신자는 한 번에 20명까지입니다.")
    return seen


def create_event(
    access_token: str,
    *,
    title: str,
    start: datetime,
    end: datetime,
    location: str = "",
    body: str = "",
    attendees: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if end <= start:
        raise CalendarError("종료 시각은 시작 시각보다 뒤여야 합니다.")

    people = []
    for item in attendees or []:
        email = _clean(item.get("email")).lower()
        if not email or not EMAIL_RE.match(email):
            continue
        name = _clean(item.get("name")) or email.split("@")[0]
        people.append(
            {"emailAddress": {"address": email, "name": name}, "type": "required"}
        )

    payload: dict[str, Any] = {
        "subject": title.strip() or "(제목 없음)",
        "start": _graph_datetime(start),
        "end": _graph_datetime(end),
        "body": {"contentType": "HTML", "content": markdown_to_html(body)},
    }
    if location.strip():
        payload["location"] = {"displayName": location.strip()[:200]}
    if people:
        payload["attendees"] = people[:50]

    data = _graph_post(access_token, "/me/events", payload)
    started = _parse_graph_datetime(data.get("start"))
    ended = _parse_graph_datetime(data.get("end"))
    return {
        "id": data.get("id") or "",
        "web_link": data.get("webLink") or "",
        "title": _clean(data.get("subject")) or title,
        "start": started,
        "end": ended,
    }


def send_mail(access_token: str, *, to: list[str], subject: str, html: str) -> None:
    recipients = parse_emails(to)
    _graph_post(
        access_token,
        "/me/sendMail",
        {
            "message": {
                "subject": subject.strip() or "(제목 없음)",
                "body": {"contentType": "HTML", "content": html},
                "toRecipients": [{"emailAddress": {"address": email}} for email in recipients],
            },
            "saveToSentItems": True,
        },
    )


def fetch_profile(access_token: str) -> dict[str, str]:
    me = _graph_get(access_token, "/me", {"$select": "displayName,mail,userPrincipalName"})
    return {
        "name": me.get("displayName") or "",
        "email": me.get("mail") or me.get("userPrincipalName") or "",
    }


TEAMS_LINK = re.compile(r"https://teams\.microsoft\.com/l/meetup-join/\S+")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_graph_datetime(value: dict | None) -> datetime | None:
    """Graph 의 {dateTime, timeZone} 을 (Prefer 헤더로 이미 로컬 변환된) naive datetime 으로."""
    if not value or not value.get("dateTime"):
        return None
    raw = value["dateTime"].split(".")[0]
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _attendees(event: dict) -> list[dict[str, str]]:
    people: list[dict[str, str]] = []
    for item in event.get("attendees") or []:
        if item.get("type") == "resource":
            continue
        email = _clean((item.get("emailAddress") or {}).get("address"))
        name = _clean((item.get("emailAddress") or {}).get("name")) or email.split("@")[0]
        people.append({"name": name, "email": email})
    return people[:30]


GRAPH_EVENT_FIELDS = ",".join(
    [
        "id",
        "iCalUId",
        "subject",
        "start",
        "end",
        "isAllDay",
        "isCancelled",
        "location",
        "onlineMeeting",
        "onlineMeetingUrl",
        "organizer",
        "attendees",
        "bodyPreview",
        "seriesMasterId",
    ]
)


def fetch_events(access_token: str, days_back: int = 1, days_ahead: int = 14) -> list[dict]:
    """calendarView 로 기간 내 일정을 가져온다. 반복 일정은 Graph 가 회차별로 펼쳐 준다."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=max(days_back, 0))
    end = today + timedelta(days=max(days_ahead, 1))

    data = _graph_get(
        access_token,
        "/me/calendarView",
        {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$select": GRAPH_EVENT_FIELDS,
            "$orderby": "start/dateTime",
            "$top": MAX_EVENTS,
        },
    )

    events: list[dict] = []
    for item in data.get("value", []):
        started = _parse_graph_datetime(item.get("start"))
        if started is None:
            continue
        ended = _parse_graph_datetime(item.get("end"))
        uid = item.get("iCalUId") or item.get("id") or ""
        organizer = _clean(((item.get("organizer") or {}).get("emailAddress") or {}).get("address"))
        online = _clean((item.get("onlineMeeting") or {}).get("joinUrl")) or _clean(
            item.get("onlineMeetingUrl")
        )
        location = _clean((item.get("location") or {}).get("displayName"))
        if not online:
            match = TEAMS_LINK.search(f"{location} {item.get('bodyPreview') or ''}")
            online = match.group(0) if match else ""

        events.append(
            {
                "event_key": f"{uid}::{started.isoformat()}",
                "uid": uid,
                "title": _clean(item.get("subject")) or "(제목 없음)",
                "start": started.isoformat(),
                "end": ended.isoformat() if ended else None,
                "all_day": bool(item.get("isAllDay")),
                "location": location[:200],
                "organizer": organizer,
                "attendees": _attendees(item),
                "online_url": online,
                "is_cancelled": bool(item.get("isCancelled")),
                "description": _clean(item.get("bodyPreview"))[:500],
            }
        )
    return events[:MAX_EVENTS]


# --------------------------------------------------------------------------- #
# 공통 유틸
# --------------------------------------------------------------------------- #
def match_internal_users(
    attendees: list[dict[str, str]], organizer: str, users: list[Any]
) -> list[str]:
    """참석자 이름/메일 아이디를 사내 계정과 대조해 user_id 목록을 만든다."""
    by_name = {u.user_name.replace(" ", ""): u.user_id for u in users}
    by_id = {u.user_id.lower(): u.user_id for u in users}

    matched: list[str] = []
    for person in [*attendees, {"name": "", "email": organizer}]:
        name = (person.get("name") or "").replace(" ", "")
        local = (person.get("email") or "").split("@")[0].lower()
        found = by_name.get(name) or by_id.get(local)
        if found and found not in matched:
            matched.append(found)
    return matched


def sample_events(base: datetime | None = None) -> list[dict]:
    """연동 전 미리보기 / 테스트용 샘플 일정."""
    slot = (base or datetime.now()).replace(minute=0, second=0, microsecond=0)
    samples = [
        ("주간 업무 점검 회의", 0, 1, "Microsoft Teams 회의", True),
        ("로그인 API 설계 리뷰", 1, 1, "회의실 A", False),
        ("스프린트 회고", 3, 2, "Microsoft Teams 회의", True),
    ]

    events: list[dict] = []
    for index, (title, day_offset, hours, location, online) in enumerate(samples, start=1):
        started = slot + timedelta(days=day_offset, hours=1)
        events.append(
            {
                "event_key": f"sample-{index}@ainote.local::{started.isoformat()}",
                "uid": f"sample-{index}@ainote.local",
                "title": title,
                "start": started.isoformat(),
                "end": (started + timedelta(hours=hours)).isoformat(),
                "all_day": False,
                "location": location,
                "organizer": "leader1@example.com",
                "attendees": [
                    {"name": "이사원", "email": "member1@example.com"},
                    {"name": "최사원", "email": "member2@example.com"},
                ],
                "online_url": (
                    "https://teams.microsoft.com/l/meetup-join/sample" if online else ""
                ),
                "is_cancelled": False,
                "description": "",
            }
        )
    return events
