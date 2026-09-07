"""업무 CRUD · 칸반 드래그앤드롭 상태 변경 · 경영 애널리틱스 라우터."""

from __future__ import annotations

import html as html_lib
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ai_engine import AIEngineError, active_config, generate_period_report
from auth import (
    CurrentUser,
    DbSession,
    assert_can_edit,
    can_view_task,
    get_deleted_tasks,
    get_visible_tasks,
    scope_dept_ids,
)
import calendar_service as cal
from config import STATUS_DEFAULT_PROGRESS, STATUSES
from database import AnalyticsReport, CalendarConnection, Department, Task, TaskActivity, User, next_subtask_id, next_task_id
from schemas import (
    AnalyticsSummary,
    AssigneeStat,
    CommentCreate,
    DeptStat,
    ReportEmailRequest,
    ReportEmailResponse,
    ReportRequest,
    ReportResponse,
    SavedReportSummary,
    StatusCount,
    TaskAlertOut,
    TaskCreate,
    TaskOut,
    TaskStatusUpdate,
    TaskUpdate,
    TrendPoint,
    WeekCompareRow,
    WeekOverWeek,
)
from serializers import is_delayed, task_to_out, tasks_to_out
from task_service import (
    add_activity,
    apply_assignee_dept,
    log_task_changes,
    replace_collaborators,
    replace_viewers,
    restore_task_tree,
    soft_delete_task_tree,
    sync_children_to_parent,
    touch_parent_after_child_change,
    recompute_parent_progress,
    active_children,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[TaskOut])
def list_tasks(
    user: CurrentUser,
    db: DbSession,
    scope: Literal["mine", "team"] = "mine",
) -> list[TaskOut]:
    """RBAC 범위 내 업무 조회. 구성원은 scope=team 이면 소속 부서 업무를 조회 전용으로 본다."""
    team_view = scope == "team"
    return tasks_to_out(
        db, user, get_visible_tasks(db, user, team_view=team_view, skip_activities=True), compact=True
    )


@router.get("/deleted", response_model=list[TaskOut])
def list_deleted_tasks(user: CurrentUser, db: DbSession) -> list[TaskOut]:
    """삭제 후 1년 이내 보관 중인 업무. 설정 화면에서 복원한다."""
    return tasks_to_out(db, user, get_deleted_tasks(db, user, skip_activities=True), compact=True)


@router.get("/alerts", response_model=list[TaskAlertOut])
def list_task_alerts(user: CurrentUser, db: DbSession) -> list[TaskAlertOut]:
    """마감 D-3 이내(초과 포함) 미완료 업무. 알림 벨용 경량 목록."""
    today = date.today()
    horizon = today + timedelta(days=3)
    alerts: list[TaskAlertOut] = []
    for task in get_visible_tasks(db, user, team_view=True, skip_activities=True):
        if task.parent_task_id or task.status == "완료" or task.due_date is None:
            continue
        if task.due_date > horizon:
            continue
        alerts.append(
            TaskAlertOut(
                task_id=task.task_id,
                task_name=task.task_name,
                assignee_name=task.assignee.user_name if task.assignee else None,
                due_date=task.due_date,
                days_left=(task.due_date - today).days,
                is_delayed=is_delayed(task),
            )
        )
    alerts.sort(key=lambda item: item.days_left)
    return alerts


@router.post("/{task_id}/restore", response_model=TaskOut)
def restore_task(task_id: str, user: CurrentUser, db: DbSession) -> TaskOut:
    task = _get_task_or_404(db, task_id, include_deleted=True)
    if task.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 복원된 업무입니다.")
    if datetime.now() - task.deleted_at >= timedelta(days=365):
        db.delete(task)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="보관 기간(1년)이 지나 완전히 삭제된 업무입니다.",
        )
    assert_can_edit(db, user, task)
    restore_task_tree(db, task, user.user_id)
    db.commit()
    db.refresh(task)
    return task_to_out(db, user, task, include_children=True)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: CurrentUser, db: DbSession) -> TaskOut:
    parent = None
    if payload.parent_task_id:
        parent = _get_task_or_404(db, payload.parent_task_id)
        assert_can_edit(db, user, parent)
        if parent.parent_task_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="하위 업무 아래에는 다시 하위 업무를 만들 수 없습니다.",
            )

    assigned_to = payload.assigned_to or (parent.assigned_to if parent else None) or user.user_id
    dept_id = payload.dept_id
    if dept_id is None:
        if parent is not None:
            dept_id = parent.dept_id
        else:
            assignee = db.get(User, assigned_to) if assigned_to else None
            dept_id = (assignee.dept_id if assignee else None) or user.dept_id
    allowed = scope_dept_ids(db, user)
    if allowed is not None and dept_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="해당 부서에 업무를 생성할 권한이 없습니다."
        )

    task = Task(
        task_id=next_subtask_id(db, parent.task_id) if parent else next_task_id(db),
        parent_task_id=parent.task_id if parent else None,
        task_name=payload.task_name,
        description=payload.description or "",
        status=parent.status if parent is not None else payload.status,
        progress=int(parent.progress or 0) if parent is not None else payload.progress,
        dept_id=dept_id,
        assigned_to=assigned_to,
        start_date=payload.start_date or (parent.start_date if parent else date.today()),
        due_date=payload.due_date if payload.due_date is not None else (parent.due_date if parent else None),
        issues=payload.issues or "",
    )
    db.add(task)
    db.flush()
    replace_collaborators(db, task, payload.collaborators)
    replace_viewers(db, task, payload.viewers)
    add_activity(
        db,
        task,
        user_id=user.user_id,
        kind="create",
        body="하위 업무가 등록되었습니다." if parent else "업무가 등록되었습니다.",
        progress=task.progress,
        status=task.status,
    )
    if (payload.issues or "").strip():
        add_activity(db, task, user_id=user.user_id, kind="comment", body=payload.issues.strip())
    if parent is not None:
        sync_children_to_parent(db, parent, user.user_id, force_default_progress=False)
    db.commit()
    db.refresh(task)
    return task_to_out(db, user, task, include_children=True)


def _get_task_or_404(db, task_id: str, *, include_deleted: bool = False) -> Task:
    task = db.get(Task, task_id)
    if task is None or (not include_deleted and task.deleted_at is not None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{task_id} 업무를 찾을 수 없습니다."
        )
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, user: CurrentUser, db: DbSession) -> TaskOut:
    task = _get_task_or_404(db, task_id)
    if not can_view_task(db, user, task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="조회 권한이 없습니다.")
    return task_to_out(db, user, task, include_children=True)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, payload: TaskUpdate, user: CurrentUser, db: DbSession) -> TaskOut:
    task = _get_task_or_404(db, task_id)
    assert_can_edit(db, user, task)

    old_status = task.status
    old_progress = int(task.progress or 0)
    old_issues = task.issues or ""

    collaborators = payload.collaborators if "collaborators" in payload.model_fields_set else None
    viewers = payload.viewers if "viewers" in payload.model_fields_set else None
    data = payload.model_dump(exclude_unset=True, exclude={"collaborators", "viewers"})
    has_children = bool(active_children(db, task.task_id))
    if has_children:
        data.pop("progress", None)
    status_changed = "status" in data and data["status"] != old_status
    assigned_changed = "assigned_to" in data
    dept_provided = "dept_id" in data
    for field, value in data.items():
        setattr(task, field, value)
    if assigned_changed:
        apply_assignee_dept(db, task, task.assigned_to, override=not dept_provided)
    if collaborators is not None:
        replace_collaborators(db, task, collaborators)
    if viewers is not None:
        replace_viewers(db, task, viewers)
    log_task_changes(
        db,
        task,
        user.user_id,
        old_status=old_status,
        old_progress=old_progress,
        old_issues=old_issues,
    )
    if status_changed and has_children:
        sync_children_to_parent(db, task, user.user_id, force_default_progress=True)
    elif has_children:
        sync_children_to_parent(db, task, user.user_id, force_default_progress=False)
    elif task.parent_task_id:
        touch_parent_after_child_change(db, task, user.user_id)
    task.updated_at = datetime.now()
    db.commit()
    db.refresh(task)
    return task_to_out(db, user, task, include_children=True)


@router.patch("/{task_id}/status", response_model=TaskOut)
def update_task_status(
    task_id: str, payload: TaskStatusUpdate, user: CurrentUser, db: DbSession
) -> TaskOut:
    """칸반 드래그앤드롭. 할당·진행중·완료만 기본 진행률을 맞추고, 이슈 발생은 유지한다.
    상위 업무를 옮기면 하위 상태도 같이 맞춘다."""
    task = _get_task_or_404(db, task_id)
    assert_can_edit(db, user, task)

    old_status = task.status
    old_progress = int(task.progress or 0)
    has_children = bool(active_children(db, task.task_id))
    task.status = payload.status
    if has_children:
        pass
    elif payload.progress is not None:
        task.progress = payload.progress
    elif payload.status in STATUS_DEFAULT_PROGRESS:
        task.progress = STATUS_DEFAULT_PROGRESS[payload.status]
    log_task_changes(
        db,
        task,
        user.user_id,
        old_status=old_status,
        old_progress=old_progress,
        old_issues=task.issues or "",
    )
    if has_children:
        sync_children_to_parent(
            db, task, user.user_id, force_default_progress=old_status != payload.status
        )
    elif task.parent_task_id:
        touch_parent_after_child_change(db, task, user.user_id)
    task.updated_at = datetime.now()
    db.commit()
    db.refresh(task)
    return task_to_out(db, user, task, include_children=True)


@router.post("/{task_id}/comments", response_model=TaskOut)
def add_task_comment(
    task_id: str, payload: CommentCreate, user: CurrentUser, db: DbSession
) -> TaskOut:
    task = _get_task_or_404(db, task_id)
    if not can_view_task(db, user, task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="조회 권한이 없습니다.")
    add_activity(db, task, user_id=user.user_id, kind="comment", body=payload.body.strip())
    db.commit()
    db.refresh(task)
    return task_to_out(db, user, task, include_children=True)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, user: CurrentUser, db: DbSession) -> None:
    task = _get_task_or_404(db, task_id)
    assert_can_edit(db, user, task)
    soft_delete_task_tree(db, task, user.user_id)
    db.commit()


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
PERIOD_LABELS = {"weekly": "주간", "monthly": "월간", "quarterly": "분기", "yearly": "연간"}


def _period_range(period: str, anchor: date) -> tuple[date, date]:
    if period == "weekly":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "monthly":
        start = anchor.replace(day=1)
        return start, (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if period == "quarterly":
        first_month = 3 * ((anchor.month - 1) // 3) + 1
        start = anchor.replace(month=first_month, day=1)
        end_month = first_month + 3
        end = (
            date(anchor.year + 1, 1, 1) if end_month > 12 else date(anchor.year, end_month, 1)
        ) - timedelta(days=1)
        return start, end
    return date(anchor.year, 1, 1), date(anchor.year, 12, 31)


def _in_period(task: Task, start: date, end: date) -> bool:
    """기간 내 갱신 / 마감 / 진행 구간이 겹치는 업무를 집계 대상으로 본다."""
    updated = task.updated_at.date() if isinstance(task.updated_at, datetime) else None
    if updated and start <= updated <= end:
        return True
    if task.due_date and start <= task.due_date <= end:
        return True
    if task.start_date and task.due_date and task.start_date <= end and task.due_date >= start:
        return True
    return False


def _as_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def _clip_text(value: str | None, limit: int = 80) -> str:
    text = (value or "").strip().replace("\n", " ")
    return text[: limit - 1] + "…" if len(text) > limit else text


def _state_at(task: Task, activities: list[TaskActivity], as_of: date) -> dict | None:
    """해당 날짜 종료 시점의 상태. 당시 업무가 없으면 None."""
    created = _as_date(task.created_at)
    if created and created > as_of:
        return None
    progress = 0
    status = "할당"
    issues = ""
    found = False
    for act in activities:
        acted = _as_date(act.created_at)
        if acted is None or acted > as_of:
            continue
        found = True
        if act.progress is not None:
            progress = int(act.progress)
        if act.status:
            status = act.status
        if act.kind == "comment" and (act.body or "").strip():
            issues = act.body.strip()
    if found:
        return {"status": status, "progress": progress, "issues": issues, "unknown": False}
    updated = _as_date(task.updated_at)
    if updated and updated <= as_of:
        return {
            "status": task.status,
            "progress": int(task.progress or 0),
            "issues": (task.issues or "").strip(),
            "unknown": False,
        }
    return {"status": "", "progress": None, "issues": "", "unknown": True}


def _last_week_text(snap: dict | None, activities: list[TaskActivity], start: date, end: date) -> str:
    if snap is None:
        return "전주 미착수"
    if snap.get("unknown"):
        week_acts = [a for a in activities if (d := _as_date(a.created_at)) and start <= d <= end]
        if week_acts:
            last = week_acts[-1]
            bits = []
            if last.status:
                bits.append(last.status)
            if last.progress is not None:
                bits.append(f"{int(last.progress)}%")
            if last.kind == "progress" and last.body:
                bits.append(last.body)
            return _clip_text(" · ".join(bits) or "전주 중 갱신")
        return "전주 기록 없음"
    text = f"{snap['status']} {int(snap['progress'] or 0)}%"
    changes = [
        a.body.strip()
        for a in activities
        if (d := _as_date(a.created_at)) and start <= d <= end and a.kind in {"progress", "status"} and a.body
    ]
    if changes:
        text += f" ({changes[-1]})"
    issues = _clip_text(snap.get("issues"), 60)
    if issues:
        text += f", {issues}"
    return text


def _this_week_plan(task: Task, this_start: date, this_end: date) -> str:
    progress = int(task.progress or 0)
    status = task.status or "할당"
    due = task.due_date
    issues = _clip_text(task.issues, 60)
    updated = _as_date(task.updated_at)
    if status == "완료":
        if updated and this_start <= updated <= this_end:
            return "이번주 완료"
        return "완료 유지"
    parts = [f"현재 {status} {progress}%"]
    if due and this_start <= due <= this_end:
        parts.append(f"금주 마감 {due.isoformat()[5:]}")
        if progress < 100:
            parts.append("완료 목표")
    elif due and due < this_start:
        parts.append(f"마감 {due.isoformat()[5:]} 초과 · 만회")
    elif due and due > this_end:
        parts.append(f"이후 마감 {due.isoformat()[5:]}")
    if issues:
        parts.append(issues)
    return ", ".join(parts)


def _make_week_over_week(
    db, this_tasks: list[Task], this_start: date, this_end: date, prior: AnalyticsSummary
) -> WeekOverWeek:
    last_map = {row.task_id: row for row in prior.tasks}
    union: dict[str, Task] = {task.task_id: task for task in this_tasks}
    if last_map:
        extras = db.scalars(
            select(Task).where(Task.task_id.in_(list(last_map)), Task.deleted_at.is_(None))
        ).all()
        for task in extras:
            if not task.parent_task_id:
                union.setdefault(task.task_id, task)
    activities: dict[str, list[TaskActivity]] = {task_id: [] for task_id in union}
    if union:
        rows = db.scalars(
            select(TaskActivity)
            .where(TaskActivity.task_id.in_(list(union)))
            .order_by(TaskActivity.created_at)
        ).all()
        for item in rows:
            activities.setdefault(item.task_id, []).append(item)

    compare_rows: list[WeekCompareRow] = []
    for task in union.values():
        acts = activities.get(task.task_id, [])
        snap = _state_at(task, acts, prior.end_date)
        last_progress = None if snap is None or snap.get("unknown") else int(snap["progress"] or 0)
        this_progress = int(task.progress or 0)
        delta = None if last_progress is None else this_progress - last_progress
        last_out = last_map.get(task.task_id)
        assignee = last_out.assignee_name if last_out and last_out.assignee_name else ""
        if not assignee:
            assignee = task.assignee.user_name if getattr(task, "assignee", None) else "미지정"
        compare_rows.append(
            WeekCompareRow(
                task_id=task.task_id,
                task_name=task.task_name,
                assignee_name=assignee or "미지정",
                last_week=_last_week_text(snap, acts, prior.start_date, prior.end_date),
                this_week=_this_week_plan(task, this_start, this_end),
                last_progress=last_progress,
                this_progress=this_progress,
                delta=delta,
            )
        )
    compare_rows.sort(key=lambda row: (0 if "초과" in row.this_week or "지연" in row.this_week else 1, row.task_name))
    return WeekOverWeek(
        last_start=prior.start_date,
        last_end=prior.end_date,
        last_total=prior.total,
        last_completed=prior.completed,
        last_delayed=prior.delayed,
        last_avg_progress=prior.avg_progress,
        last_completion_rate=prior.completion_rate,
        rows=compare_rows,
    )


def _week_compare_markdown(summary: AnalyticsSummary) -> str:
    wow = summary.week_over_week
    if wow is None:
        return ""
    lines = [
        "## 📋 업무별 전주 대비",
        "",
        f"전주 {wow.last_start} ~ {wow.last_end} 대비 이번주 {summary.start_date} ~ {summary.end_date}",
        "",
    ]
    if not wow.rows:
        lines.append("- 비교할 업무가 없습니다.")
    for row in wow.rows:
        lines.append(
            f"- **[{row.task_name}]** / 전주 진행상황: {row.last_week} / 이번주 진행 예정: {row.this_week}"
        )
    return "\n".join(lines)


def _buckets(period: str, start: date, end: date) -> list[tuple[str, date, date]]:
    if period == "weekly":
        names = ["월", "화", "수", "목", "금", "토", "일"]
        return [
            (names[i], start + timedelta(days=i), start + timedelta(days=i))
            for i in range(7)
        ]
    if period == "monthly":
        buckets: list[tuple[str, date, date]] = []
        cursor, index = start, 1
        while cursor <= end:
            bucket_end = min(cursor + timedelta(days=6), end)
            buckets.append((f"{index}주차", cursor, bucket_end))
            cursor, index = bucket_end + timedelta(days=1), index + 1
        return buckets

    buckets = []
    cursor = start
    while cursor <= end:
        month_end = (cursor + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        buckets.append((f"{cursor.month}월", cursor, min(month_end, end)))
        cursor = month_end + timedelta(days=1)
    return buckets


def _build_summary(
    db, user, period: str, anchor: date, dept_id: int | None, *, include_wow: bool = True
) -> AnalyticsSummary:
    start, end = _period_range(period, anchor)
    tasks = [
        t
        for t in get_visible_tasks(db, user, skip_activities=True)
        if _in_period(t, start, end) and not t.parent_task_id
    ]

    scope_label = f"{user.role_level} 권한 전체"
    if dept_id is not None:
        allowed = scope_dept_ids(db, user)
        if allowed is not None and dept_id not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="해당 부서 통계 조회 권한이 없습니다."
            )
        tasks = [t for t in tasks if t.dept_id == dept_id]
        dept = db.get(Department, dept_id)
        scope_label = dept.dept_name if dept else scope_label

    rows = tasks_to_out(db, user, tasks, compact=True)
    total = len(rows)
    completed = sum(1 for r in rows if r.status == "완료")
    delayed = sum(1 for r in rows if r.is_delayed)

    assignee_acc: dict[str, dict[str, int]] = {}
    dept_acc: dict[str, dict[str, int]] = {}
    for row in rows:
        acc = assignee_acc.setdefault(
            row.assignee_name or "미지정", {"total": 0, "done": 0, "delayed": 0, "progress": 0}
        )
        acc["total"] += 1
        acc["done"] += int(row.status == "완료")
        acc["delayed"] += int(row.is_delayed)
        acc["progress"] += row.progress

        dacc = dept_acc.setdefault(
            row.dept_name or "미지정", {"total": 0, "delayed": 0, "progress": 0}
        )
        dacc["total"] += 1
        dacc["delayed"] += int(row.is_delayed)
        dacc["progress"] += row.progress

    trend: list[TrendPoint] = []
    for label, bucket_start, bucket_end in _buckets(period, start, end):
        done_count = sum(
            1
            for t in tasks
            if t.status == "완료"
            and isinstance(t.updated_at, datetime)
            and bucket_start <= t.updated_at.date() <= bucket_end
        )
        created_count = sum(
            1
            for t in tasks
            if isinstance(t.created_at, datetime)
            and bucket_start <= t.created_at.date() <= bucket_end
        )
        trend.append(TrendPoint(label=label, completed=done_count, created=created_count))

    wow = None
    if period == "weekly" and include_wow:
        prior = _build_summary(
            db, user, "weekly", start - timedelta(days=1), dept_id, include_wow=False
        )
        wow = _make_week_over_week(db, tasks, start, end, prior)

    return AnalyticsSummary(
        period=period,  # type: ignore[arg-type]
        start_date=start,
        end_date=end,
        scope_label=scope_label,
        total=total,
        completed=completed,
        delayed=delayed,
        with_issues=sum(1 for r in rows if (r.issues or "").strip()),
        avg_progress=round(sum(r.progress for r in rows) / total) if total else 0,
        completion_rate=round(completed / total * 100) if total else 0,
        status_counts=[
            StatusCount(status=s, count=sum(1 for r in rows if r.status == s))
            for s in STATUSES
        ],
        by_assignee=[
            AssigneeStat(
                assignee=name,
                total=v["total"],
                done=v["done"],
                delayed=v["delayed"],
                avg_progress=round(v["progress"] / v["total"]) if v["total"] else 0,
            )
            for name, v in sorted(assignee_acc.items(), key=lambda kv: -kv[1]["total"])
        ],
        by_dept=[
            DeptStat(
                dept_name=name,
                total=v["total"],
                delayed=v["delayed"],
                avg_progress=round(v["progress"] / v["total"]) if v["total"] else 0,
            )
            for name, v in sorted(dept_acc.items(), key=lambda kv: -kv[1]["total"])
        ],
        trend=trend,
        tasks=rows,
        week_over_week=wow,
    )


@analytics_router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    user: CurrentUser,
    db: DbSession,
    period: str = "weekly",
    anchor: date | None = None,
    dept_id: int | None = None,
) -> AnalyticsSummary:
    if period not in PERIOD_LABELS:
        raise HTTPException(status_code=422, detail="지원하지 않는 기간입니다.")
    return _build_summary(db, user, period, anchor or date.today(), dept_id)


@analytics_router.get("/reports", response_model=list[SavedReportSummary])
def list_reports(user: CurrentUser, db: DbSession) -> list[SavedReportSummary]:
    """내가 생성한 AI 경영 리포트 목록."""
    rows = db.scalars(
        select(AnalyticsReport)
        .where(AnalyticsReport.created_by == user.user_id)
        .order_by(AnalyticsReport.created_at.desc())
    ).all()
    return [_report_summary(row) for row in rows]


@analytics_router.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(report_id: int, user: CurrentUser, db: DbSession) -> ReportResponse:
    row = _own_report(db, user, report_id)
    return _report_to_out(row)


@analytics_router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: int, user: CurrentUser, db: DbSession) -> None:
    row = _own_report(db, user, report_id)
    db.delete(row)
    db.commit()


@analytics_router.post("/report", response_model=ReportResponse)
def analytics_report(payload: ReportRequest, user: CurrentUser, db: DbSession) -> ReportResponse:
    """LLM 기반 경영진 요약 리포트 생성."""
    return _compose_report(db, user, payload.period, payload.anchor, payload.dept_id)


@analytics_router.post("/report/email", response_model=ReportEmailResponse)
def email_report(
    payload: ReportEmailRequest, user: CurrentUser, db: DbSession
) -> ReportEmailResponse:
    """생성된(또는 방금 만든) AI 리포트를 연결된 Outlook 계정으로 발송한다."""
    row = db.get(CalendarConnection, user.user_id)
    if row is None or not row.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="연결된 Microsoft 계정이 없습니다. 회의실에서 Outlook을 연결하세요.",
        )
    if cal.MAIL_SCOPE in cal.missing_graph_scopes(row):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="메일 보내기 권한이 없습니다. Microsoft 계정을 다시 연결해 Mail.Send 동의를 받으세요.",
        )

    if payload.markdown and payload.markdown.strip():
        summary = _build_summary(
            db, user, payload.period, payload.anchor or date.today(), payload.dept_id
        )
        markdown = payload.markdown.strip()
        period_label = f"{PERIOD_LABELS[payload.period]} ({summary.start_date} ~ {summary.end_date})"
        scope_label = summary.scope_label
    else:
        report = _compose_report(db, user, payload.period, payload.anchor, payload.dept_id)
        markdown = report.report_markdown
        period_label = report.period_label
        scope_label = report.scope_label

    try:
        recipients = cal.parse_emails(payload.to)
    except cal.CalendarError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    subject = f"[AL Note] {period_label} 경영 리포트"
    html = (
        f"<p style='font-family:Segoe UI,sans-serif;color:#6b7280;font-size:13px'>"
        f"{html_lib.escape(scope_label)} · AL Note 에서 발송</p>"
        f"{cal.markdown_to_html(markdown)}"
    )

    app = cal.app_config(db)
    try:
        token = cal.ensure_access_token(db, row, app)
        cal.send_mail(token, to=recipients, subject=subject, html=html)
    except cal.ReauthRequired as exc:
        row.needs_reauth = True
        row.last_sync_ok = False
        row.last_sync_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except cal.CalendarError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ReportEmailResponse(sent_to=recipients, subject=subject)


def _own_report(db, user, report_id: int) -> AnalyticsReport:
    row = db.get(AnalyticsReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    if row.created_by != user.user_id:
        raise HTTPException(status_code=403, detail="조회 권한이 없습니다.")
    return row


def _report_summary(row: AnalyticsReport) -> SavedReportSummary:
    return SavedReportSummary(
        report_id=row.report_id,
        period=row.period,  # type: ignore[arg-type]
        period_label=row.period_label,
        scope_label=row.scope_label,
        mock=row.mock,
        created_at=row.created_at,
    )


def _report_to_out(row: AnalyticsReport) -> ReportResponse:
    return ReportResponse(
        report_id=row.report_id,
        period=row.period,  # type: ignore[arg-type]
        anchor=row.anchor,
        dept_id=row.dept_id,
        period_label=row.period_label,
        scope_label=row.scope_label,
        report_markdown=row.report_markdown,
        mock=row.mock,
        created_at=row.created_at,
    )


def _compose_report(
    db,
    user,
    period: str,
    anchor: date | None,
    dept_id: int | None,
) -> ReportResponse:
    summary = _build_summary(db, user, period, anchor or date.today(), dept_id)
    period_label = f"{PERIOD_LABELS[period]} ({summary.start_date} ~ {summary.end_date})"

    stats = {
        "total": summary.total,
        "avg_progress": summary.avg_progress,
        "completion_rate": summary.completion_rate,
        "delayed": summary.delayed,
        "with_issues": summary.with_issues,
        **{sc.status: sc.count for sc in summary.status_counts},
        "by_assignee": [a.model_dump() for a in summary.by_assignee],
    }
    if summary.week_over_week:
        wow = summary.week_over_week
        stats["week_over_week"] = {
            "last_period": f"{wow.last_start} ~ {wow.last_end}",
            "this_period": f"{summary.start_date} ~ {summary.end_date}",
            "last_total": wow.last_total,
            "this_total": summary.total,
            "last_completed": wow.last_completed,
            "this_completed": summary.completed,
            "last_avg_progress": wow.last_avg_progress,
            "this_avg_progress": summary.avg_progress,
            "last_completion_rate": wow.last_completion_rate,
            "this_completion_rate": summary.completion_rate,
            "last_delayed": wow.last_delayed,
            "this_delayed": summary.delayed,
            "task_rows": [row.model_dump() for row in wow.rows[:80]],
        }
    tasks = [
        {
            "task_id": t.task_id,
            "task_name": t.task_name,
            "assignee_name": t.assignee_name or "미지정",
            "dept_name": t.dept_name or "-",
            "status": t.status,
            "progress": t.progress,
            "due_date": t.due_date.isoformat() if t.due_date else "",
            "issues": t.issues or "",
            "is_delayed": t.is_delayed,
        }
        for t in summary.tasks
    ]

    try:
        markdown = generate_period_report(
            period_label,
            summary.scope_label,
            stats,
            tasks,
            db=db,
            user_id=user.user_id,
            weekly_compare=_week_compare_markdown(summary) if summary.week_over_week else "",
        )
    except AIEngineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    anchor_date = anchor or date.today()
    mock = not active_config(db).ready
    row = AnalyticsReport(
        created_by=user.user_id,
        period=period,
        anchor=anchor_date,
        dept_id=dept_id,
        period_label=period_label,
        scope_label=summary.scope_label,
        report_markdown=markdown,
        mock=mock,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _report_to_out(row)
