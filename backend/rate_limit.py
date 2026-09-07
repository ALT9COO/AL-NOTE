"""로그인 등 민감 API의 간단한 메모리 속도 제한."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

_lock = Lock()
_hits: dict[str, list[float]] = defaultdict(list)


def too_many(key: str, *, limit: int = 8, window_sec: int = 600) -> bool:
    """window 안에 limit 회를 넘기면 True. 호출 시점에 1회를 기록한다."""
    now = time.monotonic()
    cutoff = now - window_sec
    with _lock:
        bucket = [stamp for stamp in _hits[key] if stamp >= cutoff]
        if len(bucket) >= limit:
            _hits[key] = bucket
            return True
        bucket.append(now)
        _hits[key] = bucket
        return False


def reset(key: str) -> None:
    with _lock:
        _hits.pop(key, None)
