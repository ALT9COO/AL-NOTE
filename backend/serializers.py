"""ORM 객체 → Pydantic 응답 스키마 변환 헬퍼."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from auth import can_edit_task, can_manage_meeting, is_task_collaborator, is_using_default_password
from database import (
    Meeting,
    MeetingParticipant,
    MeetingViewer,
    Task,
    TaskActivity,
    TaskCollaborator,
    TaskViewer,
    User,
)
from schemas import CollaboratorOut, MeetingOut, TaskActivityOut, TaskOut, UserOut
from task_service import active_children, all_children, child_count_map, latest_comment_map


def is_delayed(task: Task) -> bool:
    return bool(task.due_date and task.due_date < date.today() and task.status != "완료")


def collaborator_to_out(
    item: TaskCollaborator | TaskViewer | MeetingParticipant | MeetingViewer,
) -> CollaboratorOut:
    if item.user_id:
        return CollaboratorOut(
            kind="user",
            user_id=item.user_id,
            user_name=item.user.user_name if item.user else item.user_id,
            dept_id=item.user.dept_id if item.user else None,
            dept_name=item.user.department.dept_name if item.user and item.user.department else None,
        )
    return CollaboratorOut(
        kind="dept",
        dept_id=item.dept_id,
        dept_name=item.department.dept_name if item.department else None,
    )


def activity_to_out(item: TaskActivity) -> TaskActivityOut:
    return TaskActivityOut(
        activity_id=item.activity_id,
        kind=item.kind,
        body=item.body or "",
        progress=item.progress,
        status=item.status,  # type: ignore[arg-type]
        user_id=item.user_id,
        user_name=item.author.user_name if item.author else None,
        created_at=item.created_at,
    )


def task_to_out(
    db: Session,
    current_user: User,
    task: Task,
    *,
    include_children: bool = False,
    compact: bool = False,
    child_count: int | None = None,
    latest_comment_at=None,
) -> TaskOut:
    deleter = db.get(User, task.deleted_by) if task.deleted_by else None
    purge_on = (task.deleted_at + timedelta(days=365)) if task.deleted_at else None
    if compact:
        count = int(child_count or 0)
        kids: list[Task] = []
        comments_at = latest_comment_at
        collaborators = [collaborator_to_out(item) for item in task.collaborators]
        viewers = [collaborator_to_out(item) for item in task.viewers]
        activities = []
    else:
        kids = active_children(db, task.task_id)
        if task.deleted_at is not None:
            kids = [child for child in all_children(db, task.task_id) if child.deleted_at is not None]
        count = len(kids) if child_count is None else int(child_count)
        comments = [item for item in task.activities if item.kind == "comment"]
        comments_at = max((item.created_at for item in comments), default=None)
        collaborators = [collaborator_to_out(item) for item in task.collaborators]
        viewers = [collaborator_to_out(item) for item in task.viewers]
        activities = [activity_to_out(item) for item in task.activities]
    children_out = (
        [task_to_out(db, current_user, child, include_children=False) for child in kids]
        if include_children
        else []
    )
    return TaskOut(
        task_id=task.task_id,
        task_name=task.task_name,
        description=task.description or "",
        status=task.status,  # type: ignore[arg-type]
        progress=int(task.progress or 0),
        dept_id=task.dept_id,
        dept_name=task.department.dept_name if task.department else None,
        assigned_to=task.assigned_to,
        assignee_name=task.assignee.user_name if task.assignee else None,
        start_date=task.start_date,
        due_date=task.due_date,
        issues=task.issues or "",
        updated_at=task.updated_at,
        is_delayed=is_delayed(task),
        can_edit=can_edit_task(db, current_user, task),
        is_collaborator=is_task_collaborator(db, current_user, task),
        latest_comment_at=comments_at,
        collaborators=collaborators,
        viewers=viewers,
        activities=activities,
        deleted_at=task.deleted_at,
        deleted_by=task.deleted_by,
        deleted_by_name=deleter.user_name if deleter else task.deleted_by,
        purge_on=purge_on,
        parent_task_id=task.parent_task_id,
        child_count=count,
        progress_locked=bool(count),
        children=children_out,
    )


def tasks_to_out(
    db: Session, current_user: User, tasks: list[Task], *, compact: bool = False
) -> list[TaskOut]:
    ids = [task.task_id for task in tasks]
    include_deleted = any(task.deleted_at is not None for task in tasks)
    counts = child_count_map(db, ids, include_deleted=include_deleted)
    comments = latest_comment_map(db, ids) if compact else {}
    return [
        task_to_out(
            db,
            current_user,
            task,
            compact=compact,
            child_count=counts.get(task.task_id, 0),
            latest_comment_at=comments.get(task.task_id) if compact else None,
        )
        for task in tasks
    ]


def user_to_out(user: User) -> UserOut:
    return UserOut(
        user_id=user.user_id,
        user_name=user.user_name,
        role_level=user.role_level,  # type: ignore[arg-type]
        job_title=user.job_title or "",
        dept_id=user.dept_id,
        dept_name=user.department.dept_name if user.department else None,
        is_using_default_password=is_using_default_password(user),
    )


def meeting_to_out(meeting: Meeting, current_user: User | None = None) -> MeetingOut:
    task_ids = [item for item in (meeting.task_ids or "").split(",") if item.strip()]
    return MeetingOut(
        meeting_id=meeting.meeting_id,
        title=meeting.title,
        created_by=meeting.created_by,
        author_name=meeting.author.user_name if meeting.author else None,
        dept_name=meeting.department.dept_name if meeting.department else None,
        ai_summary=meeting.ai_summary or "",
        raw_transcript=meeting.raw_transcript or "",
        created_at=meeting.created_at,
        event_key=meeting.event_key,
        event_start=meeting.event_start,
        event_location=meeting.event_location or "",
        task_ids=task_ids,
        participants=[collaborator_to_out(item) for item in meeting.participants],
        viewers=[collaborator_to_out(item) for item in meeting.viewers],
        can_manage=can_manage_meeting(current_user, meeting) if current_user else False,
        has_audio=bool(meeting.audio_file),
        audio_name=meeting.audio_filename,
        audio_size=meeting.audio_size,
    )
