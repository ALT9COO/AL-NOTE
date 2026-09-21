"""회의 분석 결과가 기존 업무 F/U 를 신규로 만들지 않는지 검증한다."""

from __future__ import annotations

import unittest

from ai_engine import normalize_parsed


TASKS = [
    {
        "task_id": "TASK-001",
        "task_name": "로그인 API 개발",
        "assigned_to": "member1",
        "status": "진행중",
        "progress": 80,
        "due_date": "2026-09-30",
        "issues": "",
    },
    {
        "task_id": "TASK-002",
        "task_name": "대시보드 UI 퍼블리싱",
        "assigned_to": "member1",
        "status": "진행중",
        "progress": 50,
        "due_date": "2026-10-15",
        "issues": "",
    },
]
USERS = [{"user_id": "member1", "user_name": "이사원"}]


class FollowUpNormalizeTest(unittest.TestCase):
    def test_followup_action_updates_existing_not_new(self) -> None:
        parsed = normalize_parsed(
            {
                "meeting_title": "주간 점검",
                "action_items": [
                    {
                        "title": "로그인 API F/U",
                        "assignee": "member1",
                        "due_date": "2026-10-07",
                        "note": "토큰 정책 재확인",
                    }
                ],
                "task_updates": [],
            },
            TASKS,
            USERS,
        )
        updates = parsed["task_updates"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["task_id"], "TASK-001")
        self.assertFalse(updates[0]["is_new"])
        self.assertEqual(updates[0]["task_name"], "로그인 API 개발")
        self.assertEqual(updates[0]["due_date"], "2026-10-07")
        self.assertEqual(updates[0]["issues"], "토큰 정책 재확인")

    def test_bare_followup_is_not_created_as_new_task(self) -> None:
        parsed = normalize_parsed(
            {
                "meeting_title": "주간 점검",
                "action_items": [{"title": "로그인 API 후속 확인", "assignee": "", "due_date": "", "note": ""}],
                "task_updates": [],
            },
            TASKS,
            USERS,
        )
        self.assertFalse(parsed["task_updates"])
        self.assertEqual(parsed["action_items"][0]["title"], "로그인 API 후속 확인")

    def test_llm_new_followup_is_remapped_without_renaming(self) -> None:
        parsed = normalize_parsed(
            {
                "meeting_title": "주간 점검",
                "task_updates": [
                    {
                        "task_id": "NEW",
                        "task_name": "로그인 API 개발 후속",
                        "status": "이슈 발생",
                        "progress": 80,
                        "issues": "보안팀 회신 대기",
                        "assignee": "member1",
                        "due_date": "",
                    }
                ],
            },
            TASKS,
            USERS,
        )
        updates = parsed["task_updates"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["task_id"], "TASK-001")
        self.assertFalse(updates[0]["is_new"])
        self.assertEqual(updates[0]["task_name"], "로그인 API 개발")
        self.assertEqual(updates[0]["status"], "이슈 발생")

    def test_genuine_new_work_stays_new(self) -> None:
        parsed = normalize_parsed(
            {
                "meeting_title": "주간 점검",
                "action_items": [
                    {"title": "보안 감사 착수", "assignee": "member1", "due_date": "2026-11-01", "note": ""}
                ],
                "task_updates": [],
            },
            TASKS,
            USERS,
        )
        updates = parsed["task_updates"]
        self.assertEqual(len(updates), 1)
        self.assertTrue(updates[0]["is_new"])
        self.assertEqual(updates[0]["task_name"], "보안 감사 착수")

    def test_generic_api_followup_does_not_steal_existing_task(self) -> None:
        parsed = normalize_parsed(
            {
                "meeting_title": "주간 점검",
                "action_items": [{"title": "API 후속", "assignee": "", "due_date": "", "note": ""}],
                "task_updates": [],
            },
            TASKS,
            USERS,
        )
        self.assertEqual(len(parsed["task_updates"]), 1)
        self.assertTrue(parsed["task_updates"][0]["is_new"])
        self.assertEqual(parsed["task_updates"][0]["task_name"], "API 후속")


if __name__ == "__main__":
    unittest.main()
