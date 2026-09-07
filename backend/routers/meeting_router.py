"""음성 STT · AI 회의 요약 · 안건 제출(업무 일괄 반영) 라우터."""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from ai_engine import (
    AIEngineError,
    active_config,
    parse_meeting,
    stt_config,
    summary_to_markdown,
    transcribe_audio,
)
from audio_store import delete_recording, read_recording, resolve_recording, save_recording
from auth import (
    CurrentUser,
    DbSession,
    can_edit_task,
    can_manage_meeting,
    can_view_meeting,
    get_visible_tasks,
    visible_meetings,
    visible_users,
)
from database import (
    Meeting,
    MeetingDraft,
    MeetingParticipant,
    MeetingViewer,
    SessionLocal,
    Task,
    User,
    next_task_id,
)
from schemas import (
    AgendaSubmitRequest,
    AgendaSubmitResponse,
    CollaboratorIn,
    MeetingAccessUpdate,
    MeetingDraftIn,
    MeetingDraftOut,
    MeetingOut,
    MeetingParseResponse,
    ParseRequest,
    TranscriptResponse,
)
from config import MAX_AUDIO_BYTES, MAX_AUDIO_MB
from serializers import meeting_to_out, task_to_out
from task_service import (
    add_activity,
    apply_assignee_dept,
    log_task_changes,
    active_children,
    sync_children_to_parent,
    touch_parent_after_child_change,
)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
logger = logging.getLogger("ainote")
_stt_lock = threading.Lock()
_stt_jobs: set[int] = set()


def _draft_title(transcript: str, event: dict | None = None) -> str:
    if event and str(event.get("title") or "").strip():
        return str(event.get("title")).strip()[:200]
    first = next((line.strip() for line in (transcript or "").splitlines() if line.strip()), "")
    stamp = datetime.now().strftime("%m/%d %H:%M")
    if first:
        return f"{first[:60]} ({stamp})"[:200]
    return f"전사 초안 ({stamp})"


def _loads(raw: str) -> dict | None:
    if not (raw or "").strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def draft_to_out(row: MeetingDraft) -> MeetingDraftOut:
    return MeetingDraftOut(
        draft_id=row.draft_id,
        title=row.title,
        transcript=row.raw_transcript or "",
        parsed=_loads(row.parsed_json),
        event=_loads(row.event_json),
        step=int(row.step or 2),
        created_at=row.created_at,
        updated_at=row.updated_at or row.created_at,
        has_audio=bool(row.audio_file),
        audio_name=row.audio_filename,
        audio_size=row.audio_size,
        stt_status=row.stt_status or ("done" if (row.raw_transcript or "").strip() else "idle"),
        stt_error=row.stt_error,
        stt_mock=bool(row.stt_mock),
    )


def _attach_audio(row: Meeting | MeetingDraft, stored) -> None:
    row.audio_file = stored.name
    row.audio_filename = stored.original
    row.audio_mime = stored.mime
    row.audio_size = stored.size


def _copy_audio(src: MeetingDraft, dest: Meeting) -> None:
    dest.audio_file = src.audio_file
    dest.audio_filename = src.audio_filename
    dest.audio_mime = src.audio_mime
    dest.audio_size = src.audio_size
    src.audio_file = None
    src.audio_filename = None
    src.audio_mime = None
    src.audio_size = None


def _audio_response(name: str | None, filename: str | None, mime: str | None) -> FileResponse:
    path = resolve_recording(name)
    if path is None:
        raise HTTPException(status_code=404, detail="음성 파일을 찾을 수 없습니다.")
    return FileResponse(
        path,
        media_type=mime or "audio/webm",
        filename=filename or "recording.webm",
        content_disposition_type="inline",
    )


def _own_draft(db, user, draft_id: int) -> MeetingDraft:
    row = db.get(MeetingDraft, draft_id)
    if row is None or row.created_by != user.user_id:
        raise HTTPException(status_code=404, detail="저장된 전사를 찾을 수 없습니다.")
    return row


def _replace_meeting_subjects(
    db,
    meeting: Meeting,
    items: list[CollaboratorIn],
    *,
    collection: str,
    model: type[MeetingParticipant] | type[MeetingViewer],
) -> None:
    getattr(meeting, collection).clear()
    db.flush()
    seen: set[tuple[str, str]] = set()
    for item in items:
        if item.kind == "user" and item.user_id:
            if item.user_id == meeting.created_by:
                continue
            key = ("user", item.user_id)
            if key in seen:
                continue
            seen.add(key)
            if db.get(User, item.user_id) is None:
                continue
            getattr(meeting, collection).append(
                model(meeting_id=meeting.meeting_id, user_id=item.user_id)
            )
        elif item.kind == "dept" and item.dept_id is not None:
            key = ("dept", str(item.dept_id))
            if key in seen:
                continue
            seen.add(key)
            getattr(meeting, collection).append(
                model(meeting_id=meeting.meeting_id, dept_id=item.dept_id)
            )


def replace_meeting_access(
    db,
    meeting: Meeting,
    participants: list[CollaboratorIn],
    viewers: list[CollaboratorIn],
) -> None:
    _replace_meeting_subjects(
        db, meeting, participants, collection="participants", model=MeetingParticipant
    )
    _replace_meeting_subjects(db, meeting, viewers, collection="viewers", model=MeetingViewer)


def _run_stt_job(draft_id: int, user_id: str, filename: str) -> None:
    try:
        with SessionLocal() as db:
            draft = db.get(MeetingDraft, draft_id)
            if draft is None:
                return
            audio_bytes = read_recording(draft.audio_file)
            if not audio_bytes:
                draft.stt_status = "error"
                draft.stt_error = "보관된 음성 파일을 찾을 수 없습니다."
                draft.updated_at = datetime.now()
                db.commit()
                return
        try:
            text, mock = _transcribe_sync(audio_bytes, filename, user_id)
            error = None
        except AIEngineError as exc:
            text, mock, error = "", False, str(exc)
        with SessionLocal() as db:
            draft = db.get(MeetingDraft, draft_id)
            if draft is None:
                return
            draft.raw_transcript = text
            draft.stt_mock = mock
            draft.stt_error = error
            draft.stt_status = "error" if error else "done"
            if text:
                draft.title = _draft_title(text, _loads(draft.event_json))
                draft.step = max(int(draft.step or 1), 2)
            draft.updated_at = datetime.now()
            db.commit()
    except Exception:
        logger.exception("초안 %s 전사 작업 실패", draft_id)
        with SessionLocal() as db:
            draft = db.get(MeetingDraft, draft_id)
            if draft is None:
                return
            draft.stt_status = "error"
            draft.stt_error = "전사 처리 중 오류가 발생했습니다."
            draft.updated_at = datetime.now()
            db.commit()
    finally:
        with _stt_lock:
            _stt_jobs.discard(draft_id)


def _start_stt_job(draft_id: int, user_id: str, filename: str) -> bool:
    with _stt_lock:
        if draft_id in _stt_jobs:
            return False
        _stt_jobs.add(draft_id)
    threading.Thread(
        target=_run_stt_job,
        args=(draft_id, user_id, filename),
        daemon=True,
        name=f"stt-{draft_id}",
    ).start()
    return True


def _transcribe_sync(audio_bytes: bytes, filename: str, user_id: str) -> tuple[str, bool]:
    with SessionLocal() as db:
        text = transcribe_audio(audio_bytes, filename, db=db, user_id=user_id)
        return text, not stt_config(db).ready


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe(
    user: CurrentUser, db: DbSession, file: UploadFile = File(...)
) -> TranscriptResponse:
    """오디오를 저장한 뒤 전사는 백그라운드에서 진행한다."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="오디오 파일이 비어 있습니다.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"오디오 파일이 너무 큽니다. (최대 {MAX_AUDIO_MB}MB)",
        )

    stored = save_recording(audio_bytes, file.filename or "recording.webm", file.content_type)
    now = datetime.now()
    draft = MeetingDraft(
        created_by=user.user_id,
        title=f"음성 기록 ({now.strftime('%m/%d %H:%M')})",
        raw_transcript="",
        step=1,
        created_at=now,
        updated_at=now,
        stt_status="transcribing",
        stt_error=None,
        stt_mock=False,
    )
    _attach_audio(draft, stored)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    _start_stt_job(draft.draft_id, user.user_id, file.filename or "meeting.wav")
    return TranscriptResponse(
        transcript="",
        mock=False,
        draft_id=draft.draft_id,
        has_audio=True,
        audio_name=draft.audio_filename,
        audio_size=draft.audio_size,
        stt_status="transcribing",
    )


def _contexts(db, user):
    tasks = get_visible_tasks(db, user)
    tasks_context = [
        {
            "task_id": t.task_id,
            "task_name": t.task_name,
            "assigned_to": t.assigned_to,
            "status": t.status,
            "progress": t.progress,
            "due_date": t.due_date.isoformat() if t.due_date else "",
            "issues": t.issues or "",
            "parent_task_id": t.parent_task_id or "",
        }
        for t in tasks
    ]
    users_context = [
        {"user_id": u.user_id, "user_name": u.user_name, "role_level": u.role_level}
        for u in visible_users(db, user)
    ]
    return tasks_context, users_context


@router.post("/parse", response_model=MeetingParseResponse)
def parse(payload: ParseRequest, user: CurrentUser, db: DbSession) -> MeetingParseResponse:
    """전사 텍스트 → GPT-4o JSON 구조화 (요약/안건/액션/업무 업데이트)."""
    tasks_context, users_context = _contexts(db, user)
    try:
        parsed = parse_meeting(
            payload.transcript,
            tasks_context,
            users_context,
            db=db,
            user_id=user.user_id,
            event_title=payload.event_title,
            attendees=payload.attendees[:30],
        )
    except AIEngineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return MeetingParseResponse(**parsed, mock=not active_config(db).ready)


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


@router.post("/submit", response_model=AgendaSubmitResponse)
def submit_agenda(
    payload: AgendaSubmitRequest, user: CurrentUser, db: DbSession
) -> AgendaSubmitResponse:
    """검토 완료된 안건을 Tasks 에 일괄 반영하고 회의록을 저장한다."""
    updated: list[str] = []
    created: list[str] = []
    skipped: list[str] = []
    touched: list[Task] = []

    member_dept = {u.user_id: u.dept_id for u in visible_users(db, user)}

    for item in payload.task_updates:
        due = _parse_iso_date(item.due_date)

        if item.task_id in ("NEW", "", None) or item.is_new:
            task = Task(
                task_id=next_task_id(db),
                task_name=item.task_name or "제목 없는 업무",
                description=f"'{payload.title}' 회의에서 자동 생성됨",
                dept_id=member_dept.get(item.assignee, user.dept_id),
                assigned_to=item.assignee or user.user_id,
                status=item.status,
                progress=item.progress,
                start_date=date.today(),
                due_date=due,
                issues=item.issues,
            )
            db.add(task)
            db.flush()
            apply_assignee_dept(db, task, task.assigned_to, override=task.dept_id is None)
            add_activity(
                db,
                task,
                user_id=user.user_id,
                kind="create",
                body=f"'{payload.title}' 회의에서 등록되었습니다.",
            )
            if (item.issues or "").strip():
                add_activity(db, task, user_id=user.user_id, kind="comment", body=item.issues.strip())
            created.append(f"{task.task_id} {task.task_name}")
            touched.append(task)
            continue

        task = db.get(Task, item.task_id)
        if task is None:
            skipped.append(f"{item.task_id} (존재하지 않음)")
            continue
        if not can_edit_task(db, user, task):
            skipped.append(f"{item.task_id} (수정 권한 없음)")
            continue

        old_status = task.status
        old_progress = int(task.progress or 0)
        old_issues = task.issues or ""
        has_children = bool(active_children(db, task.task_id))
        task.status = item.status
        if not has_children:
            task.progress = item.progress
        task.issues = item.issues
        if item.task_name:
            task.task_name = item.task_name
        if item.assignee:
            task.assigned_to = item.assignee
            apply_assignee_dept(db, task, item.assignee, override=True)
        if due:
            task.due_date = due
        log_task_changes(
            db,
            task,
            user.user_id,
            old_status=old_status,
            old_progress=old_progress,
            old_issues=old_issues,
        )
        if has_children:
            sync_children_to_parent(db, task, user.user_id, force_default_progress=True)
        elif task.parent_task_id:
            touch_parent_after_child_change(db, task, user.user_id)
        task.updated_at = datetime.now()
        updated.append(f"{task.task_id} {task.task_name}")
        touched.append(task)

    meeting = Meeting(
        title=payload.title,
        created_by=user.user_id,
        dept_id=user.dept_id,
        event_key=payload.event_key,
        event_start=payload.event_start,
        event_location=payload.event_location or "",
        raw_transcript=payload.transcript,
        ai_summary=summary_to_markdown(
            {
                "meeting_title": payload.title,
                "summary_bullets": payload.summary_bullets,
                "agenda_items": [a.model_dump() for a in payload.agenda_items],
                "action_items": [a.model_dump() for a in payload.action_items],
                "task_updates": [t.model_dump() for t in payload.task_updates],
                "risks": payload.risks,
            }
        ),
        task_ids=",".join(task.task_id for task in touched),
    )
    db.add(meeting)
    db.flush()
    replace_meeting_access(db, meeting, payload.participants, payload.viewers)
    if payload.draft_id:
        draft = db.get(MeetingDraft, payload.draft_id)
        if draft and draft.created_by == user.user_id:
            if draft.audio_file:
                _copy_audio(draft, meeting)
            db.delete(draft)
    db.commit()

    for task in touched:
        db.refresh(task)

    return AgendaSubmitResponse(
        meeting_id=meeting.meeting_id,
        updated=updated,
        created=created,
        skipped=skipped,
        tasks=[task_to_out(db, user, t) for t in touched],
    )


@router.get("/drafts", response_model=list[MeetingDraftOut])
def list_drafts(user: CurrentUser, db: DbSession) -> list[MeetingDraftOut]:
    rows = db.scalars(
        select(MeetingDraft)
        .where(MeetingDraft.created_by == user.user_id)
        .order_by(MeetingDraft.updated_at.desc())
    ).all()
    return [draft_to_out(row) for row in rows]


@router.get("/drafts/{draft_id}", response_model=MeetingDraftOut)
def get_draft(draft_id: int, user: CurrentUser, db: DbSession) -> MeetingDraftOut:
    return draft_to_out(_own_draft(db, user, draft_id))


@router.post("/drafts/{draft_id}/transcribe", response_model=MeetingDraftOut)
def retry_draft_transcribe(draft_id: int, user: CurrentUser, db: DbSession) -> MeetingDraftOut:
    draft = _own_draft(db, user, draft_id)
    if not draft.audio_file:
        raise HTTPException(status_code=400, detail="다시 전사할 음성 파일이 없습니다.")
    draft.stt_status = "transcribing"
    draft.stt_error = None
    draft.updated_at = datetime.now()
    db.commit()
    db.refresh(draft)
    _start_stt_job(draft.draft_id, user.user_id, draft.audio_filename or "meeting.wav")
    return draft_to_out(draft)


@router.post("/drafts", response_model=MeetingDraftOut)
def create_draft(payload: MeetingDraftIn, user: CurrentUser, db: DbSession) -> MeetingDraftOut:
    transcript = (payload.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="전사 내용이 비어 있습니다.")
    now = datetime.now()
    draft = MeetingDraft(
        created_by=user.user_id,
        title=payload.title or _draft_title(transcript, payload.event),
        raw_transcript=transcript,
        parsed_json=json.dumps(payload.parsed, ensure_ascii=False) if payload.parsed else "",
        event_json=json.dumps(payload.event, ensure_ascii=False) if payload.event else "",
        step=payload.step,
        created_at=now,
        updated_at=now,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft_to_out(draft)


@router.patch("/drafts/{draft_id}", response_model=MeetingDraftOut)
def update_draft(
    draft_id: int, payload: MeetingDraftIn, user: CurrentUser, db: DbSession
) -> MeetingDraftOut:
    draft = _own_draft(db, user, draft_id)
    if payload.transcript:
        draft.raw_transcript = payload.transcript
    if payload.title:
        draft.title = payload.title
    elif payload.event and payload.event.get("title"):
        draft.title = _draft_title(draft.raw_transcript, payload.event)
    if payload.parsed is not None:
        draft.parsed_json = json.dumps(payload.parsed, ensure_ascii=False)
    if payload.event is not None:
        draft.event_json = json.dumps(payload.event, ensure_ascii=False)
    draft.step = payload.step
    draft.updated_at = datetime.now()
    db.commit()
    db.refresh(draft)
    return draft_to_out(draft)


@router.delete("/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(draft_id: int, user: CurrentUser, db: DbSession) -> None:
    draft = _own_draft(db, user, draft_id)
    delete_recording(draft.audio_file)
    db.delete(draft)
    db.commit()


@router.get("/drafts/{draft_id}/audio")
def get_draft_audio(draft_id: int, user: CurrentUser, db: DbSession) -> FileResponse:
    draft = _own_draft(db, user, draft_id)
    return _audio_response(draft.audio_file, draft.audio_filename, draft.audio_mime)


@router.get("", response_model=list[MeetingOut])
def list_meetings(user: CurrentUser, db: DbSession) -> list[MeetingOut]:
    return [meeting_to_out(m, user) for m in visible_meetings(db, user)]


@router.get("/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: int, user: CurrentUser, db: DbSession) -> MeetingOut:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    if not can_view_meeting(db, user, meeting):
        raise HTTPException(status_code=403, detail="조회 권한이 없습니다.")
    return meeting_to_out(meeting, user)


@router.get("/{meeting_id}/audio")
def get_meeting_audio(meeting_id: int, user: CurrentUser, db: DbSession) -> FileResponse:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    if not can_view_meeting(db, user, meeting):
        raise HTTPException(status_code=403, detail="조회 권한이 없습니다.")
    return _audio_response(meeting.audio_file, meeting.audio_filename, meeting.audio_mime)


@router.patch("/{meeting_id}/access", response_model=MeetingOut)
def update_meeting_access(
    meeting_id: int, payload: MeetingAccessUpdate, user: CurrentUser, db: DbSession
) -> MeetingOut:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    if not can_manage_meeting(user, meeting):
        raise HTTPException(status_code=403, detail="공유 설정을 바꿀 권한이 없습니다.")
    replace_meeting_access(db, meeting, payload.participants, payload.viewers)
    db.commit()
    db.refresh(meeting)
    return meeting_to_out(meeting, user)
