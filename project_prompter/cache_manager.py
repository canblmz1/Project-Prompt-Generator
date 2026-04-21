"""File-level cache for structural and Ollama summaries."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

CACHE_DIR_NAME = ".project-prompter-cache"


def _cache_dir(project_root: Path) -> Path:
    return project_root / CACHE_DIR_NAME


def _file_hash(file_path: Path) -> str:
    """SHA256 of file content, combined with size+mtime for speed."""
    try:
        stat = file_path.stat()
        # Fast key: path + size + mtime (no full read needed for cache key)
        fast_key = f"{file_path}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.sha256(fast_key.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


def _cache_path(project_root: Path, file_path: Path, mode: str) -> Path:
    rel = str(file_path.relative_to(project_root)).replace("\\", "/").replace("/", "_")
    key = _file_hash(file_path)
    return _cache_dir(project_root) / f"{rel}__{mode}__{key}.json"


def load_cached(project_root: Path, file_path: Path, mode: str) -> Optional[Dict[str, Any]]:
    """Load cached summary for a file. Returns None if not cached or stale."""
    cp = _cache_path(project_root, file_path, mode)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
        return data
    except Exception:
        return None


def save_cached(
    project_root: Path,
    file_path: Path,
    mode: str,
    data: Dict[str, Any],
) -> None:
    """Save summary data to cache."""
    cache_dir = _cache_dir(project_root)
    cache_dir.mkdir(exist_ok=True)
    cp = _cache_path(project_root, file_path, mode)
    try:
        cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # cache write failure is non-fatal


def clear_cache(project_root: Path) -> int:
    """Delete all cache files. Returns count of deleted files."""
    cache_dir = _cache_dir(project_root)
    if not cache_dir.exists():
        return 0
    count = 0
    for f in cache_dir.glob("*.json"):
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    return count
