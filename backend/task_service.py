"""업무 공동작업자 · 히스토리 기록 헬퍼."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import Task, TaskActivity, TaskCollaborator, TaskViewer, User
from schemas import CollaboratorIn
from config import STATUS_DEFAULT_PROGRESS


def add_activity(
    db: Session,
    task: Task,
    *,
    user_id: str | None,
    kind: str,
    body: str,
    progress: int | None = None,
    status: str | None = None,
    created_at: datetime | None = None,
) -> TaskActivity:
    activity = TaskActivity(
        task_id=task.task_id,
        user_id=user_id,
        kind=kind,
        body=body,
        progress=task.progress if progress is None else progress,
        status=task.status if status is None else status,
        created_at=created_at or datetime.now(),
    )
    db.add(activity)
    if kind == "comment" and body.strip():
        task.issues = body.strip()
    task.updated_at = datetime.now()
    return activity


def log_task_changes(
    db: Session,
    task: Task,
    user_id: str | None,
    *,
    old_status: str,
    old_progress: int,
    old_issues: str,
) -> None:
    if task.status != old_status:
        add_activity(
            db,
            task,
            user_id=user_id,
            kind="status",
            body=f"{old_status} → {task.status}",
            progress=task.progress,
            status=task.status,
        )
    if int(task.progress or 0) != int(old_progress or 0):
        add_activity(
            db,
            task,
            user_id=user_id,
            kind="progress",
            body=f"진행률 {old_progress}% → {task.progress}%",
            progress=task.progress,
            status=task.status,
        )
    new_issues = (task.issues or "").strip()
    if new_issues and new_issues != (old_issues or "").strip():
        add_activity(db, task, user_id=user_id, kind="comment", body=new_issues)


def apply_assignee_dept(db: Session, task: Task, assigned_to: str | None, *, override: bool) -> None:
    """담당자 부서를 업무 부서에 연동. override=True 이면 담당자 부서로 덮어쓴다."""
    if not assigned_to:
        return
    assignee = db.get(User, assigned_to)
    if assignee and assignee.dept_id is not None and (override or task.dept_id is None):
        task.dept_id = assignee.dept_id


def replace_collaborators(db: Session, task: Task, items: list[CollaboratorIn]) -> None:
    _replace_subjects(db, task, items, collection="collaborators", model=TaskCollaborator)


def replace_viewers(db: Session, task: Task, items: list[CollaboratorIn]) -> None:
    _replace_subjects(db, task, items, collection="viewers", model=TaskViewer)


def _replace_subjects(
    db: Session,
    task: Task,
    items: list[CollaboratorIn],
    *,
    collection: str,
    model: type[TaskCollaborator] | type[TaskViewer],
) -> None:
    getattr(task, collection).clear()
    db.flush()
    seen: set[tuple[str, str]] = set()
    for item in items:
        if item.kind == "user" and item.user_id:
            if item.user_id == task.assigned_to:
                continue
            key = ("user", item.user_id)
            if key in seen:
                continue
            seen.add(key)
            if db.get(User, item.user_id) is None:
                continue
            getattr(task, collection).append(model(task_id=task.task_id, user_id=item.user_id))
        elif item.kind == "dept" and item.dept_id is not None:
            key = ("dept", str(item.dept_id))
            if key in seen:
                continue
            seen.add(key)
            getattr(task, collection).append(model(task_id=task.task_id, dept_id=item.dept_id))


def _child_query(db: Session, parent_id: str, *, include_deleted: bool):
    stmt = select(Task).where(Task.parent_task_id == parent_id).order_by(Task.task_id)
    if not include_deleted:
        stmt = stmt.where(Task.deleted_at.is_(None))
    return db.scalars(stmt).unique().all()


def active_children(db: Session, parent_id: str) -> list[Task]:
    return list(_child_query(db, parent_id, include_deleted=False))


def all_children(db: Session, parent_id: str) -> list[Task]:
    return list(_child_query(db, parent_id, include_deleted=True))


def child_count_map(
    db: Session, parent_ids: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """상위 업무별 하위 건수를 한 번에 집계한다."""
    if not parent_ids:
        return {}
    stmt = select(Task.parent_task_id, func.count()).where(Task.parent_task_id.in_(parent_ids))
    if not include_deleted:
        stmt = stmt.where(Task.deleted_at.is_(None))
    stmt = stmt.group_by(Task.parent_task_id)
    return {str(parent_id): int(count) for parent_id, count in db.execute(stmt).all() if parent_id}


def latest_comment_map(db: Session, task_ids: list[str]) -> dict[str, datetime]:
    """업무별 마지막 댓글 시각을 한 번에 집계한다."""
    if not task_ids:
        return {}
    stmt = (
        select(TaskActivity.task_id, func.max(TaskActivity.created_at))
        .where(TaskActivity.task_id.in_(task_ids), TaskActivity.kind == "comment")
        .group_by(TaskActivity.task_id)
    )
    return {str(task_id): stamped for task_id, stamped in db.execute(stmt).all() if task_id}


def recompute_parent_progress(db: Session, parent: Task, user_id: str | None) -> None:
    """하위 업무 진행률 평균으로 상위 진행률을 맞춘다."""
    children = active_children(db, parent.task_id)
    if not children:
        return
    old = int(parent.progress or 0)
    new = round(sum(int(child.progress or 0) for child in children) / len(children))
    if new == old:
        return
    parent.progress = new
    parent.updated_at = datetime.now()
    add_activity(
        db,
        parent,
        user_id=user_id,
        kind="progress",
        body=f"하위 업무 평균으로 진행률 {old}% → {new}%",
        progress=new,
    )


def apply_status_fields(task: Task, status: str, *, set_default_progress: bool) -> None:
    task.status = status
    if set_default_progress and status in STATUS_DEFAULT_PROGRESS:
        task.progress = STATUS_DEFAULT_PROGRESS[status]


def sync_children_to_parent(
    db: Session, parent: Task, user_id: str | None, *, force_default_progress: bool = False
) -> None:
    """상위 상태 변경 시 하위 상태를 맞춘다. 상태가 바뀐 하위만 기본 진행률을 적용한다."""
    children = active_children(db, parent.task_id)
    for child in children:
        old_status = child.status
        old_progress = int(child.progress or 0)
        status_changed = child.status != parent.status
        apply_status_fields(
            child,
            parent.status,
            set_default_progress=force_default_progress or status_changed,
        )
        log_task_changes(
            db,
            child,
            user_id,
            old_status=old_status,
            old_progress=old_progress,
            old_issues=child.issues or "",
        )
        child.updated_at = datetime.now()
    recompute_parent_progress(db, parent, user_id)


def touch_parent_after_child_change(db: Session, child: Task, user_id: str | None) -> None:
    if not child.parent_task_id:
        return
    parent = db.get(Task, child.parent_task_id)
    if parent is None or parent.deleted_at is not None:
        return
    recompute_parent_progress(db, parent, user_id)


def soft_delete_task_tree(db: Session, task: Task, user_id: str) -> None:
    now = datetime.now()

    def mark_deleted(item: Task) -> None:
        if item.deleted_at is not None:
            return
        item.deleted_at = now
        item.deleted_by = user_id
        add_activity(
            db,
            item,
            user_id=user_id,
            kind="delete",
            body="업무가 삭제되었습니다. 설정에서 1년 이내 복원할 수 있습니다.",
        )

    mark_deleted(task)
    if task.parent_task_id:
        parent = db.get(Task, task.parent_task_id)
        if parent and parent.deleted_at is None:
            recompute_parent_progress(db, parent, user_id)
        return
    for child in active_children(db, task.task_id):
        mark_deleted(child)


def restore_task_tree(db: Session, task: Task, user_id: str) -> None:
    def mark_restored(item: Task) -> None:
        if item.deleted_at is None:
            return
        item.deleted_at = None
        item.deleted_by = None
        add_activity(db, item, user_id=user_id, kind="restore", body="삭제된 업무를 복원했습니다.")

    if task.parent_task_id:
        parent = db.get(Task, task.parent_task_id)
        if parent is not None and parent.deleted_at is not None:
            restore_task_tree(db, parent, user_id)
            return
        mark_restored(task)
        if parent is not None:
            recompute_parent_progress(db, parent, user_id)
        return

    mark_restored(task)
    for child in all_children(db, task.task_id):
        mark_restored(child)
    recompute_parent_progress(db, task, user_id)
