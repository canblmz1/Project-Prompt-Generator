"""Repository quality/security audit helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AuditFinding:
    category: str
    severity: str
    title: str
    detail: str
    recommendation: str


def run_repo_audit(project_path: Path) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    if not (project_path / "tests").exists():
        findings.append(
            AuditFinding(
                category="quality",
                severity="high",
                title="Automated test suite missing",
                detail="No top-level tests directory was found.",
                recommendation="Add pytest-based smoke/unit tests for CLI and web API critical paths.",
            )
        )

    if not (project_path / ".github" / "workflows").exists():
        findings.append(
            AuditFinding(
                category="quality",
                severity="medium",
                title="CI workflow missing",
                detail="No GitHub Actions workflow directory detected.",
                recommendation="Add CI for lint, tests, and packaging checks on pull requests.",
            )
        )

    if not (project_path / "SECURITY.md").exists():
        findings.append(
            AuditFinding(
                category="security",
                severity="high",
                title="No security policy file",
                detail="SECURITY.md file is missing.",
                recommendation="Publish a security policy with disclosure contact and supported versions.",
            )
        )

    if not (project_path / "pyproject.toml").exists():
        findings.append(
            AuditFinding(
                category="quality",
                severity="high",
                title="Missing pyproject.toml",
                detail="Project metadata and tooling configuration are missing.",
                recommendation="Adopt pyproject.toml and define lint/test/type/audit tool configs.",
            )
        )

    if not any((project_path / f).exists() for f in ("poetry.lock", "requirements.txt", "requirements.lock", "uv.lock")):
        findings.append(
            AuditFinding(
                category="security",
                severity="medium",
                title="Dependency lockfile/constraints missing",
                detail="No dependency lockfile or pinned requirements file detected.",
                recommendation="Add a lockfile or pinned requirements to improve supply-chain reproducibility.",
            )
        )

    has_cov_config = (project_path / ".coveragerc").exists()
    if (project_path / "pyproject.toml").exists():
        text = (project_path / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
        has_cov_config = has_cov_config or "[tool.coverage." in text
    if not has_cov_config:
        findings.append(
            AuditFinding(
                category="quality",
                severity="low",
                title="Coverage policy missing",
                detail="No coverage configuration found to enforce quality thresholds.",
                recommendation="Configure coverage and enforce a minimum threshold in CI.",
            )
        )

    return findings


def build_upgrade_plan(project_path: Path, findings: list[AuditFinding]) -> str:
    lines = [
        f"# Project Upgrade Plan ({project_path.name})",
        "",
        "## Phase 1 — Trust & Security",
        "1. Add API abuse tests for validation and path restrictions.",
        "2. Add regression tests for secret redaction and output safety.",
        "",
        "## Phase 2 — Engineering Quality",
        "1. Introduce CI (tests + static checks).",
        "2. Add baseline test coverage for CLI/web flows.",
        "",
        "## Phase 3 — Star-worthy Productization",
        "1. Ship polished demo assets and usage GIFs.",
        "2. Publish contribution guide + issue templates.",
        "",
        "## Current Findings",
    ]
    if not findings:
        lines.append("- No major structural gaps detected by baseline audit.")
    else:
        for item in findings:
            lines.append(
                f"- [{item.severity.upper()}] {item.title}: {item.detail} → {item.recommendation}"
            )
    lines.append("")
    return "\n".join(lines)
