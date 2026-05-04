from pathlib import Path

from project_prompter import cli


def test_plan_command_creates_upgrade_plan_file(tmp_path: Path):
    repo = tmp_path / "repo"
    out = tmp_path / "out"
    repo.mkdir()

    parser = cli.create_parser()
    args = parser.parse_args([str(repo), "--plan", "--output", str(out)])
    result = cli._run_plan(args)

    assert result == 0
    plan_file = out / "upgrade_plan.md"
    assert plan_file.exists()
    text = plan_file.read_text(encoding="utf-8")
    assert "Project Upgrade Plan" in text
