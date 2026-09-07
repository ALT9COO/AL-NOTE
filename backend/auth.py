"""JWT 토큰 발급/검증 · bcrypt 해싱 · RBAC 유틸리티."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import Select, and_, exists, not_, or_, select
from sqlalchemy.orm import Session, noload

from config import settings
from database import (
    Department,
    Meeting,
    MeetingParticipant,
    MeetingViewer,
    Task,
    TaskCollaborator,
    TaskViewer,
    User,
    get_ancestor_dept_ids,
    get_db,
    get_descendant_dept_ids,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------- #
# Password / Token
# --------------------------------------------------------------------------- #
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        return False


# 시드 데이터에 사용된 기본 비밀번호 목록 — 실 운영 전 반드시 변경해야 합니다.
_SEED_PASSWORDS = {"admin123", "leader123", "member123"}


def is_using_default_password(user: User) -> bool:
    """사용자가 시드 기본 비밀번호를 아직 쓰고 있는지 확인한다."""
    if getattr(user, "uses_default_password", None) is not None:
        return bool(user.uses_default_password)
    return is_seed_password_hash(user.password_hash)


def is_seed_password_hash(password_hash: str) -> bool:
    return any(verify_password(pw, password_hash) for pw in _SEED_PASSWORDS)


def mark_password_state(user: User, plain: str) -> None:
    user.uses_default_password = plain in _SEED_PASSWORDS


def create_access_token(user: User, *, remember: bool = False) -> tuple[str, int]:
    """(access_token, expires_in_seconds) 반환. remember 이면 설정된 일수, 아니면 기본 만료."""
    minutes = (
        settings.remember_token_expire_days * 24 * 60
        if remember
        else settings.access_token_expire_minutes
    )
    expires_delta = timedelta(minutes=minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user.user_id,
        "name": user.user_name,
        "role": user.role_level,
        "dept_id": user.dept_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="토큰이 만료되었습니다."
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다."
        ) from exc


def authenticate_user(db: Session, user_id: str, password: str) -> User | None:
    user = db.get(User, (user_id or "").strip())
    if user and verify_password(password, user.password_hash):
        return user
    return None


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #
def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    user = db.get(User, payload.get("sub", ""))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다."
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_roles(*roles: str):
    """특정 역할만 접근 가능한 라우트용 의존성 팩토리."""

    def _guard(user: CurrentUser) -> User:
        if user.role_level not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한이 없습니다."
            )
        return user

    return _guard


# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #
def scope_dept_ids(db: Session, user: User) -> list[int] | None:
    """접근 가능한 부서 ID 목록. ADMIN 은 None(전체)."""
    if user.role_level == "ADMIN":
        return None
    if user.role_level == "LEADER":
        return get_descendant_dept_ids(db, user.dept_id)
    return [user.dept_id] if user.dept_id is not None else []


def _subject_visible(model, db: Session, user: User):
    user_hit = exists().where(model.task_id == Task.task_id, model.user_id == user.user_id)
    ancestors = get_ancestor_dept_ids(db, user.dept_id) or [-1]
    dept_hit = exists().where(model.task_id == Task.task_id, model.dept_id.in_(ancestors))
    return or_(user_hit, dept_hit)


def _matches_subject(item, db: Session, user: User) -> bool:
    if item.user_id == user.user_id:
        return True
    if item.dept_id and user.dept_id:
        return item.dept_id in get_ancestor_dept_ids(db, user.dept_id)
    return False


def _collaborator_visible(db: Session, user: User):
    return _subject_visible(TaskCollaborator, db, user)


def _viewer_allowlisted(db: Session, user: User):
    return or_(Task.assigned_to == user.user_id, _subject_visible(TaskViewer, db, user))


def _has_viewers():
    return exists().where(TaskViewer.task_id == Task.task_id)


def is_task_collaborator(db: Session, user: User, task: Task) -> bool:
    return any(_matches_subject(item, db, user) for item in task.collaborators)


def is_task_viewer(db: Session, user: User, task: Task) -> bool:
    if task.assigned_to == user.user_id:
        return True
    return any(_matches_subject(item, db, user) for item in task.viewers)


def is_person_collaborator(task: Task, user: User) -> bool:
    return any(item.user_id == user.user_id for item in task.collaborators)


def _with_card_policy(stmt: Select, db: Session, user: User, default_clause):
    """열람 대상이 있으면 담당자+지정 대상만, 없으면 기본 정책을 적용한다."""
    if user.role_level == "ADMIN":
        return stmt
    restricted = _has_viewers()
    return stmt.where(
        or_(and_(not_(restricted), default_clause), and_(restricted, _viewer_allowlisted(db, user)))
    )


def visible_tasks_stmt(
    db: Session, user: User, *, team_view: bool = False, include_deleted: bool = False
) -> Select:
    """RBAC 이 적용된 Task 조회 statement."""
    stmt = select(Task)
    if not include_deleted:
        stmt = stmt.where(Task.deleted_at.is_(None))
    collab = _collaborator_visible(db, user)
    if user.role_level == "ADMIN":
        return stmt
    if user.role_level == "LEADER":
        dept_ids = get_descendant_dept_ids(db, user.dept_id) or [-1]
        default = or_(Task.dept_id.in_(dept_ids), Task.assigned_to == user.user_id, collab)
        return _with_card_policy(stmt, db, user, default)
    if team_view and user.dept_id is not None:
        default = or_(Task.assigned_to == user.user_id, Task.dept_id == user.dept_id, collab)
        return _with_card_policy(stmt, db, user, default)
    return _with_card_policy(stmt, db, user, or_(Task.assigned_to == user.user_id, collab))


def get_visible_tasks(
    db: Session, user: User, *, team_view: bool = False, skip_activities: bool = False
) -> list[Task]:
    stmt = visible_tasks_stmt(db, user, team_view=team_view).order_by(
        Task.due_date.is_(None), Task.due_date
    )
    if skip_activities:
        stmt = stmt.options(noload(Task.activities))
    return list(db.scalars(stmt).unique().all())


def get_deleted_tasks(db: Session, user: User, *, skip_activities: bool = False) -> list[Task]:
    """권한 범위 안에서 삭제 후 1년 이내 보관 중인 업무."""
    stmt = (
        visible_tasks_stmt(db, user, include_deleted=True)
        .where(Task.deleted_at.is_not(None))
        .order_by(Task.deleted_at.desc())
    )
    if skip_activities:
        stmt = stmt.options(noload(Task.activities))
    return list(db.scalars(stmt).unique().all())


def can_view_task(db: Session, user: User, task: Task) -> bool:
    if user.role_level == "ADMIN":
        return True
    if task.viewers:
        return is_task_viewer(db, user, task)
    if user.role_level == "LEADER":
        return (
            task.dept_id in get_descendant_dept_ids(db, user.dept_id)
            or task.assigned_to == user.user_id
            or is_task_collaborator(db, user, task)
        )
    if task.assigned_to == user.user_id:
        return True
    if is_task_collaborator(db, user, task):
        return True
    return bool(user.dept_id and task.dept_id == user.dept_id)


def can_edit_task(db: Session, user: User, task: Task) -> bool:
    """구성원은 본인 담당·사람 공동작업자, 조직장은 관할 부서, 관리자는 전체 수정 가능."""
    if not can_view_task(db, user, task):
        return False
    if user.role_level == "ADMIN":
        return True
    if user.role_level == "LEADER":
        return (
            task.dept_id in get_descendant_dept_ids(db, user.dept_id)
            or task.assigned_to == user.user_id
            or is_person_collaborator(task, user)
        )
    return task.assigned_to == user.user_id or is_person_collaborator(task, user)


def assert_can_edit(db: Session, user: User, task: Task) -> None:
    if not can_edit_task(db, user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{task.task_id} 업무를 수정할 권한이 없습니다.",
        )


def visible_users(db: Session, user: User) -> list[User]:
    dept_ids = scope_dept_ids(db, user)
    stmt = select(User).order_by(User.dept_id, User.user_name)
    if dept_ids is not None:
        stmt = stmt.where(User.dept_id.in_(dept_ids or [-1]))
    return list(db.scalars(stmt).unique().all())


def visible_departments(db: Session, user: User) -> list[Department]:
    dept_ids = scope_dept_ids(db, user)
    stmt = select(Department).order_by(Department.dept_id)
    if dept_ids is not None:
        stmt = stmt.where(Department.dept_id.in_(dept_ids or [-1]))
    return list(db.scalars(stmt).unique().all())


def visible_meetings(db: Session, user: User) -> list[Meeting]:
    """작성자·관리자 + 지정된 참여자/열람자만 회의록을 본다."""
    stmt = select(Meeting).order_by(Meeting.created_at.desc())
    if user.role_level != "ADMIN":
        ancestors = get_ancestor_dept_ids(db, user.dept_id) or [-1]
        participant_hit = exists().where(
            MeetingParticipant.meeting_id == Meeting.meeting_id,
            or_(
                MeetingParticipant.user_id == user.user_id,
                MeetingParticipant.dept_id.in_(ancestors),
            ),
        )
        viewer_hit = exists().where(
            MeetingViewer.meeting_id == Meeting.meeting_id,
            or_(
                MeetingViewer.user_id == user.user_id,
                MeetingViewer.dept_id.in_(ancestors),
            ),
        )
        stmt = stmt.where(
            or_(Meeting.created_by == user.user_id, participant_hit, viewer_hit)
        )
    return list(db.scalars(stmt).unique().all())


def can_view_meeting(db: Session, user: User, meeting: Meeting) -> bool:
    if user.role_level == "ADMIN":
        return True
    if meeting.created_by == user.user_id:
        return True
    return any(
        _matches_subject(item, db, user)
        for item in [*meeting.participants, *meeting.viewers]
    )


def can_manage_meeting(user: User, meeting: Meeting) -> bool:
    return user.role_level == "ADMIN" or meeting.created_by == user.user_id
