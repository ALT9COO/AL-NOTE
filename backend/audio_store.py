"""회의 음성 파일을 DB가 아니라 디스크에 보관한다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from config import BASE_DIR

RECORDINGS_DIR = BASE_DIR / "uploads" / "recordings"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_EXT = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/aac": ".m4a",
    "audio/x-m4a": ".m4a",
}


@dataclass(frozen=True)
class StoredRecording:
    name: str
    original: str
    mime: str
    size: int


def _ext(filename: str, mime: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".webm", ".ogg", ".mp3", ".wav", ".m4a", ".aac", ".mp4"}:
        return ".m4a" if suffix in {".aac", ".mp4"} else suffix
    return _EXT.get((mime or "").split(";")[0].strip().lower(), ".webm")


def _display_name(filename: str) -> str:
    raw = Path(filename or "recording.webm").name
    cleaned = _SAFE_NAME.sub("_", raw).strip("._") or "recording.webm"
    return cleaned[:120]


def save_recording(data: bytes, filename: str, mime: str | None) -> StoredRecording:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid4().hex}{_ext(filename, mime)}"
    path = RECORDINGS_DIR / stored
    path.write_bytes(data)
    return StoredRecording(
        name=stored,
        original=_display_name(filename),
        mime=(mime or "audio/webm").split(";")[0].strip() or "audio/webm",
        size=len(data),
    )


def resolve_recording(name: str | None) -> Path | None:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    path = (RECORDINGS_DIR / name).resolve()
    root = RECORDINGS_DIR.resolve()
    if path != root and root not in path.parents:
        return None
    return path if path.is_file() else None


def read_recording(name: str | None) -> bytes | None:
    path = resolve_recording(name)
    if path is None:
        return None
    return path.read_bytes()


def delete_recording(name: str | None) -> None:
    path = resolve_recording(name)
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass
