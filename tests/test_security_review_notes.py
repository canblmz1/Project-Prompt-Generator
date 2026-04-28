from pathlib import Path


def test_project_brief_records_ollama_url_security_task():
    project_root = Path(__file__).resolve().parents[1]
    brief = (project_root / "ai-context" / "PROJECT_BRIEF.md").read_text(encoding="utf-8")

    assert "Security Review Notes" in brief
    assert "constrain user-provided Ollama base URLs" in brief
    assert "project_prompter/web.py" in brief
    assert "project_prompter/ollama_client.py" in brief
    assert "/api/tags" in brief
    assert "/api/generate" in brief
    assert "loopback-only" in brief
    assert "explicit opt-in" in brief
