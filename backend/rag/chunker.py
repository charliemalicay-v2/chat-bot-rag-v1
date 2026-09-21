"""Split text into overlapping, roughly equal-sized chunks (measured in words).

Paragraph-aware: whole paragraphs are packed together while they fit. A
paragraph longer than `size` is cut into overlapping word windows, each
emitted as its own chunk. When a packed chunk is closed, the next one starts
with its last `overlap` words, so a sentence cut at a boundary still appears
intact in one of the two chunks. Because of that carried-over tail a packed
chunk can reach `size + overlap` words.
"""

from __future__ import annotations

import re

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def chunk_text(text: str, size: int = 200, overlap: int = 40) -> list[str]:
    if size < 1:
        raise ValueError("size must be >= 1")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and < size")

    chunks: list[str] = []
    current: list[str] = []  # paragraphs of the chunk being built (may start with an overlap tail)
    current_len = 0
    fresh = False  # True once `current` holds content not yet emitted (not just a tail)

    def close_current():
        """Emit the chunk being built and seed the next one with its overlap tail."""
        nonlocal current, current_len, fresh
        emitted = "\n\n".join(current)
        chunks.append(emitted)
        tail = emitted.split()[-overlap:] if overlap else []
        current = [" ".join(tail)] if tail else []
        current_len = len(tail)
        fresh = False

    for para in (p.strip() for p in _PARAGRAPH_SPLIT.split(text)):
        if not para:
            continue
        words = para.split()

        if len(words) > size:
            # Oversized paragraph: emit overlapping windows directly.
            if fresh:
                close_current()
            current, current_len, fresh = [], 0, False
            step = size - overlap
            for start in range(0, len(words), step):
                chunks.append(" ".join(words[start:start + size]))
                if start + size >= len(words):
                    break
            continue

        if fresh and current_len + len(words) > size:
            close_current()
        current.append(para)
        current_len += len(words)
        fresh = True

    if fresh:
        chunks.append("\n\n".join(current))
    return chunks


def extract_title(text: str, fallback: str) -> str:
    """First markdown heading, else the fallback (usually the file name)."""
    for line in text.splitlines():
        m = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if m:
            return m.group(1).strip()
    return fallback
