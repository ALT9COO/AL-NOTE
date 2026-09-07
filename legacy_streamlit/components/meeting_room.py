"""AI 회의실: 음성 녹음/업로드 → Whisper STT → LLM 파싱 → 검토 후 업무 자동 반영."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

import streamlit as st

from ai_engine import (
    AIEngineError,
    ai_status,
    parse_meeting,
    summary_to_markdown,
    transcribe_audio,
)
from auth import assignable_users, can_edit_task, get_visible_tasks, visible_meetings
from config import STATUSES, SUPPORTED_AUDIO
from database import Meeting, Task, get_session, next_task_id, user_map

K_TRANSCRIPT = "mr_transcript"
K_PARSED = "mr_parsed"
K_AUDIO_NAME = "mr_audio_name"
K_NONCE = "mr_nonce"
NEW_TASK = "NEW"


def _reset_workflow() -> None:
    for key in (K_TRANSCRIPT, K_PARSED, K_AUDIO_NAME, K_NONCE):
        st.session_state.pop(key, None)


# --------------------------------------------------------------------------- #
# Context builders
# --------------------------------------------------------------------------- #
def _build_context(user: dict[str, Any]) -> tuple[list[dict], list[dict], dict[str, str]]:
    with get_session() as session:
        tasks = get_visible_tasks(session, user)
        members = assignable_users(session, user)
        tasks_context = [
            {
                "task_id": t.task_id,
                "task_name": t.task_name,
                "assigned_to": t.assigned_to,
                "status": t.status,
                "progress": t.progress,
                "due_date": t.due_date.isoformat() if t.due_date else "",
                "issues": t.issues or "",
            }
            for t in tasks
        ]
        users_context = [
            {"user_id": u.user_id, "user_name": u.user_name, "role_level": u.role_level}
            for u in members
        ]
        labels = {u.user_id: f"{u.user_name} ({u.user_id})" for u in members}
    return tasks_context, users_context, labels


# --------------------------------------------------------------------------- #
# Step 1 · 오디오 입력 & STT
# --------------------------------------------------------------------------- #
def _render_input_step() -> None:
    st.markdown("#### 1️⃣ 회의 음성 입력")
    status = ai_status()
    if not status["stt_ready"]:
        st.info("OPENAI_API_KEY 가 없어 STT 는 데모 전사 텍스트로 대체됩니다.", icon="🧪")

    tab_upload, tab_record, tab_text = st.tabs(["📁 파일 업로드", "🎙️ 브라우저 녹음", "⌨️ 텍스트 직접 입력"])

    audio_bytes: bytes | None = None
    audio_name = "meeting.wav"

    with tab_upload:
        uploaded = st.file_uploader(
            "회의 녹음 파일 (mp3 / m4a / wav)", type=SUPPORTED_AUDIO, key="mr_uploader"
        )
        if uploaded is not None:
            st.audio(uploaded)
            audio_bytes, audio_name = uploaded.getvalue(), uploaded.name

    with tab_record:
        if hasattr(st, "audio_input"):
            recorded = st.audio_input("마이크로 회의 녹음", key="mr_recorder")
            if recorded is not None:
                audio_bytes, audio_name = recorded.getvalue(), "recording.wav"
        else:  # pragma: no cover - 구버전 streamlit
            st.warning("현재 Streamlit 버전에서는 브라우저 녹음을 지원하지 않습니다. 파일 업로드를 사용하세요.")

    with tab_text:
        # 폼으로 감싸야 입력 직후 첫 클릭에서 값이 함께 커밋된다.
        with st.form("manual_text_form"):
            manual = st.text_area("회의 내용을 직접 붙여넣기", height=180, key="mr_manual")
            use_text = st.form_submit_button("이 텍스트 사용", width="stretch")
        if use_text:
            if manual.strip():
                st.session_state[K_TRANSCRIPT] = manual.strip()
                st.session_state[K_AUDIO_NAME] = "manual_input"
                st.session_state.pop(K_PARSED, None)
                st.rerun()
            else:
                st.warning("텍스트를 입력하세요.")

    if audio_bytes:
        if st.button("🎧 음성 → 텍스트 변환 (Whisper)", type="primary", width="stretch"):
            with st.spinner("음성을 텍스트로 변환하는 중입니다..."):
                try:
                    transcript = transcribe_audio(audio_bytes, audio_name)
                except AIEngineError as exc:
                    st.error(str(exc))
                    return
            st.session_state[K_TRANSCRIPT] = transcript
            st.session_state[K_AUDIO_NAME] = audio_name
            st.session_state.pop(K_PARSED, None)
            st.rerun()


# --------------------------------------------------------------------------- #
# Step 2 · 전사 확인 & AI 분석
# --------------------------------------------------------------------------- #
def _render_transcript_step(user: dict[str, Any]) -> None:
    st.markdown("#### 2️⃣ 전사 텍스트 확인 및 AI 분석")

    with st.form("transcript_form"):
        transcript = st.text_area(
            "전사 텍스트 (필요 시 직접 수정 가능)",
            value=st.session_state.get(K_TRANSCRIPT, ""),
            height=240,
            key="mr_transcript_edit",
        )
        col1, col2 = st.columns([3, 1])
        analyze = col1.form_submit_button("🤖 AI 회의 분석 실행", type="primary", width="stretch")
        reset = col2.form_submit_button("🗑️ 초기화", width="stretch")

    if reset:
        _reset_workflow()
        st.rerun()

    if analyze:
        st.session_state[K_TRANSCRIPT] = transcript
        tasks_context, users_context, _ = _build_context(user)
        with st.spinner("회의 내용을 분석하고 업무 업데이트를 추출하는 중입니다..."):
            try:
                parsed = parse_meeting(transcript, tasks_context, users_context)
            except AIEngineError as exc:
                st.error(str(exc))
                return
        st.session_state[K_PARSED] = parsed
        st.session_state[K_NONCE] = uuid4().hex[:8]
        st.rerun()


# --------------------------------------------------------------------------- #
# Step 3 · Human-in-the-Loop 검토 & 제출
# --------------------------------------------------------------------------- #
def _apply_updates(
    user: dict[str, Any],
    title: str,
    transcript: str,
    parsed: dict[str, Any],
    edited_updates: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    """검토 완료된 업데이트를 Tasks 에 반영하고 Meeting 레코드를 저장한다."""
    updated: list[str] = []
    created: list[str] = []
    skipped: list[str] = []

    with get_session() as session:
        member_dept = {u.user_id: u.dept_id for u in assignable_users(session, user)}

        for item in edited_updates:
            task_id = item["task_id"]
            if task_id == NEW_TASK:
                new_id = next_task_id(session)
                task = Task(
                    task_id=new_id,
                    task_name=item["task_name"] or "제목 없는 업무",
                    dept_id=member_dept.get(item["assignee"], user["dept_id"]),
                    assigned_to=item["assignee"] or None,
                    status=item["status"],
                    progress=item["progress"],
                    start_date=date.today(),
                    due_date=item["due_date"],
                    issues=item["issues"],
                    description=f"{title} 회의에서 자동 생성됨",
                )
                session.add(task)
                session.flush()
                created.append(f"{new_id} {task.task_name}")
                continue

            task = session.get(Task, task_id)
            if not task:
                skipped.append(f"{task_id} (존재하지 않음)")
                continue
            if not can_edit_task(session, user, task):
                skipped.append(f"{task_id} (수정 권한 없음)")
                continue

            task.status = item["status"]
            task.progress = item["progress"]
            task.issues = item["issues"]
            if item["assignee"]:
                task.assigned_to = item["assignee"]
            if item["due_date"]:
                task.due_date = item["due_date"]
            task.updated_at = datetime.now()
            updated.append(f"{task_id} {task.task_name}")

        session.add(
            Meeting(
                title=title or parsed.get("meeting_title", "제목 없는 회의"),
                created_by=user["user_id"],
                dept_id=user["dept_id"],
                raw_transcript=transcript,
                ai_summary=summary_to_markdown({**parsed, "task_updates": edited_updates}),
            )
        )

    return updated, created, skipped


def _render_review_step(user: dict[str, Any]) -> None:
    parsed: dict[str, Any] = st.session_state[K_PARSED]
    nonce: str = st.session_state.get(K_NONCE, "0")
    tasks_context, _, user_labels = _build_context(user)
    task_options = [NEW_TASK] + [t["task_id"] for t in tasks_context]
    task_names = {t["task_id"]: t["task_name"] for t in tasks_context}
    assignee_options = [""] + list(user_labels.keys())

    st.markdown("#### 3️⃣ 안건 검토 및 제출 (Human-in-the-Loop)")
    st.caption("AI 가 추출한 내용을 확인하고 수정한 뒤 제출하면 업무 현황에 즉시 반영됩니다.")

    col_sum, col_meta = st.columns([2, 1])
    with col_sum:
        st.markdown("##### 📝 AI 요약")
        for bullet in parsed.get("summary_bullets", []):
            st.markdown(f"- {bullet}")
        if parsed.get("agenda_items"):
            with st.expander("안건별 논의 내용", expanded=False):
                for i, item in enumerate(parsed["agenda_items"], start=1):
                    st.markdown(f"**{i}. {item['topic']}**")
                    if item.get("discussion"):
                        st.caption(f"논의: {item['discussion']}")
                    if item.get("decision"):
                        st.caption(f"결정: {item['decision']}")
    with col_meta:
        st.markdown("##### ⚡ 액션 아이템")
        if parsed.get("action_items"):
            for item in parsed["action_items"]:
                owner = user_labels.get(item.get("assignee", ""), item.get("assignee") or "미지정")
                due = item.get("due_date") or "기한 미정"
                st.markdown(f"- {item['title']}  \n  <small>👤 {owner} · 📅 {due}</small>", unsafe_allow_html=True)
        else:
            st.caption("추출된 액션 아이템이 없습니다.")
        if parsed.get("risks"):
            st.markdown("##### 🚨 리스크")
            for risk in parsed["risks"]:
                st.markdown(f"- {risk}")

    st.divider()

    with st.form("agenda_submit_form"):
        title = st.text_input("회의 제목", value=parsed.get("meeting_title", "제목 없는 회의"))
        st.markdown("##### 📌 업무 업데이트 안건 카드")

        updates = parsed.get("task_updates", [])
        if not updates:
            st.info("추출된 업무 업데이트가 없습니다. 필요하면 아래에서 신규 업무를 추가하세요.")

        edited: list[dict[str, Any]] = []
        for i, item in enumerate(updates):
            default_id = item["task_id"] if item["task_id"] in task_options else NEW_TASK
            label = task_names.get(default_id, item.get("task_name", "신규 업무"))
            with st.container(border=True):
                head, chk = st.columns([5, 1])
                head.markdown(f"**#{i + 1} · {label}**")
                include = chk.checkbox("반영", value=True, key=f"inc_{nonce}_{i}")

                c1, c2, c3 = st.columns(3)
                task_id = c1.selectbox(
                    "연결 업무",
                    task_options,
                    index=task_options.index(default_id),
                    format_func=lambda x: "🆕 신규 업무 생성" if x == NEW_TASK else f"{x} · {task_names.get(x, '')}",
                    key=f"tid_{nonce}_{i}",
                )
                assignee_default = item.get("assignee", "")
                assignee = c2.selectbox(
                    "담당자",
                    assignee_options,
                    index=assignee_options.index(assignee_default)
                    if assignee_default in assignee_options
                    else 0,
                    format_func=lambda x: user_labels.get(x, "미지정"),
                    key=f"asg_{nonce}_{i}",
                )
                status = c3.selectbox(
                    "상태",
                    STATUSES,
                    index=STATUSES.index(item["status"]) if item["status"] in STATUSES else 1,
                    key=f"sts_{nonce}_{i}",
                )

                c4, c5 = st.columns([2, 1])
                progress = c4.slider(
                    "진행률(%)", 0, 100, int(item.get("progress", 0)), step=5, key=f"prg_{nonce}_{i}"
                )
                raw_due = item.get("due_date") or ""
                due = c5.date_input(
                    "마감일",
                    value=date.fromisoformat(raw_due) if raw_due else None,
                    format="YYYY-MM-DD",
                    key=f"due_{nonce}_{i}",
                )

                task_name = st.text_input(
                    "업무명", value=item.get("task_name", ""), key=f"nm_{nonce}_{i}"
                )
                issues = st.text_area(
                    "이슈 / 특이사항", value=item.get("issues", ""), height=70, key=f"iss_{nonce}_{i}"
                )

                if include:
                    edited.append(
                        {
                            "task_id": task_id,
                            "task_name": task_name,
                            "assignee": assignee,
                            "status": status,
                            "progress": progress,
                            "due_date": due,
                            "issues": issues,
                        }
                    )

        submitted = st.form_submit_button(
            "✅ 최종 제출 · 업무 현황 반영", type="primary", width="stretch"
        )

    if submitted:
        transcript = st.session_state.get(K_TRANSCRIPT, "")
        updated, created, skipped = _apply_updates(user, title, transcript, parsed, edited)
        st.success(
            f"회의록이 저장되었습니다. 업데이트 {len(updated)}건 / 신규 생성 {len(created)}건 / 건너뜀 {len(skipped)}건"
        )
        for text in updated:
            st.markdown(f"- 🔄 {text}")
        for text in created:
            st.markdown(f"- 🆕 {text}")
        for text in skipped:
            st.markdown(f"- ⛔ {text}")

        _reset_workflow()
        st.balloons()
        if st.button("새 회의 시작", type="primary"):
            st.rerun()


# --------------------------------------------------------------------------- #
# 회의록 히스토리
# --------------------------------------------------------------------------- #
def _render_history(user: dict[str, Any]) -> None:
    with get_session() as session:
        meetings = visible_meetings(session, user)
        names = user_map(session)

    if not meetings:
        st.caption("저장된 회의록이 없습니다.")
        return

    for meeting in meetings:
        header = (
            f"🗓️ {meeting.created_at:%Y-%m-%d %H:%M} · {meeting.title} "
            f"(작성: {names.get(meeting.created_by, '-')})"
        )
        with st.expander(header):
            st.markdown(meeting.ai_summary or "_요약 없음_")
            with st.expander("원본 전사 보기"):
                st.text(meeting.raw_transcript or "")


# --------------------------------------------------------------------------- #
# 메인 렌더러
# --------------------------------------------------------------------------- #
def render(user: dict[str, Any]) -> None:
    st.subheader("🎙️ AI 회의실")
    st.caption("녹음 한 번으로 회의록 요약부터 업무 현황 업데이트까지 자동화합니다.")

    tab_new, tab_history = st.tabs(["🆕 새 회의 처리", "📚 회의록 히스토리"])

    with tab_new:
        if K_PARSED in st.session_state:
            _render_review_step(user)
        elif st.session_state.get(K_TRANSCRIPT):
            _render_transcript_step(user)
        else:
            _render_input_step()

    with tab_history:
        _render_history(user)
