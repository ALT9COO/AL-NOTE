"""인증(bcrypt) · 세션 관리 · RBAC 유틸리티."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import bcrypt
import streamlit as st
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from config import ROLE_LABELS
from database import (
    Department,
    Meeting,
    Task,
    User,
    get_descendant_dept_ids,
    get_session,
)

SESSION_KEY = "auth_user"


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #
def _to_dict(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "user_name": user.user_name,
        "role_level": user.role_level,
        "dept_id": user.dept_id,
        "dept_name": user.department.dept_name if user.department else "-",
    }


def authenticate(user_id: str, password: str) -> dict[str, Any] | None:
    with get_session() as session:
        user = session.get(User, user_id.strip())
        if user and verify_password(password, user.password_hash):
            return _to_dict(user)
    return None


def login(user: dict[str, Any]) -> None:
    st.session_state[SESSION_KEY] = user


def logout() -> None:
    for key in list(st.session_state.keys()):
        if key != "_pages":
            del st.session_state[key]


def current_user() -> dict[str, Any] | None:
    return st.session_state.get(SESSION_KEY)


def require_login() -> dict[str, Any]:
    user = current_user()
    if not user:
        st.stop()
    return user  # type: ignore[return-value]


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #
def scope_dept_ids(session: Session, user: dict[str, Any]) -> list[int] | None:
    """사용자가 접근 가능한 부서 ID 목록. ADMIN 은 None(=전체)."""
    role = user["role_level"]
    if role == "ADMIN":
        return None
    if role == "LEADER":
        return get_descendant_dept_ids(session, user["dept_id"])
    return [user["dept_id"]] if user["dept_id"] is not None else []


def visible_tasks_stmt(session: Session, user: dict[str, Any]) -> Select:
    """RBAC 이 적용된 Task 조회 statement."""
    stmt = select(Task)
    role = user["role_level"]
    if role == "ADMIN":
        return stmt
    if role == "LEADER":
        dept_ids = get_descendant_dept_ids(session, user["dept_id"])
        return stmt.where(
            or_(Task.dept_id.in_(dept_ids or [-1]), Task.assigned_to == user["user_id"])
        )
    # MEMBER: 본인 업무 + 소속 팀 업무(조회만)
    return stmt.where(
        or_(Task.assigned_to == user["user_id"], Task.dept_id == (user["dept_id"] or -1))
    )


def get_visible_tasks(session: Session, user: dict[str, Any]) -> list[Task]:
    stmt = visible_tasks_stmt(session, user).order_by(Task.due_date.is_(None), Task.due_date)
    return list(session.scalars(stmt).unique().all())


def can_edit_task(session: Session, user: dict[str, Any], task: Task) -> bool:
    """MEMBER 는 본인 담당 업무만 수정 가능, LEADER 는 관할 부서, ADMIN 은 전체."""
    role = user["role_level"]
    if role == "ADMIN":
        return True
    if role == "LEADER":
        return (
            task.dept_id in get_descendant_dept_ids(session, user["dept_id"])
            or task.assigned_to == user["user_id"]
        )
    return task.assigned_to == user["user_id"]


def can_create_task(user: dict[str, Any]) -> bool:
    return user["role_level"] in {"ADMIN", "LEADER", "MEMBER"}


def assignable_users(session: Session, user: dict[str, Any]) -> list[User]:
    """업무를 배정할 수 있는 사용자 목록 (RBAC 범위 내)."""
    dept_ids = scope_dept_ids(session, user)
    stmt = select(User).order_by(User.dept_id, User.user_name)
    if dept_ids is not None:
        stmt = stmt.where(User.dept_id.in_(dept_ids or [-1]))
    return list(session.scalars(stmt).unique().all())


def visible_departments(session: Session, user: dict[str, Any]) -> list[Department]:
    dept_ids = scope_dept_ids(session, user)
    stmt = select(Department).order_by(Department.dept_id)
    if dept_ids is not None:
        stmt = stmt.where(Department.dept_id.in_(dept_ids or [-1]))
    return list(session.scalars(stmt).unique().all())


def visible_meetings(session: Session, user: dict[str, Any]) -> list[Meeting]:
    stmt = select(Meeting).order_by(Meeting.created_at.desc())
    role = user["role_level"]
    if role != "ADMIN":
        dept_ids: Sequence[int] = scope_dept_ids(session, user) or [-1]
        stmt = stmt.where(
            or_(Meeting.dept_id.in_(dept_ids), Meeting.created_by == user["user_id"])
        )
    return list(session.scalars(stmt).unique().all())


# --------------------------------------------------------------------------- #
# Login UI
# --------------------------------------------------------------------------- #
def render_login_page(app_title: str) -> None:
    st.markdown(
        """
        <style>
        .login-hero {
            padding: 2.2rem 2rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 60%, #06b6d4 100%);
            color: #fff;
            margin-bottom: 1.5rem;
        }
        .login-hero h1 { margin: 0 0 .4rem 0; font-size: 1.9rem; }
        .login-hero p { margin: 0; opacity: .9; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.image(str(Path(__file__).resolve().parent / "al-note-icon.png"), width=96)
        st.markdown(
            f"""
            <div class="login-hero">
                <h1>{app_title}</h1>
                <p>회의 한 번으로 업무 현황까지 자동 업데이트</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            user_id = st.text_input("아이디", placeholder="admin")
            password = st.text_input("비밀번호", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("로그인", width="stretch", type="primary")

        if submitted:
            user = authenticate(user_id, password)
            if user:
                login(user)
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

        with st.expander("테스트 계정 보기"):
            st.markdown(
                """
                | 역할 | 아이디 | 비밀번호 |
                |---|---|---|
                | ADMIN (관리자) | `admin` | `admin123` |
                | LEADER (팀장) | `leader1` | `leader123` |
                | MEMBER (팀원) | `member1` | `member123` |
                | MEMBER (팀원) | `member2` | `member123` |
                """
            )
