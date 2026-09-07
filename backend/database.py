"""SQLAlchemy 엔진 · 세션 · SQLite 모델 및 시드 데이터."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterator

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class Department(Base):
    __tablename__ = "departments"

    dept_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dept_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_dept_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.dept_id"), nullable=True
    )

    parent = relationship("Department", remote_side=[dept_id], backref="children")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    dept_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.dept_id"))
    job_title: Mapped[str] = mapped_column(String(50), default="")
    role_level: Mapped[str] = mapped_column(String(20), nullable=False, default="MEMBER")
    uses_default_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    department = relationship("Department", lazy="joined")


class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    parent_task_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("tasks.task_id"), nullable=True, index=True
    )
    dept_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.dept_id"))
    assigned_to: Mapped[str | None] = mapped_column(String(50), ForeignKey("users.user_id"))
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="할당")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    issues: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    deleted_by: Mapped[str | None] = mapped_column(String(50), nullable=True)

    assignee = relationship("User", lazy="joined")
    department = relationship("Department", lazy="joined")
    collaborators = relationship(
        "TaskCollaborator",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    viewers = relationship(
        "TaskViewer",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    activities = relationship(
        "TaskActivity",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TaskActivity.created_at",
    )


class TaskCollaborator(Base):
    """사람 또는 조직 단위 공동작업자. 해당 업무가 그 대상에게도 보인다."""

    __tablename__ = "task_collaborators"

    collab_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tasks.task_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.user_id"), nullable=True
    )
    dept_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.dept_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    task = relationship("Task", back_populates="collaborators")
    user = relationship("User", lazy="joined", foreign_keys=[user_id])
    department = relationship("Department", lazy="joined", foreign_keys=[dept_id])


class TaskViewer(Base):
    """카드 열람 허용 대상. 한 명이라도 있으면 기본 정책 대신 이 목록(+담당자)만 볼 수 있다."""

    __tablename__ = "task_viewers"

    viewer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tasks.task_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.user_id"), nullable=True
    )
    dept_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.dept_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    task = relationship("Task", back_populates="viewers")
    user = relationship("User", lazy="joined", foreign_keys=[user_id])
    department = relationship("Department", lazy="joined", foreign_keys=[dept_id])


class TaskActivity(Base):
    """댓글 · 진척/상태 변경 히스토리."""

    __tablename__ = "task_activities"

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tasks.task_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.user_id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="comment")
    body: Mapped[str] = mapped_column(Text, default="")
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    task = relationship("Task", back_populates="activities")
    author = relationship("User", lazy="joined", foreign_keys=[user_id])


class Meeting(Base):
    __tablename__ = "meetings"

    meeting_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(50), ForeignKey("users.user_id"))
    dept_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.dept_id"))
    raw_transcript: Mapped[str | None] = mapped_column(Text, default="")
    ai_summary: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # 외부 캘린더(ICS) 일정과의 연결. event_key = "{UID}::{시작시각}" 으로 반복 일정도 회차별로 구분한다.
    event_key: Mapped[str | None] = mapped_column(String(300), index=True)
    event_start: Mapped[datetime | None] = mapped_column(DateTime)
    event_location: Mapped[str | None] = mapped_column(String(255), default="")
    task_ids: Mapped[str] = mapped_column(Text, default="")
    audio_file: Mapped[str | None] = mapped_column(String(80), nullable=True)
    audio_filename: Mapped[str | None] = mapped_column(String(120), nullable=True)
    audio_mime: Mapped[str | None] = mapped_column(String(80), nullable=True)
    audio_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    author = relationship("User", lazy="joined")
    department = relationship("Department", lazy="joined")
    participants = relationship(
        "MeetingParticipant",
        back_populates="meeting",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    viewers = relationship(
        "MeetingViewer",
        back_populates="meeting",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MeetingParticipant(Base):
    """회의 참여자. 작성자·관리자와 함께 회의록을 볼 수 있다."""

    __tablename__ = "meeting_participants"

    participant_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meetings.meeting_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.user_id"), nullable=True
    )
    dept_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.dept_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    meeting = relationship("Meeting", back_populates="participants")
    user = relationship("User", lazy="joined", foreign_keys=[user_id])
    department = relationship("Department", lazy="joined", foreign_keys=[dept_id])


class MeetingViewer(Base):
    """추가 열람자. 참석하지 않아도 회의록을 볼 수 있다."""

    __tablename__ = "meeting_viewers"

    viewer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meetings.meeting_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.user_id"), nullable=True
    )
    dept_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.dept_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    meeting = relationship("Meeting", back_populates="viewers")
    user = relationship("User", lazy="joined", foreign_keys=[user_id])
    department = relationship("Department", lazy="joined", foreign_keys=[dept_id])


class MeetingDraft(Base):
    """전사·분석 중간 저장. 제출 전까지 유지되어 껐다 켜도 이어서 진행할 수 있다."""

    __tablename__ = "meeting_drafts"

    draft_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="전사 초안")
    raw_transcript: Mapped[str] = mapped_column(Text, default="")
    parsed_json: Mapped[str] = mapped_column(Text, default="")
    event_json: Mapped[str] = mapped_column(Text, default="")
    step: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    audio_file: Mapped[str | None] = mapped_column(String(80), nullable=True)
    audio_filename: Mapped[str | None] = mapped_column(String(120), nullable=True)
    audio_mime: Mapped[str | None] = mapped_column(String(80), nullable=True)
    audio_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stt_status: Mapped[str] = mapped_column(String(20), default="idle")
    stt_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stt_mock: Mapped[bool] = mapped_column(Boolean, default=False)

    author = relationship("User", lazy="joined")


class AnalyticsReport(Base):
    """생성된 AI 경영 리포트 보관. 새로고침·재접속 후에도 열람할 수 있다."""

    __tablename__ = "analytics_reports"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id"), index=True)
    period: Mapped[str] = mapped_column(String(20))
    anchor: Mapped[date | None] = mapped_column(Date, nullable=True)
    dept_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.dept_id"), nullable=True
    )
    period_label: Mapped[str] = mapped_column(String(120))
    scope_label: Mapped[str] = mapped_column(String(200))
    report_markdown: Mapped[str] = mapped_column(Text)
    mock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    author = relationship("User", lazy="joined")


class CalendarConnection(Base):
    """사용자별 Microsoft 365 캘린더 연결 (Graph 위임 토큰)."""

    __tablename__ = "calendar_connections"

    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), default="msgraph")
    account_name: Mapped[str] = mapped_column(String(120), default="")
    account_email: Mapped[str] = mapped_column(String(200), default="")
    access_token: Mapped[str] = mapped_column(Text, default="")
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    scopes: Mapped[str] = mapped_column(Text, default="")
    needs_reauth: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_sync_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_sync_message: Mapped[str | None] = mapped_column(Text, default="")
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class CalendarApp(Base):
    """Azure AD 앱 등록 정보 (조직 공통, ADMIN 이 설정 화면에서 입력)."""

    __tablename__ = "calendar_app"

    app_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    client_id: Mapped[str] = mapped_column(String(120), default="")
    client_secret: Mapped[str] = mapped_column(Text, default="")
    tenant_id: Mapped[str] = mapped_column(String(120), default="common")
    redirect_uri: Mapped[str] = mapped_column(String(300), default="")
    updated_by: Mapped[str | None] = mapped_column(String(50), ForeignKey("users.user_id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class ApiSetting(Base):
    """AI 프로바이더별 연동 설정 (프로바이더당 1행, 활성 프로바이더는 1개)."""

    __tablename__ = "api_settings"

    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    api_key: Mapped[str] = mapped_column(String(255), default="")
    text_model: Mapped[str] = mapped_column(String(80), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, default="")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(50), ForeignKey("users.user_id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class AppMeta(Base):
    """앱 전역 메타데이터 (업무 번호 시퀀스 등)."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(20), default="0")


class ApiUsage(Base):
    """AI 호출 1건당 사용량 로그 (실시간 사용량 모니터의 원천 데이터)."""

    __tablename__ = "api_usage"

    usage_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)
    model: Mapped[str] = mapped_column(String(80), default="")
    feature: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(20), default="success")  # success · error · mock
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, default="")
    user_id: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


# --------------------------------------------------------------------------- #
# Session dependency & helpers
# --------------------------------------------------------------------------- #
def get_db() -> Iterator[Session]:
    """FastAPI 의존성: 요청 단위 DB 세션."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def next_task_id(db: Session) -> str:
    """TASK-001 형식의 다음 상위 업무 ID. 한 번 부여된 번호는 삭제 후에도 재사용하지 않는다."""
    meta = db.get(AppMeta, "task_id_seq")
    if meta is None:
        max_num = _max_task_number(db)
        meta = AppMeta(key="task_id_seq", value=str(max_num))
        db.add(meta)
        db.flush()
    next_num = int(meta.value) + 1
    meta.value = str(next_num)
    db.flush()
    return f"TASK-{next_num:03d}"


def next_subtask_id(db: Session, parent_id: str) -> str:
    """TASK-012-01 형식. 부모 안에서만 증가하며 삭제 후에도 번호를 재사용하지 않는다."""
    prefix = f"{parent_id}-"
    max_n = 0
    for tid in db.scalars(select(Task.task_id).where(Task.task_id.startswith(prefix))).all():
        suffix = str(tid)[len(prefix) :]
        if suffix.isdigit():
            max_n = max(max_n, int(suffix))
    return f"{parent_id}-{max_n + 1:02d}"


def _parent_task_number(task_id: str) -> int | None:
    """상위 업무 번호만 추출. TASK-012-01 같은 하위 ID는 무시한다."""
    parts = str(task_id).split("-")
    if len(parts) == 2 and parts[0].upper() == "TASK" and parts[1].isdigit():
        return int(parts[1])
    return None


def _max_task_number(db: Session) -> int:
    max_num = 0
    for tid in db.scalars(select(Task.task_id)).all():
        num = _parent_task_number(str(tid))
        if num is not None:
            max_num = max(max_num, num)
    return max_num


def _ensure_task_id_seq(db: Session) -> None:
    if db.get(AppMeta, "task_id_seq") is not None:
        return
    db.add(AppMeta(key="task_id_seq", value=str(_max_task_number(db))))
    db.commit()


def _backfill_parent_links(db: Session) -> None:
    """TASK-012-01 형식인데 parent_task_id 가 비어 있으면 상위와 다시 연결한다."""
    fixed = 0
    for task in db.scalars(select(Task)).unique().all():
        if task.parent_task_id:
            continue
        parts = str(task.task_id).split("-")
        if len(parts) != 3 or parts[0].upper() != "TASK" or not parts[1].isdigit() or not parts[2].isdigit():
            continue
        parent_id = f"{parts[0]}-{parts[1]}"
        parent = db.get(Task, parent_id) or db.get(Task, parent_id.upper()) or db.get(Task, f"TASK-{int(parts[1]):03d}")
        if parent is None or parent.task_id == task.task_id:
            continue
        task.parent_task_id = parent.task_id
        fixed += 1
    if fixed:
        db.commit()
        print(f"[db] 하위 업무 상위 연결 복구: {fixed}건")


def get_descendant_dept_ids(db: Session, dept_id: int | None) -> list[int]:
    """해당 부서 + 모든 하위 부서 ID (재귀 탐색)."""
    if dept_id is None:
        return []
    cache = db.info.setdefault("dept_id_cache", {})
    key = ("desc", dept_id)
    if key in cache:
        return cache[key]
    children: dict[int | None, list[int]] = {}
    for did, parent in _dept_parent_rows(db):
        children.setdefault(parent, []).append(did)

    result: list[int] = []
    stack = [dept_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.append(current)
        stack.extend(children.get(current, []))
    cache[key] = result
    return result


def get_ancestor_dept_ids(db: Session, dept_id: int | None) -> list[int]:
    """본인 부서 + 상위 부서 ID (조직 공동작업자 조회용)."""
    if dept_id is None:
        return []
    cache = db.info.setdefault("dept_id_cache", {})
    key = ("anc", dept_id)
    if key in cache:
        return cache[key]
    parent_of = {did: parent for did, parent in _dept_parent_rows(db)}
    result: list[int] = []
    current: int | None = dept_id
    seen: set[int] = set()
    while current is not None and current not in seen:
        seen.add(current)
        result.append(current)
        current = parent_of.get(current)
    cache[key] = result
    return result


def _dept_parent_rows(db: Session):
    cached = db.info.get("dept_parent_rows")
    if cached is None:
        cached = db.execute(select(Department.dept_id, Department.parent_dept_id)).all()
        db.info["dept_parent_rows"] = cached
    return cached


# --------------------------------------------------------------------------- #
# Init & seed
# --------------------------------------------------------------------------- #
def seed_data(db: Session) -> None:
    """테스트 시드: 부서 2개, 사용자 4명(ADMIN 1 / LEADER 1 / MEMBER 2), 업무 5건."""
    from auth import hash_password  # 순환 import 방지

    if db.scalar(select(func.count()).select_from(Department)):
        return

    db.add_all(
        [
            Department(dept_id=1, dept_name="경영지원본부", parent_dept_id=None),
            Department(dept_id=2, dept_name="개발팀", parent_dept_id=1),
        ]
    )
    db.flush()

    db.add_all(
        [
            User(
                user_id="admin",
                user_name="김관리",
                password_hash=hash_password("admin123"),
                dept_id=1,
                job_title="본부장",
                role_level="ADMIN",
                uses_default_password=True,
            ),
            User(
                user_id="leader1",
                user_name="박팀장",
                password_hash=hash_password("leader123"),
                dept_id=2,
                job_title="팀장",
                role_level="LEADER",
                uses_default_password=True,
            ),
            User(
                user_id="member1",
                user_name="이사원",
                password_hash=hash_password("member123"),
                dept_id=2,
                job_title="사원",
                role_level="MEMBER",
                uses_default_password=True,
            ),
            User(
                user_id="member2",
                user_name="최사원",
                password_hash=hash_password("member123"),
                dept_id=2,
                job_title="사원",
                role_level="MEMBER",
                uses_default_password=True,
            ),
        ]
    )
    db.flush()

    today = date.today()
    db.add_all(
        [
            Task(
                task_id="TASK-001",
                dept_id=2,
                assigned_to="member1",
                task_name="로그인 API 개발",
                description="JWT 기반 인증 API 설계 및 구현",
                status="진행중",
                progress=60,
                start_date=today - timedelta(days=10),
                due_date=today + timedelta(days=5),
                issues="리프레시 토큰 저장소 정책 미확정",
            ),
            Task(
                task_id="TASK-002",
                dept_id=2,
                assigned_to="member2",
                task_name="대시보드 UI 퍼블리싱",
                description="칸반 보드 및 통계 화면 마크업",
                status="이슈 발생",
                progress=90,
                start_date=today - timedelta(days=14),
                due_date=today + timedelta(days=1),
                issues="모바일 반응형 레이아웃 QA 대기",
            ),
            Task(
                task_id="TASK-003",
                dept_id=2,
                assigned_to="member1",
                task_name="회의록 STT 파이프라인 구축",
                description="Whisper API 연동 및 텍스트 후처리",
                status="할당",
                progress=0,
                start_date=today + timedelta(days=2),
                due_date=today + timedelta(days=20),
                issues="",
            ),
            Task(
                task_id="TASK-004",
                dept_id=1,
                assigned_to="admin",
                task_name="3분기 예산 집행 계획 수립",
                description="부서별 예산 배분안 작성",
                status="완료",
                progress=100,
                start_date=today - timedelta(days=30),
                due_date=today - timedelta(days=3),
                issues="",
            ),
            Task(
                task_id="TASK-005",
                dept_id=2,
                assigned_to="leader1",
                task_name="분기 로드맵 리뷰",
                description="팀 분기 목표 점검 및 리스크 정리",
                status="진행중",
                progress=35,
                start_date=today - timedelta(days=5),
                due_date=today - timedelta(days=1),
                issues="일정 지연 - 협력사 회신 지연",
            ),
        ]
    )
    db.commit()


def seed_api_settings(db: Session) -> None:
    """프로바이더별 설정 행을 보장한다. .env 에 키가 있으면 초기값으로 채운다."""
    from config import AI_PROVIDERS

    existing = set(db.scalars(select(ApiSetting.provider)).all())
    created = [p for p in AI_PROVIDERS if p not in existing]
    if not created:
        return

    for provider in created:
        meta = AI_PROVIDERS[provider]
        db.add(
            ApiSetting(
                provider=provider,
                api_key=settings.env_key(provider),
                text_model=meta["default_model"],
                is_active=False,
            )
        )
    db.flush()

    # 활성 프로바이더가 없으면 키가 있는 프로바이더를, 없으면 OpenAI 를 기본 활성화한다.
    rows = db.scalars(select(ApiSetting)).all()
    if not any(row.is_active for row in rows):
        target = next((row for row in rows if row.api_key), None) or db.get(ApiSetting, "openai")
        if target:
            target.is_active = True
    db.commit()


def _drop_legacy_tables() -> None:
    """ICS 구독 시절의 calendar_connections 스키마는 Graph 연동과 호환되지 않아 비운다."""
    with engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(calendar_connections)").fetchall()
        }
        if "ics_url" in columns:
            conn.exec_driver_sql("DROP TABLE calendar_connections")
            print("[db] 구 ICS 캘린더 연결 테이블 제거 — Microsoft 계정으로 다시 연결해야 합니다.")


def _ensure_columns() -> None:
    """SQLite 는 create_all 로 기존 테이블에 컬럼을 추가하지 못하므로 직접 채워 넣는다."""
    added: list[str] = []
    with engine.begin() as conn:
        for table, columns in {
            "meetings": {
                "event_key": "VARCHAR(300)",
                "event_start": "DATETIME",
                "event_location": "VARCHAR(255)",
                "task_ids": "TEXT DEFAULT ''",
                "audio_file": "VARCHAR(80)",
                "audio_filename": "VARCHAR(120)",
                "audio_mime": "VARCHAR(80)",
                "audio_size": "INTEGER",
            },
            "meeting_drafts": {
                "audio_file": "VARCHAR(80)",
                "audio_filename": "VARCHAR(120)",
                "audio_mime": "VARCHAR(80)",
                "audio_size": "INTEGER",
                "stt_status": "VARCHAR(20) DEFAULT 'idle'",
                "stt_error": "TEXT",
                "stt_mock": "BOOLEAN DEFAULT 0",
            },
            "users": {
                "job_title": "VARCHAR(50) DEFAULT ''",
                "uses_default_password": "BOOLEAN DEFAULT 0",
            },
            "tasks": {
                "deleted_at": "DATETIME",
                "deleted_by": "VARCHAR(50)",
                "parent_task_id": "VARCHAR(30)",
            },
        }.items():
            existing = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue
            for name, ddl in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                    added.append(f"{table}.{name}")
    if added:
        print(f"[db] 컬럼 추가: {', '.join(added)}")


def _backfill_task_history(db: Session) -> None:
    """기존 최신 이슈 텍스트를 첫 댓글로 옮기고, 등록 이력을 채운다."""
    tasks = list(db.scalars(select(Task)).unique().all())
    added = 0
    for task in tasks:
        kinds = {item.kind for item in task.activities}
        if "create" not in kinds:
            db.add(
                TaskActivity(
                    task_id=task.task_id,
                    user_id=task.assigned_to,
                    kind="create",
                    body="업무가 등록되었습니다.",
                    progress=task.progress or 0,
                    status=task.status,
                    created_at=task.created_at,
                )
            )
            added += 1
        if (task.issues or "").strip() and "comment" not in kinds:
            db.add(
                TaskActivity(
                    task_id=task.task_id,
                    user_id=task.assigned_to,
                    kind="comment",
                    body=task.issues.strip(),
                    progress=task.progress or 0,
                    status=task.status,
                    created_at=task.updated_at or task.created_at,
                )
            )
            added += 1
    if added:
        db.commit()
        print(f"[db] 업무 히스토리 백필: {added}건")


def _migrate_status_labels() -> None:
    """칸반 상태 워딩 변경: 시작전→할당, 검토필요/검토요청→이슈 발생."""
    renamed = 0
    with engine.begin() as conn:
        for old, new in (("시작전", "할당"), ("검토필요", "이슈 발생"), ("검토요청", "이슈 발생")):
            result = conn.exec_driver_sql("UPDATE tasks SET status = ? WHERE status = ?", (new, old))
            renamed += result.rowcount or 0
            conn.exec_driver_sql(
                "UPDATE task_activities SET status = ? WHERE status = ?", (new, old)
            )
    if renamed:
        print(f"[db] 업무 상태 워딩 변경: {renamed}건")


def _purge_expired_tasks() -> None:
    """삭제 후 1년이 지난 업무는 완전히 지운다."""
    cutoff = datetime.now() - timedelta(days=365)
    with SessionLocal() as db:
        expired = list(
            db.scalars(
                select(Task).where(Task.deleted_at.is_not(None), Task.deleted_at < cutoff)
            ).unique().all()
        )
        for task in expired:
            db.delete(task)
        db.commit()
    if expired:
        print(f"[db] 보관 만료 업무 삭제: {len(expired)}건")


def _backfill_default_password_flags(db: Session) -> None:
    from auth import is_seed_password_hash

    changed = 0
    for user in db.scalars(select(User)).unique().all():
        flag = is_seed_password_hash(user.password_hash)
        if bool(user.uses_default_password) != flag:
            user.uses_default_password = flag
            changed += 1
    if changed:
        db.commit()
        print(f"[db] 기본 비밀번호 플래그 갱신: {changed}명")


def _seal_stored_secrets(db: Session) -> None:
    from secret_box import is_sealed, seal

    changed = 0
    for row in db.scalars(select(ApiSetting)).all():
        if row.api_key and not is_sealed(row.api_key):
            row.api_key = seal(row.api_key)
            changed += 1
    app = db.get(CalendarApp, 1)
    if app is not None and app.client_secret and not is_sealed(app.client_secret):
        app.client_secret = seal(app.client_secret)
        changed += 1
    for conn in db.scalars(select(CalendarConnection)).all():
        if conn.access_token and not is_sealed(conn.access_token):
            conn.access_token = seal(conn.access_token)
            changed += 1
        if conn.refresh_token and not is_sealed(conn.refresh_token):
            conn.refresh_token = seal(conn.refresh_token)
            changed += 1
    if changed:
        db.commit()
        print(f"[db] 저장 시크릿 암호화: {changed}건")


def init_db() -> None:
    _drop_legacy_tables()
    Base.metadata.create_all(engine)
    _ensure_columns()
    _migrate_status_labels()
    _purge_expired_tasks()
    with SessionLocal() as db:
        seed_data(db)
        seed_api_settings(db)
        _ensure_task_id_seq(db)
        _backfill_task_history(db)
        _backfill_parent_links(db)
        _backfill_default_password_flags(db)
        _seal_stored_secrets(db)
