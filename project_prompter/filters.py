"""File and folder filtering logic — ignore rules, secret detection, and redaction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Ignored folders
# ---------------------------------------------------------------------------

IGNORED_FOLDERS: set[str] = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "out",
    "coverage",
    "htmlcov",
    ".cache",
    "vendor",
    "target",
    "bin",
    "obj",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
    ".DS_Store",
    "logs",
    "tmp",
    "temp",
    "output",
    "outputs",
    "runtime",
    "cache",
    "uploads",
    "media",
    "audios",
    "audio",
    "temp_audios",
    "manual_tests",
    "test_deploy",
}

# ---------------------------------------------------------------------------
# Ignored file patterns (exact names and glob-style suffixes)
# ---------------------------------------------------------------------------

IGNORED_FILE_NAMES: set[str] = {
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "Thumbs.db",
    ".DS_Store",
}

IGNORED_FILE_SUFFIXES: tuple[str, ...] = (
    ".pem",
    ".key",
    ".crt",
    ".p12",
    ".pfx",
    ".sqlite-journal",
    ".log",
    ".tmp",
    ".cache",
)

# Env-like patterns (e.g. .env.local, .env.production)
IGNORED_ENV_PATTERN = re.compile(r"^\.env(\..+)?$")

# Lock files — skip content but allow for package manager detection
LOCK_FILES: set[str] = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "composer.lock",
}

# Allowed extensions for content reading
ALLOWED_EXTENSIONS: set[str] = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".json",
    ".md",
    ".py",
    ".rb",
    ".rs",
    ".php",
    ".java",
    ".cs",
    ".xml",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".prisma",
    ".sql",
    ".html",
    ".css",
    ".scss",
    "",  # for files like Dockerfile with no extension
}

# Binary / asset extensions to always skip
BINARY_EXTENSIONS: set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".bmp",
    ".tiff",
    ".mp4",
    ".mp3",
    ".avi",
    ".mov",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".wasm",
    ".pdf",
    ".docx",
    ".xlsx",
    ".ttf",
    ".woff",
    ".woff2",
    ".eot",
    ".otf",
    ".db",
    ".sqlite",
    ".pyc",
    ".class",
    ".o",
    ".a",
    ".m4a",
    ".aac",
    ".ogg",
    ".flac",
}

# ---------------------------------------------------------------------------
# Secret detection patterns
# ---------------------------------------------------------------------------

SECRET_PATTERNS: List[Tuple[str, str, str]] = [
    # (pattern_name, regex, placeholder)
    (
        "API_KEY",
        r'(?i)(api[_\-]?key|apikey)\s*[=:]\s*["\']?([A-Za-z0-9\-_]{20,})["\']?',
        "[REDACTED_SECRET]",
    ),
    (
        "TOKEN",
        r'(?i)(access[_\-]?token|auth[_\-]?token|bearer[_\-]?token|refresh[_\-]?token|jwt[_\-]?secret)\s*[=:]\s*["\']?([A-Za-z0-9\-_.]{20,})["\']?',
        "[REDACTED_TOKEN]",
    ),
    (
        "PASSWORD",
        r'(?i)(password|passwd|db[_\-]?pass|database[_\-]?password)\s*[=:]\s*["\']?([^\s"\']{6,})["\']?',
        "[REDACTED_PASSWORD]",
    ),
    (
        "PRIVATE_KEY",
        r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        "SECRET",
        r'(?i)(secret[_\-]?key|app[_\-]?secret|client[_\-]?secret|oauth[_\-]?secret)\s*[=:]\s*["\']?([A-Za-z0-9\-_]{16,})["\']?',
        "[REDACTED_SECRET]",
    ),
    (
        "CONNECTION_STRING",
        r'(?i)(connection[_\-]?string|database[_\-]?url|db[_\-]?url)\s*[=:]\s*["\']?([a-zA-Z][a-zA-Z0-9+\-.]{1,20}://[^\s"\'@]{1,100}:[^\s"\'@]{1,100}@[^\s"\']{1,200})["\']?',
        "[REDACTED_SECRET]",
    ),
    (
        "AWS_KEY",
        r"(?i)(aws[_\-]?access[_\-]?key[_\-]?id|aws[_\-]?secret[_\-]?access[_\-]?key)\s*[=:]\s*[\"']?([A-Za-z0-9/+=]{16,})[\"']?",
        "[REDACTED_SECRET]",
    ),
    (
        "GENERIC_SECRET",
        r'(?i)(secret|token|key|credential)\s*=\s*["\']([A-Za-z0-9\-_+/=]{32,})["\']',
        "[REDACTED_SECRET]",
    ),
]


def should_ignore_folder(folder_name: str, extra: frozenset[str] = frozenset()) -> bool:
    """Return True if a folder should be skipped entirely."""
    return folder_name in IGNORED_FOLDERS or folder_name in extra


def should_ignore_file(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Return (should_ignore, reason) for a given file path.
    Reason is None when the file is allowed.
    """
    name = file_path.name
    suffix = file_path.suffix.lower()

    # .env and .env.* patterns (check before exact names so .env gets "env_file" reason)
    if IGNORED_ENV_PATTERN.match(name):
        return True, "env_file"

    # Exact name matches (id_rsa, id_dsa, etc.)
    if name in IGNORED_FILE_NAMES:
        return True, "secret_file"

    # Suffix-based ignores
    if suffix in IGNORED_FILE_SUFFIXES:
        return True, "secret_extension"

    # Binary / asset extensions
    if suffix in BINARY_EXTENSIONS:
        return True, "binary_or_asset"

    return False, None


def is_lock_file(file_path: Path) -> bool:
    """Return True if the file is a lock file (skip content, allow detection)."""
    return file_path.name in LOCK_FILES


def is_allowed_extension(file_path: Path) -> bool:
    """Return True if the file extension is in the allowed list."""
    suffix = file_path.suffix.lower()
    name = file_path.name
    # Dockerfile has no extension
    if name == "Dockerfile":
        return True
    return suffix in ALLOWED_EXTENSIONS


def is_minified_file(file_path: Path) -> bool:
    """Heuristic: treat .min.js / .min.css as minified."""
    name = file_path.name.lower()
    return ".min." in name


def redact_secrets(content: str) -> Tuple[str, List[Tuple[str, int]]]:
    """
    Scan content for secret patterns and replace them with placeholders.

    Returns:
        (redacted_content, findings) where findings is a list of
        (finding_type, count) tuples.
    """
    findings: dict[str, int] = {}
    redacted = content

    for pattern_name, pattern, placeholder in SECRET_PATTERNS:
        compiled = re.compile(pattern, re.MULTILINE)
        matches = compiled.findall(redacted)
        if matches:
            findings[pattern_name] = findings.get(pattern_name, 0) + len(matches)
            # Replace the full match
            redacted = compiled.sub(
                lambda m, ph=placeholder: _build_replacement(m, ph),
                redacted,
            )

    return redacted, list(findings.items())


def _build_replacement(match: re.Match, placeholder: str) -> str:
    """Build a replacement string that keeps the key name but redacts the value."""
    full = match.group(0)
    # Try to keep the key part and replace only the value
    # For patterns with 2 groups: group(1) = key, group(2) = value
    try:
        if match.lastindex and match.lastindex >= 2:
            return full.replace(match.group(2), placeholder)
    except IndexError:
        pass
    return placeholder


def has_suspicious_content(content: str) -> bool:
    """Quick check: does the content contain any secret-like patterns?"""
    for _, pattern, _ in SECRET_PATTERNS:
        if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# Secret file category — for file tree masking
# ---------------------------------------------------------------------------

def secret_file_category(file_path: Path) -> str | None:
    """
    Return a human-readable secret category for file tree masking.
    Returns None if the file is not a secret file.

    Categories:
    - "env file"
    - "private key/certificate"
    - "credential file"
    """
    name = file_path.name
    suffix = file_path.suffix.lower()

    # .env and .env.* patterns
    if IGNORED_ENV_PATTERN.match(name):
        return "env file"

    # Private key / certificate files
    if suffix in (".pem", ".key", ".crt", ".p12", ".pfx"):
        return "private key/certificate"

    # SSH key files
    if name in ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"):
        return "credential file"

    return None

