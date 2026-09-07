"""SQLAlchemy ORM 모델, 엔진, 초기 시드 데이터."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Iterable, Iterator

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
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
    settings.db_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if settings.db_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


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

    def __repr__(self) -> str:  # pragma: no cover - 디버깅용
        return f"<Department {self.dept_id} {self.dept_name}>"


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    dept_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.dept_id"))
    role_level: Mapped[str] = mapped_column(String(20), nullable=False, default="MEMBER")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    department = relationship("Department", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.user_id} ({self.role_level})>"


class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    dept_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.dept_id"))
    assigned_to: Mapped[str | None] = mapped_column(String(50), ForeignKey("users.user_id"))
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="시작전")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    issues: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    assignee = relationship("User", lazy="joined")
    department = relationship("Department", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Task {self.task_id} {self.task_name} {self.status}>"


class Meeting(Base):
    __tablename__ = "meetings"

    meeting_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(50), ForeignKey("users.user_id"))
    dept_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.dept_id"))
    raw_transcript: Mapped[str | None] = mapped_column(Text, default="")
    ai_summary: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    author = relationship("User", lazy="joined")
    department = relationship("Department", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Meeting {self.meeting_id} {self.title}>"


# --------------------------------------------------------------------------- #
# Session helpers
# --------------------------------------------------------------------------- #
@contextmanager
def get_session() -> Iterator[Session]:
    """with 문으로 사용하는 세션 컨텍스트 매니저 (자동 commit / rollback)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def next_task_id(session: Session) -> str:
    """TASK-001 형식의 다음 ID 를 생성한다."""
    ids = session.scalars(select(Task.task_id)).all()
    max_num = 0
    for tid in ids:
        try:
            max_num = max(max_num, int(str(tid).split("-")[-1]))
        except (ValueError, IndexError):
            continue
    return f"TASK-{max_num + 1:03d}"


def get_descendant_dept_ids(session: Session, dept_id: int | None) -> list[int]:
    """해당 부서와 모든 하위 부서 ID 목록 (재귀)."""
    if dept_id is None:
        return []
    rows = session.execute(select(Department.dept_id, Department.parent_dept_id)).all()
    children: dict[int | None, list[int]] = {}
    for did, parent in rows:
        children.setdefault(parent, []).append(did)

    result: list[int] = []
    stack: list[int] = [dept_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.append(current)
        stack.extend(children.get(current, []))
    return result


def department_map(session: Session) -> dict[int, str]:
    return {d.dept_id: d.dept_name for d in session.scalars(select(Department)).all()}


def user_map(session: Session) -> dict[str, str]:
    return {u.user_id: u.user_name for u in session.scalars(select(User)).all()}


def list_users(session: Session, dept_ids: Iterable[int] | None = None) -> list[User]:
    stmt = select(User).order_by(User.dept_id, User.user_name)
    if dept_ids is not None:
        dept_ids = list(dept_ids)
        if not dept_ids:
            return []
        stmt = stmt.where(User.dept_id.in_(dept_ids))
    return list(session.scalars(stmt).all())


# --------------------------------------------------------------------------- #
# Init & seed
# --------------------------------------------------------------------------- #
def seed_data(session: Session) -> None:
    """테스트용 초기 데이터: 부서 2개, 사용자 4명(관리자1/팀장1/팀원2), 업무 5개."""
    from auth import hash_password  # 순환 import 방지를 위한 지연 import

    if session.scalar(select(func.count()).select_from(Department)):
        return

    hq = Department(dept_id=1, dept_name="경영지원본부", parent_dept_id=None)
    dev = Department(dept_id=2, dept_name="개발팀", parent_dept_id=1)
    session.add_all([hq, dev])
    session.flush()

    users = [
        User(
            user_id="admin",
            user_name="김관리",
            password_hash=hash_password("admin123"),
            dept_id=1,
            role_level="ADMIN",
        ),
        User(
            user_id="leader1",
            user_name="박팀장",
            password_hash=hash_password("leader123"),
            dept_id=2,
            role_level="LEADER",
        ),
        User(
            user_id="member1",
            user_name="이사원",
            password_hash=hash_password("member123"),
            dept_id=2,
            role_level="MEMBER",
        ),
        User(
            user_id="member2",
            user_name="최사원",
            password_hash=hash_password("member123"),
            dept_id=2,
            role_level="MEMBER",
        ),
    ]
    session.add_all(users)
    session.flush()

    today = date.today()
    tasks = [
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
            status="검토필요",
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
            status="시작전",
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
    session.add_all(tasks)


def init_db() -> None:
    """테이블 생성 + 최초 1회 시드."""
    Base.metadata.create_all(engine)
    with get_session() as session:
        seed_data(session)
