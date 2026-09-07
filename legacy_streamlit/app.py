"""AI Note — 업무 관리 · AI 회의록 · 자동 업무 업데이트 대시보드.

실행: streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
from sqlalchemy import select

from ai_engine import ai_status
from auth import (
    current_user,
    hash_password,
    logout,
    render_login_page,
    role_label,
)
from components import ai_analytics, kanban, meeting_room
from config import ROLES, settings
from database import Department, User, get_session, init_db

_BRAND_ICON = Path(__file__).resolve().parent / "al-note-icon.png"

st.set_page_config(
    page_title=settings.app_title,
    page_icon=str(_BRAND_ICON) if _BRAND_ICON.exists() else "📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

GLOBAL_CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 2.2rem; padding-bottom: 3rem;}
div[data-testid="stMetricValue"] {font-size: 1.5rem;}
.sb-profile {
    background: linear-gradient(135deg,#1e3a8a,#3b82f6);
    color:#fff; padding:.9rem 1rem; border-radius:12px; margin-bottom:.8rem;
}
.sb-profile .name {font-weight:700; font-size:1.02rem;}
.sb-profile .meta {font-size:.78rem; opacity:.9;}
.sb-badge {
    display:inline-block; background:rgba(255,255,255,.22); border-radius:999px;
    padding:.05rem .5rem; font-size:.72rem; margin-top:.3rem;
}
</style>
"""


@st.cache_resource
def _bootstrap() -> bool:
    init_db()
    return True


def _render_sidebar(user: dict[str, Any]) -> str:
    with st.sidebar:
        st.markdown(
            f"""
            <div class="sb-profile">
                <div class="name">{user['user_name']}</div>
                <div class="meta">{user['dept_name']} · {user['user_id']}</div>
                <div class="sb-badge">{role_label(user['role_level'])} ({user['role_level']})</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        menu_items = ["칸반 보드", "AI 회의실", "AI 리포트"]
        menu_icons = ["kanban", "mic", "graph-up"]
        if user["role_level"] == "ADMIN":
            menu_items.append("관리자")
            menu_icons.append("gear")

        # ?page=AI 리포트 형태의 딥링크 지원
        current = st.query_params.get("page", menu_items[0])
        default_index = menu_items.index(current) if current in menu_items else 0

        try:
            from streamlit_option_menu import option_menu

            selected = option_menu(
                menu_title=None,
                options=menu_items,
                icons=menu_icons,
                default_index=default_index,
                styles={
                    "container": {"padding": "0", "background-color": "transparent"},
                    "nav-link": {"font-size": "0.92rem", "padding": "0.5rem 0.8rem"},
                    "nav-link-selected": {"background-color": "#3b82f6"},
                },
            )
        except Exception:  # pragma: no cover - 패키지 미설치 시 fallback
            selected = st.radio(
                "메뉴", menu_items, index=default_index, label_visibility="collapsed"
            )

        if selected != current:
            st.query_params["page"] = selected

        st.divider()
        status = ai_status()
        provider = status["provider"].upper()
        if status["llm_ready"]:
            st.success(f"LLM: {provider} 연결됨", icon="🤖")
        else:
            st.warning(f"LLM: {provider} 키 없음 (데모 모드)", icon="🧪")
        st.caption("STT: " + ("Whisper 연결됨 ✅" if status["stt_ready"] else "데모 전사 사용 🧪"))

        st.divider()
        if st.button("로그아웃", width="stretch"):
            logout()
            st.rerun()

    return selected


def _render_admin(user: dict[str, Any]) -> None:
    st.subheader("⚙️ 관리자 콘솔")
    tab_users, tab_depts = st.tabs(["👥 사용자 관리", "🏢 부서 관리"])

    with tab_users:
        with get_session() as session:
            users = list(session.scalars(select(User).order_by(User.dept_id, User.user_id)).unique())
            depts = list(session.scalars(select(Department).order_by(Department.dept_id)).unique())
            rows = [
                {
                    "아이디": u.user_id,
                    "이름": u.user_name,
                    "부서": u.department.dept_name if u.department else "-",
                    "권한": u.role_level,
                    "가입일": u.created_at.strftime("%Y-%m-%d"),
                }
                for u in users
            ]
        st.dataframe(rows, width="stretch", hide_index=True)

        dept_ids = [d.dept_id for d in depts]
        dept_labels = {d.dept_id: d.dept_name for d in depts}

        with st.expander("➕ 사용자 추가"):
            with st.form("add_user"):
                col1, col2 = st.columns(2)
                new_id = col1.text_input("아이디 *")
                new_name = col2.text_input("이름 *")
                col3, col4 = st.columns(2)
                new_pw = col3.text_input("초기 비밀번호 *", type="password")
                new_role = col4.selectbox("권한", ROLES, index=2)
                new_dept = st.selectbox(
                    "부서", dept_ids, format_func=lambda x: dept_labels.get(x, str(x))
                )
                if st.form_submit_button("생성", type="primary"):
                    if not (new_id.strip() and new_name.strip() and new_pw):
                        st.error("필수 항목을 모두 입력하세요.")
                    else:
                        with get_session() as session:
                            if session.get(User, new_id.strip()):
                                st.error("이미 존재하는 아이디입니다.")
                            else:
                                session.add(
                                    User(
                                        user_id=new_id.strip(),
                                        user_name=new_name.strip(),
                                        password_hash=hash_password(new_pw),
                                        dept_id=new_dept,
                                        role_level=new_role,
                                    )
                                )
                                st.success(f"{new_name} 계정이 생성되었습니다.")
                                st.rerun()

        with st.expander("✏️ 권한 · 부서 · 비밀번호 변경"):
            target_ids = [u.user_id for u in users]
            with st.form("edit_user"):
                target = st.selectbox("대상 사용자", target_ids)
                col1, col2 = st.columns(2)
                role = col1.selectbox("권한", ROLES)
                dept = col2.selectbox(
                    "부서", dept_ids, format_func=lambda x: dept_labels.get(x, str(x))
                )
                reset_pw = st.text_input("새 비밀번호 (변경 시에만 입력)", type="password")
                if st.form_submit_button("적용", type="primary"):
                    with get_session() as session:
                        target_user = session.get(User, target)
                        if target_user:
                            target_user.role_level = role
                            target_user.dept_id = dept
                            if reset_pw:
                                target_user.password_hash = hash_password(reset_pw)
                    st.success("변경되었습니다.")
                    st.rerun()

    with tab_depts:
        with get_session() as session:
            depts = list(session.scalars(select(Department).order_by(Department.dept_id)).unique())
            names = {d.dept_id: d.dept_name for d in depts}
            rows = [
                {
                    "ID": d.dept_id,
                    "부서명": d.dept_name,
                    "상위 부서": names.get(d.parent_dept_id, "-") if d.parent_dept_id else "-",
                }
                for d in depts
            ]
        st.dataframe(rows, width="stretch", hide_index=True)

        with st.form("add_dept"):
            col1, col2 = st.columns(2)
            dept_name = col1.text_input("새 부서명 *")
            parent = col2.selectbox(
                "상위 부서",
                [None] + [d.dept_id for d in depts],
                format_func=lambda x: "없음 (최상위)" if x is None else names.get(x, str(x)),
            )
            if st.form_submit_button("부서 추가", type="primary"):
                if not dept_name.strip():
                    st.error("부서명을 입력하세요.")
                else:
                    with get_session() as session:
                        session.add(
                            Department(dept_name=dept_name.strip(), parent_dept_id=parent)
                        )
                    st.success("부서가 추가되었습니다.")
                    st.rerun()


def main() -> None:
    _bootstrap()
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    user = current_user()
    if not user:
        render_login_page(settings.app_title)
        return

    selected = _render_sidebar(user)

    st.markdown(f"### {settings.app_title}")

    if selected == "칸반 보드":
        kanban.render(user)
    elif selected == "AI 회의실":
        meeting_room.render(user)
    elif selected == "AI 리포트":
        ai_analytics.render(user)
    elif selected == "관리자":
        _render_admin(user)


if __name__ == "__main__":
    main()
