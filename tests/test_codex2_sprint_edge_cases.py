"""Codex #2 focused edge-case tests for the sprint feature batch."""

from pathlib import Path

import pytest

from project_prompter.analyzer import analyze_project
from project_prompter.domain_classifier import detect_domain
from project_prompter.models import ScanOptions
from project_prompter.scanner import _safe_read
from project_prompter.structural_analyzer import build_structural_summary


def test_dry_run_does_not_call_summarization_or_export(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    output_path = tmp_path / "out"

    def fail_summarization(*args, **kwargs):
        raise AssertionError("dry-run should not call run_summarization")

    def fail_export(*args, **kwargs):
        raise AssertionError("dry-run should not call export_all")

    monkeypatch.setattr("project_prompter.analyzer.run_summarization", fail_summarization)
    monkeypatch.setattr("project_prompter.analyzer.export_all", fail_export)

    analysis = analyze_project(
        ScanOptions(
            project_path=project,
            output_path=output_path,
            max_files=10,
            max_chars_per_file=1000,
            use_ollama=True,
            dry_run=True,
        )
    )

    assert analysis.scan_metadata is not None
    assert analysis.scan_metadata.ollama_used is False
    assert output_path.exists() is False


def test_safe_read_truncated_preview_respects_max_chars_budget(tmp_path):
    file_path = tmp_path / "large.txt"
    file_path.write_text("A" * 80 + "B" * 80 + "C" * 80, encoding="utf-8")

    content, error = _safe_read(file_path, max_chars=100)

    assert error is None
    assert len(content) <= 100


def test_go_structural_summary_extracts_receiver_methods():
    content = """
package service

type Server struct {}

func (s *Server) Start(addr string) error {
    return nil
}
"""

    summary = build_structural_summary(Path("server.go"), "server.go", content, 512, 75)

    assert "Start(" in summary


@pytest.mark.parametrize("dependency", ["pandas", "numpy", "jupyter"])
def test_data_science_domain_detects_single_core_indicator(dependency):
    result = detect_domain(
        project_path_str="analysis_project",
        file_paths=["src/analysis.py"],
        structural_summaries={"src/analysis.py": f"Imports:\n  - {dependency}"},
        dependencies=[dependency],
        markdown_contents={},
    )

    assert result.domain == "data_science"
    assert result.confidence in ("medium", "high")


def test_data_science_weak_indicators_alone_do_not_trigger_exception():
    result = detect_domain(
        project_path_str="reporting_project",
        file_paths=["data/dataset.csv", "src/dataframe_export.py"],
        structural_summaries={
            "src/dataframe_export.py": "Functions:\n  - predict_accuracy_report()"
        },
        dependencies=["matplotlib", "seaborn"],
        markdown_contents={
            "README.md": "csv dataset dataframe preprocessing inference predict accuracy loss epoch"
        },
    )

    assert result.domain == "generic"
    assert result.confidence == "low"


def test_single_indicator_exception_does_not_apply_to_other_domains():
    result = detect_domain(
        project_path_str="integration_project",
        file_paths=["src/integration.py"],
        structural_summaries={"src/integration.py": "Imports:\n  - binance"},
        dependencies=["binance"],
        markdown_contents={},
    )

    assert result.domain == "generic"
    assert result.confidence == "low"


def test_data_science_structural_only_hit_below_threshold_stays_generic():
    result = detect_domain(
        project_path_str="analysis_project",
        file_paths=["src/analysis.py"],
        structural_summaries={"src/analysis.py": "Imports:\n  - pandas"},
        dependencies=[],
        markdown_contents={},
    )

    assert result.domain == "generic"
    assert result.confidence == "low"
