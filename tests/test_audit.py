from pathlib import Path

from project_prompter.audit import build_upgrade_plan, run_repo_audit


def test_run_repo_audit_reports_missing_items(tmp_path: Path):
    findings = run_repo_audit(tmp_path)
    titles = {f.title for f in findings}
    assert "Automated test suite missing" in titles
    assert "CI workflow missing" in titles
    assert "No security policy file" in titles


def test_run_repo_audit_respects_present_files(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "SECURITY.md").write_text("policy", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.coverage.run]\nsource=['x']\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest==9.0.0\n", encoding="utf-8")

    findings = run_repo_audit(tmp_path)
    assert findings == []


def test_build_upgrade_plan_contains_findings(tmp_path: Path):
    findings = run_repo_audit(tmp_path)
    content = build_upgrade_plan(tmp_path, findings)

    assert "Project Upgrade Plan" in content
    assert "Phase 1" in content
    assert "Current Findings" in content
    assert "Automated test suite missing" in content
