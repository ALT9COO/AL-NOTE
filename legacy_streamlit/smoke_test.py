"""로컬 스모크 테스트: DB 시드 · 인증 · RBAC · AI 목업 파이프라인 검증."""

from datetime import date

from ai_engine import generate_period_report, parse_meeting, summary_to_markdown, transcribe_audio
from auth import authenticate, can_edit_task, get_visible_tasks, scope_dept_ids
from database import Task, get_session, init_db, next_task_id

init_db()
print("[1] DB init OK")

for uid, pw in [("admin", "admin123"), ("leader1", "leader123"), ("member1", "member123")]:
    user = authenticate(uid, pw)
    assert user, f"{uid} 로그인 실패"
    print(f"    로그인 OK: {uid} -> {user['role_level']} / {user['dept_name']}")
assert authenticate("admin", "wrong") is None
print("[2] 인증 OK (잘못된 비밀번호 거부 확인)")

with get_session() as s:
    for uid in ["admin", "leader1", "member1"]:
        u = authenticate(uid, {"admin": "admin123", "leader1": "leader123", "member1": "member123"}[uid])
        tasks = get_visible_tasks(s, u)
        editable = [t.task_id for t in tasks if can_edit_task(s, u, t)]
        print(f"    {uid}: 조회 {len(tasks)}건 {[t.task_id for t in tasks]} / 수정가능 {editable} / dept scope={scope_dept_ids(s, u)}")
print("[3] RBAC OK")

transcript = transcribe_audio(b"fake-bytes", "demo.wav")
assert transcript
print(f"[4] STT(mock) OK - {len(transcript)}자")

with get_session() as s:
    tasks = get_visible_tasks(s, authenticate("leader1", "leader123"))
    tasks_ctx = [
        {"task_id": t.task_id, "task_name": t.task_name, "assigned_to": t.assigned_to,
         "status": t.status, "progress": t.progress,
         "due_date": t.due_date.isoformat() if t.due_date else "", "issues": t.issues or ""}
        for t in tasks
    ]
users_ctx = [
    {"user_id": "leader1", "user_name": "박팀장", "role_level": "LEADER"},
    {"user_id": "member1", "user_name": "이사원", "role_level": "MEMBER"},
]
parsed = parse_meeting(transcript, tasks_ctx, users_ctx)
assert parsed["task_updates"], "업무 업데이트가 비어 있음"
for u in parsed["task_updates"]:
    assert u["status"] in ["시작전", "진행중", "검토필요", "완료"]
    assert 0 <= u["progress"] <= 100
print(f"[5] LLM 파싱(mock) OK - 요약 {len(parsed['summary_bullets'])}개 / 업무 업데이트 {len(parsed['task_updates'])}건")
print(summary_to_markdown(parsed)[:200].replace("\n", " | "))

with get_session() as s:
    new_id = next_task_id(s)
    s.add(Task(task_id=new_id, task_name="스모크 테스트 업무", dept_id=2, assigned_to="member1",
               status="진행중", progress=10, start_date=date.today()))
print(f"[6] Task 생성 OK - {new_id}")
with get_session() as s:
    t = s.get(Task, new_id)
    t.status = "완료"
    t.progress = 100
with get_session() as s:
    t = s.get(Task, new_id)
    assert t.status == "완료" and t.progress == 100
    s.delete(t)
print("[7] Task 수정/삭제 OK")

rows = [{"task_id": t["task_id"], "task_name": t["task_name"], "assignee_name": t["assigned_to"],
         "status": t["status"], "progress": t["progress"], "due_date": t["due_date"],
         "issues": t["issues"], "is_delayed": False} for t in tasks_ctx]
stats = {"total": len(rows), "avg_progress": 55, "완료": 1, "진행중": 2, "검토필요": 1, "시작전": 1}
report = generate_period_report("주간 (2026-08-10 ~ 2026-08-16)", "개발팀", stats, rows)
assert "총평" in report
print(f"[8] 기간 리포트(mock) OK - {len(report)}자")

print("\n[DONE] 전체 스모크 테스트 통과")
