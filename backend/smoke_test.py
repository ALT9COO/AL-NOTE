"""백엔드 API 스모크 테스트.

서버를 먼저 띄운 뒤 실행하세요.
    uvicorn main:app --port 8000
    python smoke_test.py
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
    expect: int | tuple[int, ...] = 200,
) -> dict | list | None:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    expected = (expect,) if isinstance(expect, int) else expect
    try:
        with urllib.request.urlopen(request) as response:
            status, payload = response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        status, payload = exc.code, exc.read().decode()

    assert status in expected, f"{method} {path} -> {status} (기대 {expected})\n{payload}"
    return json.loads(payload) if payload else None


def login(user_id: str, password: str) -> tuple[str, dict]:
    result = call("POST", "/api/auth/login", {"user_id": user_id, "password": password})
    return result["access_token"], result["user"]


def main() -> None:
    health = call("GET", "/api/health")
    print(f"[1] health OK — AI mock={health['ai']['mock_mode']}")

    call("POST", "/api/auth/login", {"user_id": "admin", "password": "wrong"}, expect=401)
    call("GET", "/api/tasks", expect=401)
    print("[2] 인증 실패 케이스 차단 확인 (401)")

    tokens = {}
    for uid, pw in [("admin", "admin123"), ("leader1", "leader123"), ("member1", "member123")]:
        token, user = login(uid, pw)
        tokens[uid] = token
        print(f"    로그인 OK: {uid} / {user['role_level']} / {user['dept_name']}")
    print("[3] JWT 로그인 OK")

    for uid, token in tokens.items():
        tasks = call("GET", "/api/tasks", token=token)
        editable = [t["task_id"] for t in tasks if t["can_edit"]]
        print(f"    {uid}: 조회 {len(tasks)}건 {[t['task_id'] for t in tasks]} / 수정가능 {editable}")
    print("[4] RBAC 필터링 OK")

    member_tasks = call("GET", "/api/tasks", token=tokens["member1"])
    # 시드 데이터를 수정한 환경에서는 member1 이 볼 수 있는 모든 업무가 본인 담당일 수 있다.
    forbidden = next((t for t in member_tasks if not t["can_edit"]), None)
    if forbidden:
        call(
            "PATCH",
            f"/api/tasks/{forbidden['task_id']}/status",
            {"status": "완료"},
            token=tokens["member1"],
            expect=403,
        )
        print(f"[5] 권한 없는 업무 수정 차단 OK ({forbidden['task_id']} -> 403)")
    else:
        print("[5] 권한 없는 업무 수정 차단 SKIP (member1 담당이 아닌 업무가 없음)")

    before = call("GET", "/api/tasks/TASK-001", token=tokens["leader1"])
    moved = call(
        "PATCH", "/api/tasks/TASK-001/status", {"status": "이슈 발생"}, token=tokens["leader1"]
    )
    assert moved["status"] == "이슈 발생" and moved["progress"] == before["progress"]
    call(
        "PATCH",
        "/api/tasks/TASK-001/status",
        {"status": "진행중", "progress": 60},
        token=tokens["leader1"],
    )
    print("[6] 드래그앤드롭 상태 변경 OK (이슈 발생 시 진행률 유지)")

    created = call(
        "POST",
        "/api/tasks",
        {
            "task_name": "스모크 테스트 업무",
            "assigned_to": "member1",
            "dept_id": 2,
            "status": "진행중",
            "progress": 20,
            "due_date": "2026-12-31",
        },
        token=tokens["leader1"],
        expect=201,
    )
    task_id = created["task_id"]
    patched = call(
        "PATCH", f"/api/tasks/{task_id}", {"progress": 55, "issues": "테스트 이슈"},
        token=tokens["leader1"],
    )
    assert patched["progress"] == 55
    call("DELETE", f"/api/tasks/{task_id}", token=tokens["leader1"], expect=204)
    print(f"[7] 업무 생성/수정/삭제 OK ({task_id})")

    transcript_payload = {
        "transcript": "박팀장: 로그인 API 진행 상황 공유해주세요. 이사원: 90% 완료했습니다."
    }
    parsed = call(
        "POST", "/api/meetings/parse", transcript_payload, token=tokens["leader1"],
        expect=(200, 502),
    )
    # 연동된 API 키가 유효하지 않으면 502 가 정상 동작이므로 AI 의존 단계는 건너뛴다.
    if "detail" in parsed:
        print(f"[8-12] AI 단계 SKIP — 프로바이더 응답 실패: {parsed['detail'][:80]}")
        admin_smoke(tokens)
        calendar_smoke(tokens)
        print("\n[DONE] 백엔드 API 스모크 테스트 통과 (AI 호출 단계 제외)")
        return

    assert parsed["task_updates"], "업무 업데이트가 비어 있음"
    print(
        f"[8] 회의 파싱 OK — 요약 {len(parsed['summary_bullets'])}개 / 업무 업데이트 {len(parsed['task_updates'])}건"
    )

    submitted = call(
        "POST",
        "/api/meetings/submit",
        {
            "title": "스모크 테스트 회의",
            "transcript": transcript_payload["transcript"],
            "summary_bullets": parsed["summary_bullets"],
            "agenda_items": parsed["agenda_items"],
            "action_items": parsed["action_items"],
            "risks": parsed["risks"],
            "task_updates": parsed["task_updates"],
        },
        token=tokens["leader1"],
    )
    print(
        f"[9] 안건 제출 OK — 업데이트 {len(submitted['updated'])} / 신규 {len(submitted['created'])} / 스킵 {len(submitted['skipped'])}"
    )

    meetings = call("GET", "/api/meetings", token=tokens["leader1"])
    assert meetings, "회의록이 저장되지 않음"
    meeting_id = meetings[0]["meeting_id"]
    print(f"[10] 회의록 저장 확인 OK — {meetings[0]['title']}")

    call("GET", f"/api/meetings/{meeting_id}", token=tokens["member1"], expect=403)
    call("GET", f"/api/meetings/{meeting_id}", token=tokens["admin"], expect=200)
    shared = call(
        "PATCH",
        f"/api/meetings/{meeting_id}/access",
        {"participants": [{"kind": "user", "user_id": "member1"}], "viewers": []},
        token=tokens["leader1"],
    )
    assert any(p.get("user_id") == "member1" for p in shared["participants"]), shared
    call("GET", f"/api/meetings/{meeting_id}", token=tokens["member1"], expect=200)
    call(
        "PATCH",
        f"/api/meetings/{meeting_id}/access",
        {"participants": [], "viewers": []},
        token=tokens["member1"],
        expect=403,
    )
    print("[10b] 회의록 기본 비공개 · 참여자 공유 · 권한 없는 수정 차단 OK")

    summary = call("GET", "/api/analytics/summary?period=weekly", token=tokens["admin"])
    print(
        f"[11] 애널리틱스 OK — 전체 {summary['total']}건 / 완료율 {summary['completion_rate']}% / 지연 {summary['delayed']}건 / trend {len(summary['trend'])}포인트"
    )

    report = call(
        "POST", "/api/analytics/report", {"period": "weekly"}, token=tokens["admin"]
    )
    assert "총평" in report["report_markdown"]
    print(f"[12] AI 리포트 OK — {len(report['report_markdown'])}자")

    admin_smoke(tokens)
    calendar_smoke(tokens)

    print("\n[DONE] 백엔드 API 스모크 테스트 전체 통과")


def admin_smoke(tokens: dict[str, str]) -> None:
    """관리자 전용 사용자 · 조직 · 권한 관리 API."""
    admin, leader, member = tokens["admin"], tokens["leader1"], tokens["member1"]

    call("GET", "/api/admin/users", token=leader, expect=403)
    call("GET", "/api/admin/departments", token=member, expect=403)
    print("[13] 비관리자 접근 차단 OK (403)")

    dept = call(
        "POST", "/api/admin/departments", {"dept_name": "디자인팀", "parent_dept_id": 1},
        token=admin, expect=201,
    )
    dept_id = dept["dept_id"]
    call(
        "POST", "/api/admin/departments", {"dept_name": "디자인팀"}, token=admin, expect=409
    )
    call(
        "PATCH", f"/api/admin/departments/{dept_id}", {"parent_dept_id": dept_id},
        token=admin, expect=400,
    )
    renamed = call(
        "PATCH", f"/api/admin/departments/{dept_id}", {"dept_name": "프로덕트디자인팀"},
        token=admin,
    )
    assert renamed["dept_name"] == "프로덕트디자인팀"
    call("PATCH", "/api/admin/departments/1", {"parent_dept_id": 2}, token=admin, expect=400)
    call("DELETE", "/api/admin/departments/2", token=admin, expect=409)
    print(f"[14] 조직 등록/수정/검증 OK (dept_id={dept_id}, 순환·중복·삭제 차단 확인)")

    new_user = call(
        "POST",
        "/api/admin/users",
        {
            "user_id": "designer1",
            "user_name": "정디자",
            "password": "design123",
            "role_level": "MEMBER",
            "dept_id": dept_id,
        },
        token=admin,
        expect=201,
    )
    assert new_user["dept_name"] == "프로덕트디자인팀"
    call(
        "POST",
        "/api/admin/users",
        {"user_id": "designer1", "user_name": "중복", "password": "dup12345"},
        token=admin,
        expect=409,
    )
    designer_token, designer = login("designer1", "design123")
    print(f"[15] 사용자 등록 OK — {designer['user_name']} / {designer['role_level']} 로그인 확인")

    call(
        "PATCH", "/api/admin/users/designer1", {"role_level": "LEADER"}, token=admin
    )
    promoted = call("GET", "/api/auth/me", token=designer_token)
    assert promoted["role_level"] == "LEADER"
    call("PATCH", "/api/admin/users/admin", {"role_level": "MEMBER"}, token=admin, expect=400)
    call("DELETE", "/api/admin/users/admin", token=admin, expect=400)
    print("[16] 권한 변경 OK (본인 권한 변경 · 마지막 관리자 삭제 차단 확인)")

    call(
        "PATCH", "/api/admin/users/designer1", {"password": "newpass123"}, token=admin
    )
    call("POST", "/api/auth/login", {"user_id": "designer1", "password": "design123"}, expect=401)
    login("designer1", "newpass123")
    print("[17] 비밀번호 초기화 OK")

    created = call(
        "POST",
        "/api/tasks",
        {"task_name": "관리자 테스트 업무", "assigned_to": "designer1", "dept_id": dept_id},
        token=admin,
        expect=201,
    )
    call("DELETE", "/api/admin/users/designer1", token=admin, expect=409)
    call("DELETE", "/api/admin/users/designer1?reassign_to=admin", token=admin, expect=204)
    moved = call("GET", f"/api/tasks/{created['task_id']}", token=admin)
    assert moved["assigned_to"] == "admin"
    call("DELETE", f"/api/tasks/{created['task_id']}", token=admin, expect=204)
    call("DELETE", f"/api/admin/departments/{dept_id}", token=admin, expect=204)
    print("[18] 사용자 삭제 · 업무 인수인계 · 부서 삭제 OK")

    integration_smoke(admin, leader)


DUMMY_KEYS = {
    "openai": "sk-smoke-dummy-0123456789abcdef",
    "anthropic": "sk-ant-smoke-dummy-0123456789",
    "google": "AIzaSySMOKE-dummy-0123456789",
}


def integration_smoke(admin: str, leader: str) -> None:
    """API 연동(OpenAI/Claude/Gemini) 설정과 사용량 집계.

    실제 등록된 키를 건드리지 않도록 '키가 없는 프로바이더'를 골라 테스트하고,
    끝나면 원래 활성 엔진으로 되돌린다.
    """
    call("GET", "/api/admin/integrations", token=leader, expect=403)
    data = call("GET", "/api/admin/integrations", token=admin)
    providers = {p["provider"]: p for p in data["providers"]}
    assert set(providers) == {"openai", "anthropic", "google"}, providers.keys()
    assert providers["openai"]["supports_stt"] is True
    assert providers["google"]["supports_stt"] is True
    assert providers["anthropic"]["supports_stt"] is False
    print(
        f"[19] API 연동 목록 OK — {', '.join(p['label'] for p in data['providers'])} "
        f"/ 활성 {data['active_provider']} / 데모모드 {data['mock_mode']}"
    )

    origin_active = data["active_provider"] if data["llm_ready"] else None
    target = next((name for name, p in providers.items() if not p["has_key"]), None)
    if target is None:
        print("[20-23] API 연동 쓰기 테스트 SKIP (모든 프로바이더에 실제 키가 등록되어 있음)")
        return

    wrong_model = next(m for p, meta in providers.items() if p != target for m in meta["models"])
    call(
        "PATCH", f"/api/admin/integrations/{target}",
        {"text_model": wrong_model}, token=admin, expect=400,
    )
    call(
        "PATCH", f"/api/admin/integrations/{target}", {"activate": True}, token=admin, expect=400
    )
    model = providers[target]["default_model"]
    saved = call(
        "PATCH",
        f"/api/admin/integrations/{target}",
        {"api_key": DUMMY_KEYS[target], "text_model": model, "activate": True},
        token=admin,
    )
    row = next(p for p in saved["providers"] if p["provider"] == target)
    assert saved["active_provider"] == target, saved["active_provider"]
    assert row["has_key"] and "•" in row["masked_key"], row
    assert "smoke-dummy" not in json.dumps(saved), "원본 키가 응답에 노출되면 안 됩니다"
    assert sum(1 for p in saved["providers"] if p["is_active"]) == 1, "활성 엔진은 1개여야 합니다"
    print(
        f"[20] 프로바이더 전환 OK — 활성 {saved['active_provider']}/{saved['active_model']} "
        f"/ 마스킹 {row['masked_key']} / 모델·활성화 검증 완료"
    )

    result = call("POST", f"/api/admin/integrations/{target}/test", token=admin)
    assert result["ok"] is False, "더미 키로는 연결이 성공하면 안 됩니다"
    print(f"[21] 연결 테스트 OK — 실패 응답 정상 처리 ({result['message'][:60]}...)")

    usage = call("GET", "/api/admin/usage?days=7", token=admin)
    assert usage["totals"]["calls"] >= 1, usage["totals"]
    features = {f["feature"] for f in usage["by_feature"]}
    assert "연결 테스트" in features, features
    assert any(p["provider"] == target and p["calls"] >= 1 for p in usage["by_provider"])
    assert len(usage["daily"]) == 7
    print(
        f"[22] 사용량 집계 OK — 호출 {usage['totals']['calls']}건 "
        f"(성공 {usage['totals']['success']} / 실패 {usage['totals']['error']} / 데모 {usage['totals']['mock']}) "
        f"/ 기능 {sorted(features)}"
    )

    restored = call("PATCH", f"/api/admin/integrations/{target}", {"api_key": ""}, token=admin)
    assert not any(p["provider"] == target and p["has_key"] for p in restored["providers"])
    if origin_active and restored["active_provider"] != origin_active:
        restored = call(
            "PATCH", f"/api/admin/integrations/{origin_active}", {"activate": True}, token=admin
        )
    assert restored["active_provider"] == (origin_active or restored["active_provider"])
    print(
        f"[23] 더미 키 삭제 · 활성 엔진 복구 OK (현재 활성 {restored['active_provider']})"
    )


def calendar_smoke(tokens: dict[str, str]) -> None:
    """사용자별 Microsoft 365(Graph) 캘린더 연동 · 일정 → 회의록 연결."""
    leader = tokens["leader1"]
    admin = tokens["admin"]

    call("GET", "/api/calendar/connection", expect=401)
    status_before = call("GET", "/api/calendar/connection", token=leader)
    print(
        f"[24] 캘린더 연결 상태 조회 OK — connected={status_before['connected']} "
        f"/ 앱 등록={status_before['app_configured']}"
    )

    # Azure 앱 설정은 ADMIN 전용, 시크릿은 마스킹되어야 한다.
    call("GET", "/api/calendar/app", token=leader, expect=403)
    app_before = call("GET", "/api/calendar/app", token=admin)

    if not app_before["configured"]:
        # 앱 미등록 상태에서는 로그인 URL 발급이 막혀야 한다.
        call("GET", "/api/calendar/login-url", token=leader, expect=400)
        saved = call(
            "PUT",
            "/api/calendar/app",
            {
                "client_id": "00000000-1111-2222-3333-444444444444",
                "client_secret": "smoke-dummy-secret-value",
                "tenant_id": "common",
                "redirect_uri": "http://localhost:8000/api/calendar/callback",
            },
            token=admin,
        )
        assert saved["configured"] is True, saved
        assert "smoke-dummy-secret-value" not in json.dumps(saved), "시크릿이 그대로 노출됨"
        login = call("GET", "/api/calendar/login-url", token=leader)
        assert "login.microsoftonline.com" in login["url"], login
        assert "Calendars.ReadWrite" in login["url"], login
        assert "Mail.Send" in login["url"], login
        call("DELETE", "/api/calendar/app", token=admin, expect=204)
        print("[25] Azure 앱 설정 OK — ADMIN 전용 · 시크릿 마스킹 · 로그인 URL 생성/차단 확인")
    else:
        login = call("GET", "/api/calendar/login-url", token=leader)
        assert "login.microsoftonline.com" in login["url"], login
        assert "Calendars.ReadWrite" in login["url"], login
        assert "Mail.Send" in login["url"], login
        print("[25] Azure 앱 설정 OK — 이미 등록됨(값 보존) · 로그인 URL 생성 확인")

    call("POST", "/api/calendar/sync", token=leader, expect=(404, 200))
    # 연결 없음·권한 부족·시각 오류 모두 생성/발송 전에 막혀야 한다 (실일정·실메일은 만들지 않음).
    call(
        "POST",
        "/api/calendar/events",
        {
            "title": "스모크 후속 일정",
            "start": "2026-08-17T11:00:00",
            "end": "2026-08-17T10:00:00",
        },
        token=leader,
        expect=(400, 401, 502),
    )
    call(
        "POST",
        "/api/analytics/report/email",
        {"period": "weekly", "to": ["not-an-email"]},
        token=leader,
        expect=(400, 401),
    )

    data = call("GET", "/api/calendar/events?sample=true&days_ahead=14", token=leader)
    events = data["events"]
    assert len(events) >= 3, events
    first = events[0]
    assert first["title"] and first["start"], first
    assert "member1" in first["matched_user_ids"], first["matched_user_ids"]
    print(
        f"[26] 샘플 일정 조회 OK — {len(events)}건 / 첫 일정 '{first['title']}' "
        f"/ 참석자 매칭 {first['matched_user_ids']}"
    )

    # 같은 날 재실행하면 앞 일정이 이미 연결돼 있으므로 아직 비어 있는 일정을 고른다.
    target = next((e for e in events if e["meeting_id"] is None), None)
    if target is None:
        linked = events[0]
        print(
            f"[27-28] 일정 연결 SKIP — 샘플 일정이 모두 연결됨 "
            f"(예: '{linked['title']}' → {linked['meeting_title']})"
        )
        return
    first = target

    submitted = call(
        "POST",
        "/api/meetings/submit",
        {
            "title": f"[스모크] {first['title']}",
            "transcript": "캘린더 연동 확인용 전사입니다.",
            "summary_bullets": ["캘린더 일정 기준으로 회의록을 저장"],
            "task_updates": [],
            "event_key": first["event_key"],
            "event_start": first["start"],
            "event_location": first["location"],
        },
        token=leader,
    )
    meeting_id = submitted["meeting_id"]
    saved = call(f"GET", f"/api/meetings/{meeting_id}", token=leader)
    assert saved["event_key"] == first["event_key"], saved
    assert saved["event_location"] == first["location"]
    print(f"[27] 일정 연결 회의록 저장 OK — meeting_id={meeting_id} / {saved['event_start']}")

    relinked = call("GET", "/api/calendar/events?sample=true&days_ahead=14", token=leader)
    linked = next(e for e in relinked["events"] if e["event_key"] == first["event_key"])
    assert linked["meeting_id"] == meeting_id, linked
    other = call("GET", "/api/calendar/connection", token=tokens["member1"])
    assert other["connected"] is False, "다른 사용자의 캘린더 연결이 섞였습니다."
    print(
        f"[28] 일정↔회의록 매핑 OK — '{linked['title']}' → {linked['meeting_title']} "
        "/ 캘린더 연결은 사용자별로 분리됨"
    )

    cleanup_sample_meetings()


def cleanup_sample_meetings() -> int:
    """샘플 일정으로 만든 테스트 회의록을 지운다 (화면에 남지 않도록)."""
    from database import Meeting, SessionLocal

    with SessionLocal() as db:
        rows = [
            m
            for m in db.query(Meeting).all()
            if (m.event_key or "").startswith("sample-")
            or m.title.startswith("[스모크]")
            or m.title == "스모크 테스트 회의"
        ]
        for row in rows:
            db.delete(row)
        db.commit()
    if rows:
        print(f"[정리] 샘플 회의록 {len(rows)}건 삭제")
    return len(rows)


if __name__ == "__main__":
    main()
