from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_process_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = _WHITESPACE.sub("", value.strip().lower())
    return normalized
