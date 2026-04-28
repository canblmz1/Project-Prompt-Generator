"""Codex #2 focused edge-case tests for the sprint feature batch."""

from pathlib import Path

import pytest

from project_prompter import web
from project_prompter.analyzer import analyze_project
from project_prompter.cache_manager import _cache_path, load_cached, save_cached
from project_prompter.domain_classifier import detect_domain
from project_prompter.models import ScanOptions
from project_prompter.scanner import _safe_read
from project_prompter.structural_analyzer import build_structural_summary

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - optional web dependency
    TestClient = None  # type: ignore


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


def test_cache_path_hash_keeps_separator_collision_candidates_distinct(tmp_path):
    first = tmp_path / "src" / "api_client.py"
    second = tmp_path / "src_api" / "client.py"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("FIRST = True\n", encoding="utf-8")
    second.write_text("SECOND = True\n", encoding="utf-8")

    first_cache_path = _cache_path(tmp_path, first, "fast")
    second_cache_path = _cache_path(tmp_path, second, "fast")

    assert first_cache_path.name != second_cache_path.name
    assert "src" not in first_cache_path.name
    assert "api_client.py" not in first_cache_path.name

    save_cached(tmp_path, first, "fast", {"structural_summary": "first"})
    save_cached(tmp_path, second, "fast", {"structural_summary": "second"})

    assert load_cached(tmp_path, first, "fast") == {"structural_summary": "first"}
    assert load_cached(tmp_path, second, "fast") == {"structural_summary": "second"}


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_cors_preflight_allows_127_origin_and_blocks_unlisted_methods():
    client = TestClient(web.create_app())

    allowed = client.options(
        "/api/analyze",
        headers={
            "Origin": "http://127.0.0.1:8787",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    blocked_method = client.options(
        "/api/analyze",
        headers={
            "Origin": "http://127.0.0.1:8787",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:8787"
    assert blocked_method.status_code == 400


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_analyze_endpoint_evicts_before_queueing_new_scan(tmp_path, monkeypatch):
    previous_scans = dict(web._scans)
    web._scans.clear()

    async def noop_analysis_task(*args, **kwargs):
        return None

    try:
        for i in range(web.MAX_SCANS):
            web._scans[f"old_{i:04d}"] = {"started_at": f"2026-01-01T00:00:{i:04d}Z"}

        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(web, "_run_analysis_task", noop_analysis_task)

        client = TestClient(web.create_app())
        response = client.post(
            "/api/analyze",
            json={
                "project_path": str(project),
                "output_path": "output",
                "mode": "fast",
                "ollama_url": "http://localhost:11434",
            },
        )

        assert response.status_code == 200
        scan_id = response.json()["scan_id"]
        assert scan_id in web._scans
        assert len(web._scans) == web.MAX_SCANS - web._SCAN_EVICTION_BATCH + 1
        assert "old_0000" not in web._scans
        assert "old_0009" not in web._scans
        assert "old_0010" in web._scans
    finally:
        web._scans.clear()
        web._scans.update(previous_scans)


def test_evict_old_scans_reduces_already_over_limit_store_to_max():
    previous_scans = dict(web._scans)
    web._scans.clear()
    over_limit_count = web.MAX_SCANS + web._SCAN_EVICTION_BATCH + 1

    try:
        for i in range(over_limit_count):
            web._scans[f"scan_{i:04d}"] = {"started_at": f"2026-01-01T00:00:{i:04d}Z"}

        web._evict_old_scans()

        assert len(web._scans) <= web.MAX_SCANS
        assert "scan_0000" not in web._scans
    finally:
        web._scans.clear()
        web._scans.update(previous_scans)


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
