"""AI 주기별 요약 대시보드 (주간 / 월간 / 연간)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from ai_engine import AIEngineError, generate_period_report
from auth import get_visible_tasks, scope_dept_ids
from config import STATUSES
from database import Task, department_map, get_session, user_map

PERIODS = {"주간": 7, "월간": 30, "분기": 90, "연간": 365}


def _period_range(period: str, anchor: date) -> tuple[date, date]:
    if period == "주간":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "월간":
        start = anchor.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, next_month - timedelta(days=1)
    if period == "분기":
        q_start_month = 3 * ((anchor.month - 1) // 3) + 1
        start = anchor.replace(month=q_start_month, day=1)
        end_month = q_start_month + 3
        end = (
            date(anchor.year + 1, 1, 1)
            if end_month > 12
            else date(anchor.year, end_month, 1)
        ) - timedelta(days=1)
        return start, end
    return date(anchor.year, 1, 1), date(anchor.year, 12, 31)


def _in_period(task: Task, start: date, end: date) -> bool:
    """기간 내에 갱신되었거나 마감 예정인 업무를 대상으로 집계한다."""
    updated = task.updated_at.date() if isinstance(task.updated_at, datetime) else None
    if updated and start <= updated <= end:
        return True
    if task.due_date and start <= task.due_date <= end:
        return True
    if task.start_date and task.due_date and task.start_date <= end and task.due_date >= start:
        return True
    return False


def _to_rows(tasks: list[Task], names: dict[str, str], depts: dict[int, str]) -> list[dict[str, Any]]:
    today = date.today()
    rows = []
    for t in tasks:
        delayed = bool(t.due_date and t.due_date < today and t.status != "완료")
        rows.append(
            {
                "task_id": t.task_id,
                "task_name": t.task_name,
                "assignee_name": names.get(t.assigned_to, "미지정"),
                "dept_name": depts.get(t.dept_id, "-"),
                "status": t.status,
                "progress": int(t.progress or 0),
                "start_date": t.start_date.isoformat() if t.start_date else "",
                "due_date": t.due_date.isoformat() if t.due_date else "",
                "issues": (t.issues or "").strip(),
                "is_delayed": delayed,
                "delay_days": (today - t.due_date).days if delayed and t.due_date else 0,
            }
        )
    return rows


def _build_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    stats: dict[str, Any] = {
        "total": total,
        "avg_progress": round(sum(r["progress"] for r in rows) / total) if total else 0,
        "delayed": sum(1 for r in rows if r["is_delayed"]),
        "with_issues": sum(1 for r in rows if r["issues"]),
    }
    for status in STATUSES:
        stats[status] = sum(1 for r in rows if r["status"] == status)
    stats["completion_rate"] = round(stats["완료"] / total * 100) if total else 0

    by_person: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = by_person.setdefault(
            row["assignee_name"], {"count": 0, "progress_sum": 0, "delayed": 0, "done": 0}
        )
        entry["count"] += 1
        entry["progress_sum"] += row["progress"]
        entry["delayed"] += int(row["is_delayed"])
        entry["done"] += int(row["status"] == "완료")
    stats["by_assignee"] = {
        name: {
            "업무수": v["count"],
            "평균진행률": round(v["progress_sum"] / v["count"]),
            "완료": v["done"],
            "지연": v["delayed"],
        }
        for name, v in by_person.items()
    }
    return stats


def render(user: dict[str, Any]) -> None:
    st.subheader("📊 AI 주기별 요약 리포트")
    st.caption("권한 범위 내 업무 데이터를 집계하고, LLM 이 경영진 보고용 리포트를 생성합니다.")

    col1, col2, col3 = st.columns([1, 1, 2])
    period = col1.selectbox("보고 주기", list(PERIODS.keys()), index=0)
    anchor = col2.date_input("기준일", value=date.today(), format="YYYY-MM-DD")
    start, end = _period_range(period, anchor)
    col3.info(f"집계 기간: **{start} ~ {end}**", icon="🗓️")

    with get_session() as session:
        tasks = get_visible_tasks(session, user)
        names = user_map(session)
        depts = department_map(session)
        allowed_depts = scope_dept_ids(session, user)

    dept_choices = ["전체"] + [
        depts[d] for d in sorted(depts) if allowed_depts is None or d in allowed_depts
    ]
    selected_dept = st.selectbox("부서 범위", dept_choices, index=0)

    scoped = [t for t in tasks if _in_period(t, start, end)]
    if selected_dept != "전체":
        scoped = [t for t in scoped if depts.get(t.dept_id) == selected_dept]

    rows = _to_rows(scoped, names, depts)
    stats = _build_stats(rows)

    if not rows:
        st.warning("선택한 기간/범위에 해당하는 업무가 없습니다. 기간을 넓혀보세요.")
        return

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("전체 업무", f"{stats['total']}건")
    m2.metric("완료율", f"{stats['completion_rate']}%")
    m3.metric("평균 진행률", f"{stats['avg_progress']}%")
    m4.metric("지연 업무", f"{stats['delayed']}건", delta_color="inverse")
    m5.metric("이슈 등록", f"{stats['with_issues']}건")

    st.divider()

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("##### 상태별 업무 분포")
        status_df = pd.DataFrame(
            {"상태": STATUSES, "건수": [stats[s] for s in STATUSES]}
        ).set_index("상태")
        st.bar_chart(status_df, color="#3b82f6", height=280)

    with chart_col2:
        st.markdown("##### 담당자별 평균 진행률")
        person_df = pd.DataFrame(
            [
                {"담당자": name, "평균진행률": value["평균진행률"], "업무수": value["업무수"]}
                for name, value in stats["by_assignee"].items()
            ]
        ).set_index("담당자")
        st.bar_chart(person_df[["평균진행률"]], color="#22c55e", height=280)

    st.markdown("##### 업무 상세")
    detail_df = pd.DataFrame(rows)[
        ["task_id", "task_name", "assignee_name", "dept_name", "status", "progress", "due_date", "delay_days", "issues"]
    ].rename(
        columns={
            "task_id": "ID",
            "task_name": "업무명",
            "assignee_name": "담당자",
            "dept_name": "부서",
            "status": "상태",
            "progress": "진행률",
            "due_date": "마감일",
            "delay_days": "지연일",
            "issues": "이슈",
        }
    )
    st.dataframe(
        detail_df,
        width="stretch",
        hide_index=True,
        column_config={
            "진행률": st.column_config.ProgressColumn("진행률", min_value=0, max_value=100, format="%d%%")
        },
    )

    st.divider()
    st.markdown("##### 🤖 AI 경영 요약 리포트")

    scope_label = f"{selected_dept} ({user['role_level']} 권한)"
    period_label = f"{period} ({start} ~ {end})"
    report_key = f"report_{period}_{start}_{end}_{selected_dept}"

    if st.button("리포트 생성", type="primary", width="stretch"):
        with st.spinner("AI 가 리포트를 작성하는 중입니다..."):
            try:
                st.session_state[report_key] = generate_period_report(
                    period_label, scope_label, stats, rows
                )
            except AIEngineError as exc:
                st.error(str(exc))

    report = st.session_state.get(report_key)
    if report:
        with st.container(border=True):
            st.markdown(report)
        st.download_button(
            "📥 리포트 다운로드 (.md)",
            data=report,
            file_name=f"AI리포트_{period}_{start}_{end}.md",
            mime="text/markdown",
            width="stretch",
        )
