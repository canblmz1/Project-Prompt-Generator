from __future__ import annotations

import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

ANALYZE_RATE_LIMIT_PER_MIN_ENV = "PROJECT_PROMPTER_ANALYZE_RATE_LIMIT_PER_MIN"
_analyze_window: deque[float] = deque()


def validate_extra_ignore_dirs(extra_ignore_dirs: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in extra_ignore_dirs:
        value = item.strip().strip('/\\')
        if not value:
            continue
        if '..' in value or Path(value).is_absolute():
            raise ValueError("extra_ignore_dirs contains invalid directory entries")
        cleaned.append(value)
    return cleaned


def enforce_analyze_rate_limit() -> int:
    raw_limit = os.environ.get(ANALYZE_RATE_LIMIT_PER_MIN_ENV, "60")
    try:
        limit = int(raw_limit)
    except (ValueError, TypeError):
        limit = 60  # fall back to safe default when env var is malformed
    if limit <= 0:
        return 0

    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - 60
    while _analyze_window and _analyze_window[0] < cutoff:
        _analyze_window.popleft()
    if len(_analyze_window) >= limit:
        oldest = _analyze_window[0]
        retry_after = max(1, int(61 - (now_ts - oldest)))
        raise ValueError(f"rate limit exceeded: too many analyze requests|{retry_after}")
    _analyze_window.append(now_ts)
    return 0
