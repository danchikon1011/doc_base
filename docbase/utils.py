from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Iterable

ALLOWED_EXTENSIONS = {"txt", "md", "markdown"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def chunk_text(text: str, max_length: int = 600) -> Iterable[str]:
    words = text.split()
    chunk = []
    count = 0
    for word in words:
        chunk.append(word)
        count += len(word) + 1
        if count >= max_length:
            yield " ".join(chunk)
            chunk = []
            count = 0
    if chunk:
        yield " ".join(chunk)


def detect_mime_type(filename: str) -> str:
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"
