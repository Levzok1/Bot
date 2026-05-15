import os
from typing import List


def get_int_env(name: str, default: int = 0) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        return int(raw_value)
    except ValueError:
        return default


def chunk_text(text: str, limit: int = 1900) -> List[str]:
    if len(text) <= limit:
        return [text]

    chunks = []
    current = []
    current_length = 0

    for line in text.splitlines():
        line_length = len(line) + 1
        if current and current_length + line_length > limit:
            chunks.append("\n".join(current))
            current = []
            current_length = 0

        if line_length > limit:
            for start in range(0, len(line), limit):
                chunks.append(line[start:start + limit])
            continue

        current.append(line)
        current_length += line_length

    if current:
        chunks.append("\n".join(current))

    return chunks or [""]
