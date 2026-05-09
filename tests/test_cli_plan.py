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


def test_start_ui_rejects_out_of_range_port():
    """_start_ui must refuse ports outside 1-65535 without starting the server."""
    import types

    args = types.SimpleNamespace(port=0, host="127.0.0.1")
    assert cli._start_ui(args) == 1

    args.port = 65536
    assert cli._start_ui(args) == 1

    args.port = -1
    assert cli._start_ui(args) == 1


def test_validate_flags_called_before_plan_with_conflicting_ollama_flags(tmp_path):
    """--plan should honour --use-ollama/--no-ollama conflict detection."""
    parser = cli.create_parser()
    args = parser.parse_args(
        [str(tmp_path), "--plan", "--use-ollama", "--no-ollama", "--output", str(tmp_path / "out")]
    )
    # The main() entry-point calls _validate_flags before _run_plan;
    # validate directly here to confirm the flag check catches it.
    error = cli._validate_flags(args)
    assert error is not None
    assert "Conflicting" in error
