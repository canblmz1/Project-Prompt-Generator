"""Tests for exporters.py — output file generation."""

import json
import pytest
import tempfile
from pathlib import Path

from project_prompter.exporters import export_all
from project_prompter.models import (
    ProjectAnalysis,
    RedactionFinding,
    ScanMetadata,
    ScanOptions,
    ScannedFile,
    TechStack,
)
from project_prompter.prompt_builder import build_prompts


def make_analysis_and_options(tmp_path: Path):
    """Create test analysis and options."""
    meta = ScanMetadata(
        scan_id="export-test-001",
        scanned_at="2024-01-01T00:00:00+00:00",
        project_path=str(tmp_path),
        total_files_found=20,
        files_scanned=15,
        files_skipped=5,
        files_redacted=1,
        ollama_used=False,
        ollama_model="llama3:latest",
        ollama_available=False,
        ollama_error="Ollama not available",
        target_model="all",
        duration_seconds=2.5,
    )

    stack = TechStack(
        languages=["Python"],
        frameworks=["FastAPI"],
        databases=["PostgreSQL"],
        tools=["Docker"],
        package_managers=["pip"],
        testing_tools=["Pytest"],
    )

    analysis = ProjectAnalysis(
        project_path=str(tmp_path),
        file_tree="my-project/\n├── main.py\n└── requirements.txt",
        tech_stack=stack,
        important_files=[
            ScannedFile(
                path=tmp_path / "main.py",
                relative_path="main.py",
                extension=".py",
                size=512,
                priority_score=75,
                content_preview="from fastapi import FastAPI\napp = FastAPI()",
            )
        ],
        file_summaries={"main.py": "FastAPI application entry point."},
        module_summaries={"root": "Root module with FastAPI app."},
        risk_notes=["No .env.example found"],
        assumptions=["Static analysis only"],
        redaction_findings=[
            RedactionFinding(file_path="config.py", finding_type="PASSWORD", count=1)
        ],
        scan_metadata=meta,
        project_summary="A FastAPI Python project.",
    )

    output_dir = tmp_path / "output"
    options = ScanOptions(
        project_path=tmp_path,
        output_path=output_dir,
        model="llama3:latest",
        ollama_url="http://localhost:11434",
        max_files=120,
        max_chars_per_file=8000,
        use_ollama=False,
        target_model="all",
    )

    return analysis, options


class TestExportAll:
    def test_creates_output_directory(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        assert options.output_path.exists()

    def test_creates_project_summary_md(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        assert (options.output_path / "project_summary.md").exists()

    def test_creates_file_tree_md(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        assert (options.output_path / "file_tree.md").exists()

    def test_creates_tech_stack_md(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        assert (options.output_path / "tech_stack.md").exists()

    def test_creates_risk_notes_md(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        assert (options.output_path / "risk_notes.md").exists()

    def test_creates_redaction_report_md(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        assert (options.output_path / "redaction_report.md").exists()

    def test_creates_scan_report_json(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        assert (options.output_path / "scan_report.json").exists()

    def test_creates_prompts_directory(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        assert (options.output_path / "prompts").is_dir()

    def test_creates_all_prompt_files(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        prompts_dir = options.output_path / "prompts"
        for model in ["chatgpt", "claude", "gemini", "minimax", "generic"]:
            assert (prompts_dir / f"{model}_prompt.md").exists(), f"Missing {model}_prompt.md"

    def test_creates_single_prompt_file(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        options.target_model = "chatgpt"
        prompts = build_prompts(analysis, "chatgpt")
        export_all(analysis, prompts, options)
        assert (options.output_path / "prompts" / "chatgpt_prompt.md").exists()
        # Other prompts should NOT exist
        assert not (options.output_path / "prompts" / "claude_prompt.md").exists()

    def test_scan_report_is_valid_json(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        report_path = options.output_path / "scan_report.json"
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert "scan_id" in data
        assert "tech_stack" in data
        assert "statistics" in data
        assert "redaction" in data

    def test_scan_report_contains_ollama_info(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        data = json.loads((options.output_path / "scan_report.json").read_text())
        assert "ollama" in data
        assert data["ollama"]["used"] is False
        assert data["ollama"]["error"] == "Ollama not available"

    def test_scan_report_contains_security_note(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        data = json.loads((options.output_path / "scan_report.json").read_text())
        assert "security_note" in data
        assert "cloud AI" in data["security_note"]

    def test_project_summary_contains_tech_stack(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        content = (options.output_path / "project_summary.md").read_text()
        assert "Python" in content
        assert "FastAPI" in content

    def test_redaction_report_contains_findings(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        content = (options.output_path / "redaction_report.md").read_text()
        assert "PASSWORD" in content
        assert "config.py" in content

    def test_returns_list_of_paths(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        result = export_all(analysis, prompts, options)
        assert isinstance(result, list)
        assert len(result) > 0
        for path in result:
            assert isinstance(path, Path)
            assert path.exists()

    def test_tech_stack_md_contains_table(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        content = (options.output_path / "tech_stack.md").read_text()
        assert "|" in content  # markdown table
        assert "Python" in content

    def test_file_tree_md_contains_tree(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        content = (options.output_path / "file_tree.md").read_text()
        assert "main.py" in content


class TestNoOllamaFallback:
    """Tests for the no-Ollama fallback mode."""

    def test_scan_report_marks_ollama_skipped_when_disabled(self, tmp_path):
        analysis, options = make_analysis_and_options(tmp_path)
        options.use_ollama = False
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        data = json.loads((options.output_path / "scan_report.json").read_text())
        assert data["ollama"]["used"] is False

    def test_prompts_generated_without_ollama(self, tmp_path):
        """Prompts should still be generated even without Ollama."""
        analysis, options = make_analysis_and_options(tmp_path)
        options.use_ollama = False
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        for model in ["chatgpt", "claude", "gemini", "minimax", "generic"]:
            prompt_file = options.output_path / "prompts" / f"{model}_prompt.md"
            assert prompt_file.exists()
            content = prompt_file.read_text()
            assert len(content) > 100

    def test_project_summary_mentions_static_analysis(self, tmp_path):
        """When Ollama is not used, summary should mention static analysis."""
        analysis, options = make_analysis_and_options(tmp_path)
        # The analysis already has ollama_used=False
        prompts = build_prompts(analysis, "all")
        export_all(analysis, prompts, options)
        content = (options.output_path / "project_summary.md").read_text()
        # Should mention Ollama was not used or static analysis
        assert "Ollama" in content or "static" in content.lower()
