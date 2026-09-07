"""진행 현황 칸반 보드 컴포넌트."""

from __future__ import annotations

import html
from datetime import date
from typing import Any

import streamlit as st

from auth import assignable_users, can_edit_task, get_visible_tasks, visible_departments
from config import STATUS_COLORS, STATUS_DEFAULT_PROGRESS, STATUSES
from database import Task, department_map, get_session, next_task_id, user_map

_CSS = """
<style>
.kb-col-head {
    display:flex; align-items:center; justify-content:space-between;
    padding:.55rem .8rem; border-radius:10px 10px 0 0; color:#fff; font-weight:700;
    font-size:.92rem; letter-spacing:.02em;
}
.kb-col-body { background:#f1f5f9; border-radius:0 0 10px 10px; padding:.5rem; min-height:60px; }
.kb-count { background:rgba(255,255,255,.28); border-radius:999px; padding:.05rem .5rem; font-size:.78rem; }
.kb-card {
    background:#fff; border-radius:10px; padding:.7rem .8rem; margin-bottom:.5rem;
    box-shadow:0 1px 3px rgba(15,23,42,.12); border-left:5px solid #cbd5e1;
}
.kb-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:.25rem; }
.kb-id { font-size:.72rem; font-weight:700; color:#64748b; letter-spacing:.03em; }
.kb-due { font-size:.7rem; padding:.08rem .45rem; border-radius:999px; background:#e2e8f0; color:#475569; }
.kb-due.warn { background:#fef3c7; color:#92400e; }
.kb-due.late { background:#fee2e2; color:#b91c1c; font-weight:700; }
.kb-title { font-size:.95rem; font-weight:650; color:#0f172a; line-height:1.32; margin-bottom:.3rem; }
.kb-meta { font-size:.76rem; color:#475569; margin-bottom:.4rem; }
.kb-bar { background:#e2e8f0; border-radius:999px; height:7px; overflow:hidden; }
.kb-bar > div { height:100%; border-radius:999px; }
.kb-pct { font-size:.7rem; color:#64748b; text-align:right; margin-top:.15rem; }
.kb-issue {
    margin-top:.35rem; font-size:.74rem; color:#b45309; background:#fffbeb;
    border-radius:6px; padding:.28rem .45rem; line-height:1.3;
}
.kb-empty { color:#94a3b8; font-size:.8rem; text-align:center; padding:1rem .5rem; }
</style>
"""


# --------------------------------------------------------------------------- #
# 데이터 조작
# --------------------------------------------------------------------------- #
def apply_task_change(task_id: str, **fields: Any) -> None:
    with get_session() as session:
        task = session.get(Task, task_id)
        if not task:
            return
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)


def delete_task(task_id: str) -> None:
    with get_session() as session:
        task = session.get(Task, task_id)
        if task:
            session.delete(task)


# --------------------------------------------------------------------------- #
# 카드 렌더링
# --------------------------------------------------------------------------- #
def _due_badge(due: date | None) -> str:
    if not due:
        return '<span class="kb-due">기한 없음</span>'
    delta = (due - date.today()).days
    if delta < 0:
        cls, text = "late", f"D+{abs(delta)} 지연"
    elif delta <= 3:
        cls, text = "warn", f"D-{delta}"
    else:
        cls, text = "", f"D-{delta}"
    return f'<span class="kb-due {cls}">{due.strftime("%m/%d")} · {text}</span>'


def _card_html(task: Task, assignee_name: str, dept_name: str) -> str:
    color = STATUS_COLORS.get(task.status, "#94a3b8")
    issue = (
        f'<div class="kb-issue">⚠️ {html.escape(task.issues.strip())}</div>'
        if task.issues and task.issues.strip()
        else ""
    )
    return f"""
    <div class="kb-card" style="border-left-color:{color}">
        <div class="kb-top">
            <span class="kb-id">{html.escape(task.task_id)}</span>
            {_due_badge(task.due_date)}
        </div>
        <div class="kb-title">{html.escape(task.task_name)}</div>
        <div class="kb-meta">👤 {html.escape(assignee_name)} · 🏢 {html.escape(dept_name)}</div>
        <div class="kb-bar"><div style="width:{max(0, min(100, task.progress or 0))}%;background:{color}"></div></div>
        <div class="kb-pct">{task.progress or 0}%</div>
        {issue}
    </div>
    """


def _card_controls(task: Task, user: dict[str, Any], editable: bool) -> None:
    if not editable:
        st.caption("🔒 조회 권한만 있습니다")
        return

    idx = STATUSES.index(task.status) if task.status in STATUSES else 0
    left, mid, right = st.columns([1, 2, 1])

    with left:
        if st.button("◀", key=f"prev_{task.task_id}", disabled=idx == 0, help="이전 단계로 이동",
                     width="stretch"):
            new_status = STATUSES[idx - 1]
            apply_task_change(
                task.task_id, status=new_status, progress=STATUS_DEFAULT_PROGRESS[new_status]
            )
            st.rerun()

    with right:
        if st.button("▶", key=f"next_{task.task_id}", disabled=idx == len(STATUSES) - 1,
                     help="다음 단계로 이동", width="stretch"):
            new_status = STATUSES[idx + 1]
            apply_task_change(
                task.task_id, status=new_status, progress=STATUS_DEFAULT_PROGRESS[new_status]
            )
            st.rerun()

    with mid:
        with st.popover("수정", width="stretch"):
            st.markdown(f"**{task.task_id}** · {task.task_name}")
            # 폼으로 묶어야 입력 직후 첫 클릭에 값이 함께 반영된다.
            with st.form(f"quick_{task.task_id}"):
                new_status = st.selectbox("상태", STATUSES, index=idx)
                new_progress = st.slider("진행률(%)", 0, 100, int(task.progress or 0), step=5)
                new_issue = st.text_area("최신 이슈", value=task.issues or "", height=80)
                col_a, col_b = st.columns(2)
                saved = col_a.form_submit_button("저장", type="primary", width="stretch")
                detail = col_b.form_submit_button("상세 편집", width="stretch")

            if saved:
                apply_task_change(
                    task.task_id, status=new_status, progress=new_progress, issues=new_issue
                )
                st.rerun()
            if detail:
                open_task_editor(user, task.task_id)


# --------------------------------------------------------------------------- #
# 등록 / 편집 폼
# --------------------------------------------------------------------------- #
def _task_form(user: dict[str, Any], task_id: str | None = None) -> None:
    with get_session() as session:
        task = session.get(Task, task_id) if task_id else None
        users = assignable_users(session, user)
        depts = visible_departments(session, user)

    if task_id and not task:
        st.error("업무를 찾을 수 없습니다.")
        return

    user_options = [u.user_id for u in users] or [user["user_id"]]
    user_labels = {u.user_id: f"{u.user_name} ({u.user_id})" for u in users}
    user_labels.setdefault(user["user_id"], f"{user['user_name']} ({user['user_id']})")

    dept_options = [d.dept_id for d in depts] or ([user["dept_id"]] if user["dept_id"] else [])
    dept_labels = {d.dept_id: d.dept_name for d in depts}

    with st.form(f"task_form_{task_id or 'new'}"):
        name = st.text_input("업무명 *", value=task.task_name if task else "")
        description = st.text_area("설명", value=(task.description or "") if task else "", height=90)

        col1, col2 = st.columns(2)
        with col1:
            assignee = st.selectbox(
                "담당자",
                user_options,
                index=user_options.index(task.assigned_to)
                if task and task.assigned_to in user_options
                else 0,
                format_func=lambda x: user_labels.get(x, x),
            )
            status = st.selectbox(
                "상태",
                STATUSES,
                index=STATUSES.index(task.status) if task and task.status in STATUSES else 0,
            )
            start = st.date_input(
                "시작일", value=(task.start_date if task else date.today()), format="YYYY-MM-DD"
            )
        with col2:
            dept_id = st.selectbox(
                "부서",
                dept_options,
                index=dept_options.index(task.dept_id)
                if task and task.dept_id in dept_options
                else 0,
                format_func=lambda x: dept_labels.get(x, str(x)),
            ) if dept_options else None
            progress = st.slider("진행률(%)", 0, 100, int(task.progress) if task else 0, step=5)
            due = st.date_input(
                "마감일", value=(task.due_date if task else None), format="YYYY-MM-DD"
            )

        issues = st.text_area("최신 이슈", value=(task.issues or "") if task else "", height=70)

        col_save, col_del = st.columns([3, 1])
        saved = col_save.form_submit_button("저장", type="primary", width="stretch")
        deleted = (
            col_del.form_submit_button("삭제", width="stretch") if task else False
        )

    if saved:
        if not name.strip():
            st.error("업무명을 입력하세요.")
            return
        with get_session() as session:
            if task:
                target = session.get(Task, task.task_id)
            else:
                target = Task(task_id=next_task_id(session))
                session.add(target)
            target.task_name = name.strip()
            target.description = description
            target.assigned_to = assignee
            target.dept_id = dept_id
            target.status = status
            target.progress = progress
            target.start_date = start
            target.due_date = due
            target.issues = issues
        st.success("저장되었습니다.")
        st.rerun()

    if deleted and task:
        delete_task(task.task_id)
        st.rerun()


def open_task_editor(user: dict[str, Any], task_id: str | None = None) -> None:
    """모달(st.dialog) 지원 시 모달로, 아니면 인라인 폼으로 편집 화면을 연다."""
    if hasattr(st, "dialog"):

        @st.dialog("업무 수정" if task_id else "새 업무 등록", width="large")
        def _dialog() -> None:
            _task_form(user, task_id)

        _dialog()
    else:  # pragma: no cover - 구버전 streamlit fallback
        st.session_state["inline_task_editor"] = task_id or "__new__"


# --------------------------------------------------------------------------- #
# 메인 렌더러
# --------------------------------------------------------------------------- #
def render(user: dict[str, Any]) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    header, action = st.columns([4, 1])
    with header:
        st.subheader("📋 진행 현황 칸반 보드")
        st.caption(f"{user['dept_name']} · {user['role_level']} 권한 범위의 업무만 표시됩니다.")
    with action:
        st.write("")
        if st.button("➕ 새 업무", type="primary", width="stretch"):
            open_task_editor(user, None)

    with get_session() as session:
        tasks = get_visible_tasks(session, user)
        editable_map = {t.task_id: can_edit_task(session, user, t) for t in tasks}
        names = user_map(session)
        depts = department_map(session)

    if st.session_state.get("inline_task_editor"):  # pragma: no cover - fallback 경로
        target = st.session_state.pop("inline_task_editor")
        with st.expander("업무 편집", expanded=True):
            _task_form(user, None if target == "__new__" else target)

    with st.expander("🔎 필터", expanded=False):
        col1, col2, col3 = st.columns([2, 2, 1])
        keyword = col1.text_input("검색 (업무명 / ID)", key="kb_kw")
        assignee_filter = col2.multiselect(
            "담당자",
            sorted({t.assigned_to for t in tasks if t.assigned_to}),
            format_func=lambda x: names.get(x, x),
            key="kb_assignee",
        )
        mine_only = col3.checkbox("내 업무만", key="kb_mine")

    filtered = []
    for task in tasks:
        if keyword and keyword.lower() not in f"{task.task_id} {task.task_name}".lower():
            continue
        if assignee_filter and task.assigned_to not in assignee_filter:
            continue
        if mine_only and task.assigned_to != user["user_id"]:
            continue
        filtered.append(task)

    total = len(filtered)
    done = sum(1 for t in filtered if t.status == "완료")
    delayed = sum(
        1 for t in filtered if t.due_date and t.due_date < date.today() and t.status != "완료"
    )
    avg = round(sum(t.progress or 0 for t in filtered) / total) if total else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("전체 업무", f"{total}건")
    m2.metric("완료", f"{done}건")
    m3.metric("지연", f"{delayed}건", delta=None if not delayed else f"-{delayed}", delta_color="inverse")
    m4.metric("평균 진행률", f"{avg}%")

    st.divider()

    columns = st.columns(len(STATUSES), gap="small")
    for col, status in zip(columns, STATUSES):
        bucket = [t for t in filtered if t.status == status]
        color = STATUS_COLORS[status]
        with col:
            st.markdown(
                f'<div class="kb-col-head" style="background:{color}">'
                f"<span>{status}</span><span class='kb-count'>{len(bucket)}</span></div>",
                unsafe_allow_html=True,
            )
            st.markdown('<div class="kb-col-body">', unsafe_allow_html=True)
            if not bucket:
                st.markdown('<div class="kb-empty">업무 없음</div>', unsafe_allow_html=True)
            for task in bucket:
                st.markdown(
                    _card_html(
                        task,
                        names.get(task.assigned_to, "미지정"),
                        depts.get(task.dept_id, "-"),
                    ),
                    unsafe_allow_html=True,
                )
                _card_controls(task, user, editable_map.get(task.task_id, False))
            st.markdown("</div>", unsafe_allow_html=True)
