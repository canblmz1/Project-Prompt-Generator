"""Project scanner — recursively walks a project directory safely."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

from .filters import (
    is_allowed_extension,
    is_lock_file,
    is_minified_file,
    redact_secrets,
    secret_file_category,
    should_ignore_file,
    should_ignore_folder,
)
from .models import RedactionFinding, ScannedFile


def build_file_tree(
    project_root: Path,
    max_depth: int = 8,
    extra_ignore_dirs: Optional[List[str]] = None,
) -> str:
    """
    Build a text-based file tree for the project, respecting ignore rules.
    Returns a markdown code block string.
    """
    lines: List[str] = [f"{project_root.name}/"]
    extra = _normalize_extra_ignore_dirs(extra_ignore_dirs)
    _walk_tree(
        project_root,
        project_root,
        lines,
        prefix="",
        depth=0,
        max_depth=max_depth,
        extra_ignore_dirs=extra,
    )
    return "\n".join(lines)


def _walk_tree(
    root: Path,
    current: Path,
    lines: List[str],
    prefix: str,
    depth: int,
    max_depth: int,
    extra_ignore_dirs: frozenset[str],
) -> None:
    if depth > max_depth:
        return

    try:
        entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return

    dirs = [
        e
        for e in entries
        if e.is_dir() and not should_ignore_folder(e.name, extra_ignore_dirs)
    ]
    files = [e for e in entries if e.is_file()]

    all_entries = dirs + files
    for i, entry in enumerate(all_entries):
        is_last = i == len(all_entries) - 1
        connector = "└── " if is_last else "├── "

        # Mask secret files in the tree with category-based placeholder
        if entry.is_file():
            category = secret_file_category(entry)
            if category:
                lines.append(f"{prefix}{connector}[SECRET_FILE_SKIPPED: {category}]")
                continue

        lines.append(f"{prefix}{connector}{entry.name}")

        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _walk_tree(
                root,
                entry,
                lines,
                prefix + extension,
                depth + 1,
                max_depth,
                extra_ignore_dirs,
            )


def scan_project(
    project_root: Path,
    max_files: int = 120,
    max_chars_per_file: int = 8000,
    extra_ignore_dirs: Optional[List[str]] = None,
) -> Tuple[List[ScannedFile], List[RedactionFinding]]:
    """
    Recursively scan a project directory.

    Note: ``max_files`` is intentionally *not* enforced here.  The scanner
    walks the entire tree so that ``detect_tech_stack`` and
    ``domain_classifier`` can see all files.  File selection is capped later
    by ``prioritize_files`` which ranks files by importance before truncating.

    Returns:
        (scanned_files, redaction_findings)
        scanned_files includes all discovered files with content_preview set.
        redaction_findings lists all secrets found and redacted.
    """
    scanned: List[ScannedFile] = []
    redaction_findings: List[RedactionFinding] = []
    extra = _normalize_extra_ignore_dirs(extra_ignore_dirs)

    for dirpath, dirnames, filenames in os.walk(project_root):
        current_dir = Path(dirpath)

        # Prune ignored directories in-place so os.walk skips them
        new_dirnames = []
        for d in dirnames:
            if should_ignore_folder(d, extra):
                # Add the folder itself as a skipped entry so Domain Classifier can see its name
                rel_d = str((current_dir / d).relative_to(project_root)).replace("\\", "/")
                scanned.append(
                    ScannedFile(
                        path=current_dir / d,
                        relative_path=rel_d,
                        extension="",
                        size=0,
                        skipped_reason="ignored_folder",
                    )
                )
            else:
                new_dirnames.append(d)
        dirnames[:] = new_dirnames

        for filename in filenames:
            file_path = current_dir / filename
            relative_path = str(file_path.relative_to(project_root)).replace("\\", "/")

            # Check ignore rules
            ignored, reason = should_ignore_file(file_path)
            if ignored:
                scanned.append(
                    ScannedFile(
                        path=file_path,
                        relative_path=relative_path,
                        extension=file_path.suffix.lower(),
                        size=_safe_size(file_path),
                        skipped_reason=reason,
                    )
                )
                continue

            # Lock files: record but skip content
            if is_lock_file(file_path):
                scanned.append(
                    ScannedFile(
                        path=file_path,
                        relative_path=relative_path,
                        extension=file_path.suffix.lower(),
                        size=_safe_size(file_path),
                        skipped_reason="lock_file",
                    )
                )
                continue

            # Minified files
            if is_minified_file(file_path):
                scanned.append(
                    ScannedFile(
                        path=file_path,
                        relative_path=relative_path,
                        extension=file_path.suffix.lower(),
                        size=_safe_size(file_path),
                        skipped_reason="minified",
                    )
                )
                continue

            # Extension check
            if not is_allowed_extension(file_path):
                scanned.append(
                    ScannedFile(
                        path=file_path,
                        relative_path=relative_path,
                        extension=file_path.suffix.lower(),
                        size=_safe_size(file_path),
                        skipped_reason="unsupported_extension",
                    )
                )
                continue

            # Read content
            content, read_error = _safe_read(file_path, max_chars_per_file)
            if read_error:
                scanned.append(
                    ScannedFile(
                        path=file_path,
                        relative_path=relative_path,
                        extension=file_path.suffix.lower(),
                        size=_safe_size(file_path),
                        skipped_reason=f"read_error: {read_error}",
                    )
                )
                continue

            # Redact secrets
            redacted_content, findings = redact_secrets(content)
            was_redacted = len(findings) > 0

            for finding_type, count in findings:
                redaction_findings.append(
                    RedactionFinding(
                        file_path=relative_path,
                        finding_type=finding_type,
                        count=count,
                    )
                )

            scanned.append(
                ScannedFile(
                    path=file_path,
                    relative_path=relative_path,
                    extension=file_path.suffix.lower(),
                    size=_safe_size(file_path),
                    redacted=was_redacted,
                    content_preview=redacted_content,
                )
            )

    return scanned, redaction_findings


def _normalize_extra_ignore_dirs(extra_ignore_dirs: Optional[List[str]]) -> frozenset[str]:
    """Normalize user-provided folder names for exact-name matching."""
    if not extra_ignore_dirs:
        return frozenset()
    return frozenset(
        name.strip().strip("/\\")
        for name in extra_ignore_dirs
        if name.strip().strip("/\\")
    )


def _safe_read(file_path: Path, max_chars: int) -> Tuple[str, Optional[str]]:
    """Read a file safely, truncating to max_chars. Returns (content, error)."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            if max_chars <= 0:
                omitted_all = len(content)
                content = f"... [MIDDLE SECTION OMITTED \u2014 {omitted_all} chars] ..."
            else:
                marker_template = f"\n\n... [MIDDLE SECTION OMITTED \u2014 {len(content)} chars] ...\n\n"
                available = max_chars - len(marker_template)
                if available <= 0:
                    head = ""
                    tail = ""
                    omitted = len(content)
                else:
                    head_size = int(available * 0.70)
                    tail_size = available - head_size
                    head = content[:head_size]
                    tail = content[-tail_size:] if tail_size else ""
                    omitted = len(content) - len(head) - len(tail)
                content = (
                    head
                    + f"\n\n... [MIDDLE SECTION OMITTED \u2014 {omitted} chars] ...\n\n"
                    + tail
                )
        return content, None
    except PermissionError:
        return "", "permission_denied"
    except Exception as e:
        return "", str(e)


def _safe_size(file_path: Path) -> int:
    """Return file size in bytes, or 0 on error."""
    try:
        return file_path.stat().st_size
    except Exception:
        return 0
