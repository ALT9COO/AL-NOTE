"""DB에 넣는 API 키·OAuth 토큰을 Fernet으로 봉인한다.

값이 이미 `enc:v1:` 로 시작하면 암호화된 것으로 보고, 아니면 평문으로 읽는다.
ENCRYPTION_KEY 가 없으면 JWT_SECRET 에서 키를 파생한다.
"""

from __future__ import annotations

import base64
import hashlib
import logging

logger = logging.getLogger("ainote")

_PREFIX = "enc:v1:"


def _fernet():
    from cryptography.fernet import Fernet

    from config import settings

    material = (settings.encryption_key or settings.jwt_secret or "al-note").encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(plain: str | None) -> str:
    text = (plain or "").strip()
    if not text:
        return ""
    if text.startswith(_PREFIX):
        return text
    try:
        token = _fernet().encrypt(text.encode("utf-8")).decode("ascii")
        return f"{_PREFIX}{token}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("시크릿 암호화 실패 — 평문으로 저장합니다: %s", exc)
        return text


def reveal(stored: str | None) -> str:
    text = stored or ""
    if not text.startswith(_PREFIX):
        return text
    try:
        return _fernet().decrypt(text[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.error("시크릿 복호화 실패: %s", exc)
        return ""


def is_sealed(stored: str | None) -> bool:
    return (stored or "").startswith(_PREFIX)
