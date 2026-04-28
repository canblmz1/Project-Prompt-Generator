"""File prioritization — score files by importance for AI summarization."""

from __future__ import annotations

import re
from typing import List

from .models import ScannedFile

# ---------------------------------------------------------------------------
# Priority scoring rules
# Each rule is (score, condition_fn)
# Higher score = more important
# ---------------------------------------------------------------------------

# Name-based high-priority patterns
HIGH_PRIORITY_NAMES: set[str] = {
    "readme.md",
    "readme.txt",
    "readme",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "pipfile",
    "composer.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "vite.config.mjs",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "electron.vite.config.ts",
    "jest.config.js",
    "jest.config.ts",
    "vitest.config.ts",
    "vitest.config.js",
    "playwright.config.ts",
    "playwright.config.js",
    "cypress.config.ts",
    "cypress.config.js",
    "prisma/schema.prisma",
    "schema.prisma",
    "manage.py",
    "artisan",
    "appsettings.json",
    ".env.example",
    "conftest.py",
    "pytest.ini",
    "setup.py",
    "setup.cfg",
}

# Path segment patterns that indicate important files
HIGH_PRIORITY_PATH_PATTERNS: List[tuple[int, re.Pattern]] = [
    (90, re.compile(r"(^|/)readme(\.(md|txt))?$", re.IGNORECASE)),
    (85, re.compile(r"(^|/)package\.json$", re.IGNORECASE)),
    (85, re.compile(r"(^|/)pyproject\.toml$", re.IGNORECASE)),
    (85, re.compile(r"(^|/)requirements\.txt$", re.IGNORECASE)),
    (85, re.compile(r"(^|/)dockerfile$", re.IGNORECASE)),
    (85, re.compile(r"(^|/)docker-compose\.(yml|yaml)$", re.IGNORECASE)),
    (80, re.compile(r"(^|/)schema\.prisma$", re.IGNORECASE)),
    (80, re.compile(r"(^|/)tsconfig\.json$", re.IGNORECASE)),
    (75, re.compile(r"(^|/)(main|index)\.(ts|tsx|js|jsx|py|java|cs)$", re.IGNORECASE)),
    (75, re.compile(r"(^|/)app\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (75, re.compile(r"(^|/)server\.(ts|js|py)$", re.IGNORECASE)),
    (70, re.compile(r"(^|/)(routes?|router)\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (70, re.compile(r"(^|/)api\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (70, re.compile(r"(^|/)auth\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (70, re.compile(r"(^|/)(auth|authentication|authorization)\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (65, re.compile(r"(^|/)middleware\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (65, re.compile(r"(^|/)database\.(ts|js|py)$", re.IGNORECASE)),
    (65, re.compile(r"(^|/)db\.(ts|js|py)$", re.IGNORECASE)),
    (65, re.compile(r"(^|/)models?\.(ts|tsx|js|jsx|py|java|cs)$", re.IGNORECASE)),
    (65, re.compile(r"(^|/)schema\.(ts|js|py|sql)$", re.IGNORECASE)),
    (60, re.compile(r"(^|/).*service[s]?\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (60, re.compile(r"(^|/)repository\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (60, re.compile(r"(^|/)store\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (60, re.compile(r"(^|/)state\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (55, re.compile(r"(^|/)controller[s]?\.(ts|tsx|js|jsx|py|java|cs)$", re.IGNORECASE)),
    (55, re.compile(r"(^|/)handler[s]?\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (55, re.compile(r"(^|/)preload\.(ts|js)$", re.IGNORECASE)),
    (50, re.compile(r"(^|/)migration[s]?/", re.IGNORECASE)),
    (50, re.compile(r"(^|/)security\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (45, re.compile(r"(^|/)config\.(ts|tsx|js|jsx|py|json|yml|yaml)$", re.IGNORECASE)),
    (40, re.compile(r"(^|/)utils?\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (40, re.compile(r"(^|/)helpers?\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (35, re.compile(r"\.(test|spec)\.(ts|tsx|js|jsx|py)$", re.IGNORECASE)),
    (30, re.compile(r"(^|/)tests?/", re.IGNORECASE)),
]

# Patterns that indicate generated / low-priority files
LOW_PRIORITY_PATTERNS: List[re.Pattern] = [
    re.compile(r"\.min\.(js|css)$", re.IGNORECASE),
    re.compile(r"\.generated\.", re.IGNORECASE),
    re.compile(r"(^|/)generated/", re.IGNORECASE),
    re.compile(r"(^|/)\.next/", re.IGNORECASE),
    re.compile(r"(^|/)dist/", re.IGNORECASE),
    re.compile(r"(^|/)build/", re.IGNORECASE),
]


def compute_priority_score(relative_path: str) -> int:
    """
    Compute a priority score (0-100) for a file based on its path.
    Higher = more important.
    """
    path_lower = relative_path.lower().replace("\\", "/")

    # Check low-priority patterns first
    for pattern in LOW_PRIORITY_PATTERNS:
        if pattern.search(path_lower):
            return 5

    # Check high-priority path patterns
    best_score = 10  # default
    for score, pattern in HIGH_PRIORITY_PATH_PATTERNS:
        if pattern.search(path_lower):
            best_score = max(best_score, score)

    # Exact name match bonus
    file_name = path_lower.split("/")[-1]
    if file_name in HIGH_PRIORITY_NAMES:
        best_score = max(best_score, 80)

    return best_score


def prioritize_files(files: List[ScannedFile], max_files: int) -> List[ScannedFile]:
    """
    Sort files by priority score descending and return up to max_files.
    Assigns priority_score to each file in-place.
    """
    for f in files:
        f.priority_score = compute_priority_score(f.relative_path)

    sorted_files = sorted(files, key=lambda f: f.priority_score, reverse=True)
    return sorted_files[:max_files]
