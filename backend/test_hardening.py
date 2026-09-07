"""암호화 · 로그인 제한 · STT 모델 폴백 단위 테스트."""

from __future__ import annotations

import unittest

from ai_engine import _gemini_stt_models
from rate_limit import reset, too_many
from secret_box import is_sealed, reveal, seal


class SecretBoxTest(unittest.TestCase):
    def test_roundtrip(self) -> None:
        token = seal("sk-test-key")
        self.assertTrue(is_sealed(token))
        self.assertEqual(reveal(token), "sk-test-key")
        self.assertEqual(seal(token), token)

    def test_plain_passthrough(self) -> None:
        self.assertEqual(reveal("plain-key"), "plain-key")
        self.assertFalse(is_sealed("plain-key"))

    def test_empty(self) -> None:
        self.assertEqual(seal(""), "")
        self.assertEqual(reveal(""), "")


class RateLimitTest(unittest.TestCase):
    def test_blocks_after_limit(self) -> None:
        key = "test-limit-unique"
        reset(key)
        for _ in range(8):
            self.assertFalse(too_many(key, limit=8, window_sec=60))
        self.assertTrue(too_many(key, limit=8, window_sec=60))
        reset(key)
        self.assertFalse(too_many(key, limit=8, window_sec=60))
        reset(key)


class GeminiModelsTest(unittest.TestCase):
    def test_prefers_then_flash(self) -> None:
        names = _gemini_stt_models("gemini-3.5-flash")
        self.assertTrue(names)
        self.assertEqual(names[0], "gemini-3.5-flash")
        self.assertTrue(all("pro" not in name.lower() or name == "gemini-3.5-flash" for name in names))


if __name__ == "__main__":
    unittest.main()
