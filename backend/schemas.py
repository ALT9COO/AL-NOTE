"""Pydantic v2 요청/응답 스키마."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusLiteral = Literal["할당", "진행중", "이슈 발생", "완료"]
RoleLiteral = Literal["ADMIN", "LEADER", "MEMBER"]


# --------------------------------------------------------------------------- #
# Auth / User
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1, examples=["admin"])
    password: str = Field(min_length=1, examples=["admin123"])
    remember: bool = True


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    user_name: str
    role_level: RoleLiteral
    job_title: str = ""
    dept_id: int | None = None
    dept_name: str | None = None
    is_using_default_password: bool = False


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=4, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dept_id: int
    dept_name: str
    parent_dept_id: int | None = None


# --------------------------------------------------------------------------- #
# Admin (사용자 · 조직 · 권한 관리)
# --------------------------------------------------------------------------- #
class AdminUserOut(UserOut):
    created_at: datetime | None = None
    task_count: int = 0
    is_self: bool = False


class AdminUserCreate(BaseModel):
    user_id: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    user_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=4, max_length=128)
    role_level: RoleLiteral = "MEMBER"
    job_title: str = Field(default="", max_length=50)
    dept_id: int | None = None


class AdminUserUpdate(BaseModel):
    user_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=4, max_length=128)
    role_level: RoleLiteral | None = None
    job_title: str | None = Field(default=None, max_length=50)
    dept_id: int | None = None


class AdminDepartmentOut(DepartmentOut):
    parent_dept_name: str | None = None
    user_count: int = 0
    task_count: int = 0
    child_count: int = 0
    depth: int = 0


class AdminDepartmentCreate(BaseModel):
    dept_name: str = Field(min_length=1, max_length=100)
    parent_dept_id: int | None = None


class AdminDepartmentUpdate(BaseModel):
    dept_name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_dept_id: int | None = None


# --------------------------------------------------------------------------- #
# API 연동 · 사용량
# --------------------------------------------------------------------------- #
ProviderLiteral = Literal["openai", "anthropic", "google"]


class IntegrationOut(BaseModel):
    provider: str
    label: str
    description: str
    models: list[str]
    default_model: str
    supports_stt: bool
    key_hint: str
    console_url: str
    text_model: str
    has_key: bool
    masked_key: str
    is_active: bool
    last_test_ok: bool | None = None
    last_test_message: str | None = ""
    last_tested_at: datetime | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


class IntegrationListResponse(BaseModel):
    providers: list[IntegrationOut]
    active_provider: str
    active_model: str
    llm_ready: bool
    stt_ready: bool
    mock_mode: bool


class IntegrationUpdate(BaseModel):
    api_key: str | None = Field(default=None, max_length=255)
    text_model: str | None = Field(default=None, max_length=80)
    activate: bool | None = None


class ConnectionTestResult(BaseModel):
    provider: str
    ok: bool
    message: str
    latency_ms: int
    model: str


class UsageTotals(BaseModel):
    calls: int = 0
    success: int = 0
    error: int = 0
    mock: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: int = 0


class UsageByProvider(BaseModel):
    provider: str
    label: str
    calls: int
    total_tokens: int
    cost_usd: float
    avg_latency_ms: int
    error_calls: int
    is_active: bool


class UsageByFeature(BaseModel):
    feature: str
    calls: int
    total_tokens: int
    cost_usd: float


class UsageDailyPoint(BaseModel):
    date: str
    calls: int
    total_tokens: int
    cost_usd: float


class UsageLogOut(BaseModel):
    usage_id: int
    created_at: datetime
    provider: str
    model: str
    feature: str
    status: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    error_message: str | None = ""
    user_id: str | None = None


# --------------------------------------------------------------------------- #
# 캘린더 연동 (사용자별 Microsoft 365 / Graph)
# --------------------------------------------------------------------------- #
class CalendarConnectionOut(BaseModel):
    connected: bool
    app_configured: bool = False
    provider: str = "msgraph"
    account_name: str = ""
    account_email: str = ""
    needs_reauth: bool = False
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_sync_ok: bool | None = None
    last_sync_message: str = ""
    event_count: int = 0
    can_write: bool = False
    can_mail: bool = False
    missing_scopes: list[str] = []


class CalendarLoginUrl(BaseModel):
    url: str
    expires_in: int


class CalendarAppOut(BaseModel):
    configured: bool
    source: str = "none"  # db · env · none
    client_id: str = ""
    tenant_id: str = "common"
    redirect_uri: str = ""
    suggested_redirect_uris: list[str] = []
    client_secret_masked: str = ""
    scopes: list[str] = []
    updated_by: str | None = None
    updated_at: datetime | None = None


class CalendarAppUpdate(BaseModel):
    client_id: str = Field(default="", max_length=120)
    client_secret: str = Field(default="", max_length=300)
    tenant_id: str = Field(default="common", max_length=120)
    redirect_uri: str = Field(default="", max_length=300)


class CalendarAttendee(BaseModel):
    name: str
    email: str


class CalendarEventOut(BaseModel):
    event_key: str
    uid: str
    title: str
    start: datetime
    end: datetime | None = None
    all_day: bool = False
    location: str = ""
    organizer: str = ""
    attendees: list[CalendarAttendee] = []
    online_url: str = ""
    is_cancelled: bool = False
    description: str = ""
    matched_user_ids: list[str] = []
    meeting_id: int | None = None
    meeting_title: str | None = None


class CalendarEventsResponse(BaseModel):
    connection: CalendarConnectionOut
    range_start: date
    range_end: date
    events: list[CalendarEventOut]
    sample: bool = False


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    start: datetime
    end: datetime
    location: str = Field(default="", max_length=300)
    body: str = Field(default="", max_length=8000)
    attendees: list[CalendarAttendee] = []


class CalendarEventCreated(BaseModel):
    id: str
    web_link: str = ""
    title: str
    start: datetime | None = None
    end: datetime | None = None


class UsageResponse(BaseModel):
    generated_at: datetime
    range_days: int
    totals: UsageTotals
    today: UsageTotals
    by_provider: list[UsageByProvider]
    by_feature: list[UsageByFeature]
    daily: list[UsageDailyPoint]
    recent: list[UsageLogOut]


# --------------------------------------------------------------------------- #
# Task
# --------------------------------------------------------------------------- #
class CollaboratorIn(BaseModel):
    kind: Literal["user", "dept"]
    user_id: str | None = None
    dept_id: int | None = None


class CollaboratorOut(BaseModel):
    kind: Literal["user", "dept"]
    user_id: str | None = None
    user_name: str | None = None
    dept_id: int | None = None
    dept_name: str | None = None


class TaskActivityOut(BaseModel):
    activity_id: int
    kind: str
    body: str
    progress: int | None = None
    status: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    created_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class TaskOut(BaseModel):
    task_id: str
    task_name: str
    description: str | None = ""
    status: StatusLiteral
    progress: int
    dept_id: int | None = None
    dept_name: str | None = None
    assigned_to: str | None = None
    assignee_name: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    issues: str | None = ""
    updated_at: datetime | None = None
    is_delayed: bool = False
    can_edit: bool = False
    is_collaborator: bool = False
    latest_comment_at: datetime | None = None
    collaborators: list[CollaboratorOut] = []
    viewers: list[CollaboratorOut] = []
    activities: list[TaskActivityOut] = []
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    deleted_by_name: str | None = None
    purge_on: datetime | None = None
    parent_task_id: str | None = None
    child_count: int = 0
    progress_locked: bool = False
    children: list["TaskOut"] = []


class TaskAlertOut(BaseModel):
    task_id: str
    task_name: str
    assignee_name: str | None = None
    due_date: date | None = None
    days_left: int
    is_delayed: bool = False


class TaskCreate(BaseModel):
    task_name: str = Field(min_length=1, max_length=200)
    description: str | None = ""
    status: StatusLiteral = "할당"
    progress: int = Field(default=0, ge=0, le=100)
    dept_id: int | None = None
    assigned_to: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    issues: str | None = ""
    collaborators: list[CollaboratorIn] = []
    viewers: list[CollaboratorIn] = []
    parent_task_id: str | None = None


class TaskUpdate(BaseModel):
    task_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: StatusLiteral | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    dept_id: int | None = None
    assigned_to: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    issues: str | None = None
    collaborators: list[CollaboratorIn] | None = None
    viewers: list[CollaboratorIn] | None = None


class TaskStatusUpdate(BaseModel):
    """칸반 드래그 앤 드롭 전용 — 상태 변경 시 진행률 자동 보정."""

    status: StatusLiteral
    progress: int | None = Field(default=None, ge=0, le=100)


TaskOut.model_rebuild()


# --------------------------------------------------------------------------- #
# Meeting
# --------------------------------------------------------------------------- #
class TranscriptResponse(BaseModel):
    transcript: str
    mock: bool = False
    draft_id: int | None = None
    has_audio: bool = False
    audio_name: str | None = None
    audio_size: int | None = None
    stt_status: str = "done"
    stt_error: str | None = None


class ParseRequest(BaseModel):
    transcript: str = Field(min_length=1)
    event_title: str = Field(default="", max_length=200)
    attendees: list[str] = []


class AgendaItem(BaseModel):
    topic: str = ""
    discussion: str = ""
    decision: str = ""


class ActionItem(BaseModel):
    title: str = ""
    assignee: str = ""
    due_date: str = ""
    note: str = ""


class TaskUpdateProposal(BaseModel):
    task_id: str = "NEW"
    task_name: str = ""
    assignee: str = ""
    status: StatusLiteral = "진행중"
    progress: int = Field(default=0, ge=0, le=100)
    issues: str = ""
    due_date: str = ""
    is_new: bool = False
    change_note: str = ""


class MeetingParseResponse(BaseModel):
    meeting_title: str
    summary_bullets: list[str] = []
    agenda_items: list[AgendaItem] = []
    action_items: list[ActionItem] = []
    task_updates: list[TaskUpdateProposal] = []
    risks: list[str] = []
    mock: bool = False


class AgendaSubmitRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    transcript: str = ""
    summary_bullets: list[str] = []
    agenda_items: list[AgendaItem] = []
    action_items: list[ActionItem] = []
    risks: list[str] = []
    task_updates: list[TaskUpdateProposal] = []
    event_key: str | None = Field(default=None, max_length=300)
    event_start: datetime | None = None
    event_location: str | None = Field(default=None, max_length=255)
    participants: list[CollaboratorIn] = []
    viewers: list[CollaboratorIn] = []
    draft_id: int | None = None


class MeetingDraftIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    transcript: str = ""
    parsed: dict | None = None
    event: dict | None = None
    step: int = Field(default=2, ge=1, le=3)


class MeetingDraftOut(BaseModel):
    draft_id: int
    title: str
    transcript: str
    parsed: dict | None = None
    event: dict | None = None
    step: int = 2
    created_at: datetime
    updated_at: datetime
    has_audio: bool = False
    audio_name: str | None = None
    audio_size: int | None = None
    stt_status: str = "idle"
    stt_error: str | None = None
    stt_mock: bool = False


class MeetingAccessUpdate(BaseModel):
    participants: list[CollaboratorIn] = []
    viewers: list[CollaboratorIn] = []


class AgendaSubmitResponse(BaseModel):
    meeting_id: int
    updated: list[str] = []
    created: list[str] = []
    skipped: list[str] = []
    tasks: list[TaskOut] = []


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meeting_id: int
    title: str
    created_by: str | None = None
    author_name: str | None = None
    dept_name: str | None = None
    ai_summary: str | None = ""
    raw_transcript: str | None = ""
    created_at: datetime
    event_key: str | None = None
    event_start: datetime | None = None
    event_location: str | None = ""
    task_ids: list[str] = []
    participants: list[CollaboratorOut] = []
    viewers: list[CollaboratorOut] = []
    can_manage: bool = False
    has_audio: bool = False
    audio_name: str | None = None
    audio_size: int | None = None


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
PeriodLiteral = Literal["weekly", "monthly", "quarterly", "yearly"]


class StatusCount(BaseModel):
    status: str
    count: int


class AssigneeStat(BaseModel):
    assignee: str
    total: int
    done: int
    delayed: int
    avg_progress: int


class DeptStat(BaseModel):
    dept_name: str
    total: int
    avg_progress: int
    delayed: int


class TrendPoint(BaseModel):
    label: str
    completed: int
    created: int


class WeekCompareRow(BaseModel):
    task_id: str
    task_name: str
    assignee_name: str = ""
    last_week: str
    this_week: str
    last_progress: int | None = None
    this_progress: int | None = None
    delta: int | None = None


class WeekOverWeek(BaseModel):
    last_start: date
    last_end: date
    last_total: int
    last_completed: int
    last_delayed: int
    last_avg_progress: int
    last_completion_rate: int
    rows: list[WeekCompareRow] = []


class AnalyticsSummary(BaseModel):
    period: PeriodLiteral
    start_date: date
    end_date: date
    scope_label: str
    total: int
    completed: int
    delayed: int
    with_issues: int
    avg_progress: int
    completion_rate: int
    status_counts: list[StatusCount]
    by_assignee: list[AssigneeStat]
    by_dept: list[DeptStat]
    trend: list[TrendPoint]
    tasks: list[TaskOut]
    week_over_week: WeekOverWeek | None = None


class ReportRequest(BaseModel):
    period: PeriodLiteral = "weekly"
    anchor: date | None = None
    dept_id: int | None = None


class SavedReportSummary(BaseModel):
    report_id: int
    period: PeriodLiteral
    period_label: str
    scope_label: str
    mock: bool = False
    created_at: datetime


class ReportResponse(BaseModel):
    report_id: int | None = None
    period: PeriodLiteral | None = None
    anchor: date | None = None
    dept_id: int | None = None
    period_label: str
    scope_label: str
    report_markdown: str
    mock: bool = False
    created_at: datetime | None = None


class ReportEmailRequest(BaseModel):
    period: PeriodLiteral = "weekly"
    anchor: date | None = None
    dept_id: int | None = None
    to: list[str] = Field(min_length=1, max_length=20)
    markdown: str | None = Field(default=None, max_length=50_000)


class ReportEmailResponse(BaseModel):
    sent_to: list[str]
    subject: str
