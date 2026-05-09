"""Tests for mode system, structural analysis, cache, trading detection, prompt quality, and web UI schema."""

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from project_prompter.mode_config import (
    MODE_DEFAULTS,
    get_mode_defaults,
    evidence_level_for_mode,
)
from project_prompter.models import ScanOptions, ScanMetadata, ProjectAnalysis, TechStack, ScannedFile
from project_prompter.filters import should_ignore_folder, should_ignore_file, secret_file_category
from project_prompter.structural_analyzer import (
    build_structural_summary,
    large_file_risk_note,
)
from project_prompter.cache_manager import load_cached, save_cached, clear_cache, _cache_path
from project_prompter.prompt_templates._common import (
    build_analysis_metadata,
    build_evidence_disclaimer,
    build_special_domain_section
)
from project_prompter.cli import create_parser, _validate_flags, _resolve_options


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analysis(
    mode: str = "fast",
    ollama_used: bool = False,
    ollama_error: str | None = "Ollama not available",
    is_trading: bool = False,
    num_files: int = 30,
) -> ProjectAnalysis:
    """Create a test ProjectAnalysis."""
    from project_prompter.models import DomainDetectionResult
    
    if is_trading:
        domain_res = DomainDetectionResult("trading_fintech", "high", 15, 3, ["binance"], ["fake"])
    else:
        domain_res = DomainDetectionResult("generic", "low", 0, 0, [], [])
        
    meta = ScanMetadata(
        scan_id="test-001",
        scanned_at="2024-01-01T00:00:00Z",
        project_path="/test",
        total_files_found=50,
        files_scanned=num_files,
        files_skipped=20,
        files_redacted=0,
        ollama_used=ollama_used,
        ollama_model="qwen2.5-coder:1.5b",
        ollama_available=ollama_used,
        ollama_error=ollama_error,
        target_model="all",
        duration_seconds=1.0,
        mode=mode,
        evidence_level="limited" if not ollama_used else "medium",
        domain_result=domain_res,
    )

    files = [
        ScannedFile(path=Path("main.py"), relative_path="main.py", extension=".py", size=1000, priority_score=75)
    ]

    return ProjectAnalysis(
        project_path="/test",
        file_tree="test/\n├── main.py\n└── README.md",
        tech_stack=TechStack(languages=["Python"]),
        important_files=files * min(num_files, 5),
        file_summaries={"main.py": "Main entry point."},
        scan_metadata=meta,
        project_summary="A test project.",
        domain_result=domain_res,
    )


def _make_namespace(**kwargs):
    """Create a minimal argparse Namespace for testing."""
    import argparse
    defaults = {
        "project_path": "/test",
        "output": "./output",
        "mode": "fast",
        "model": "qwen2.5-coder:1.5b",
        "ollama_url": "http://localhost:11434",
        "use_ollama": False,
        "no_ollama": False,
        "strict_ollama": False,
        "max_files": None,
        "max_chars_per_file": None,
        "exclude": [],
        "use_cache": False,
        "no_cache": False,
        "clear_cache": False,
        "clear_cache_only": False,
        "format": "markdown",
        "target_model": "all",
        "ui": False,
        "host": "127.0.0.1",
        "port": 8787,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ===========================================================================
# 1. Default mode tests
# ===========================================================================

class TestDefaultMode:
    def test_default_mode_is_fast(self):
        assert MODE_DEFAULTS["fast"]["use_ollama"] is False

    def test_fast_mode_no_ollama(self):
        opts = _resolve_options(_make_namespace(mode="fast"))
        assert opts.use_ollama is False

    def test_fast_mode_ignores_use_ollama_flag(self):
        """Fast mode must NEVER use Ollama, even if --use-ollama is given."""
        opts = _resolve_options(_make_namespace(mode="fast", use_ollama=True))
        assert opts.use_ollama is False

    def test_balanced_mode_ollama_off_by_default(self):
        opts = _resolve_options(_make_namespace(mode="balanced"))
        assert opts.use_ollama is False

    def test_balanced_mode_ollama_on_with_flag(self):
        opts = _resolve_options(_make_namespace(mode="balanced", use_ollama=True))
        assert opts.use_ollama is True


# ===========================================================================
# 2. Mode config tests
# ===========================================================================

class TestModeConfig:
    def test_fast_defaults(self):
        d = get_mode_defaults("fast")
        assert d["max_files"] == 40
        assert d["max_chars_per_file"] == 3000
        assert d["ollama_max_files"] == 0
        assert d["use_ollama"] is False

    def test_balanced_defaults(self):
        d = get_mode_defaults("balanced")
        assert d["max_files"] == 50
        assert d["max_chars_per_file"] == 4000
        assert d["ollama_max_files"] == 10

    def test_deep_defaults(self):
        d = get_mode_defaults("deep")
        assert d["max_files"] == 80
        assert d["max_chars_per_file"] == 6000
        assert d["ollama_max_files"] == 20

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            get_mode_defaults("turbo")

    def test_evidence_level_fast(self):
        assert evidence_level_for_mode("fast", False) == "limited"

    def test_evidence_level_balanced(self):
        assert evidence_level_for_mode("balanced", False) == "medium"

    def test_evidence_level_deep_ollama(self):
        assert evidence_level_for_mode("deep", True) == "high"


# ===========================================================================
# 3. Mode precedence — explicit values override mode defaults
# ===========================================================================

class TestModePrecedence:
    def test_explicit_max_files_overrides_mode_default(self):
        opts = _resolve_options(_make_namespace(mode="fast", max_files=100))
        assert opts.max_files == 100

    def test_explicit_max_chars_overrides_mode_default(self):
        opts = _resolve_options(_make_namespace(mode="fast", max_chars_per_file=8000))
        assert opts.max_chars_per_file == 8000

    def test_mode_default_applies_when_not_explicit(self):
        opts = _resolve_options(_make_namespace(mode="deep"))
        assert opts.max_files == 80
        assert opts.max_chars_per_file == 6000

    def test_cli_rejects_zero_max_files(self):
        with pytest.raises(SystemExit):
            create_parser().parse_args(["/test", "--max-files", "0"])

    def test_cli_rejects_too_large_max_chars_per_file(self):
        with pytest.raises(SystemExit):
            create_parser().parse_args(["/test", "--max-chars-per-file", "50001"])


# ===========================================================================
# 3b. User-defined excludes
# ===========================================================================

class TestUserDefinedExcludes:
    def test_parser_accepts_repeated_exclude(self):
        args = create_parser().parse_args([
            "/test",
            "--exclude", "data",
            "--exclude", "fixtures",
        ])
        assert args.exclude == ["data", "fixtures"]

    def test_resolve_options_sets_extra_ignore_dirs(self):
        opts = _resolve_options(_make_namespace(exclude=["data", "fixtures"]))
        assert opts.extra_ignore_dirs == ["data", "fixtures"]

    def test_analyze_project_applies_extra_ignore_dirs(self, tmp_path):
        from project_prompter.analyzer import analyze_project

        project = tmp_path / "project"
        project.mkdir()
        data_dir = project / "data"
        data_dir.mkdir()
        (data_dir / "raw.py").write_text("SECRET = 'not read'")
        (project / "main.py").write_text("print('hello')")

        options = ScanOptions(
            project_path=project,
            output_path=tmp_path / "out",
            max_files=5,
            max_chars_per_file=100,
            use_ollama=False,
            target_model="generic",
            extra_ignore_dirs=["data"],
        )

        analysis = analyze_project(options, progress_callback=lambda _msg: None)

        assert "data" not in analysis.file_tree
        assert "raw.py" not in analysis.file_tree
        assert [f.relative_path for f in analysis.important_files] == ["main.py"]
        assert analysis.scan_metadata.files_skipped == 1


# ===========================================================================
# 4. Conflicting CLI flags
# ===========================================================================

class TestConflictingFlags:
    def test_use_ollama_and_no_ollama_conflicts(self):
        ns = _make_namespace(use_ollama=True, no_ollama=True)
        error = _validate_flags(ns)
        assert error is not None
        assert "Conflicting" in error

    def test_use_cache_and_no_cache_conflicts(self):
        ns = _make_namespace(use_cache=True, no_cache=True)
        error = _validate_flags(ns)
        assert error is not None
        assert "Conflicting" in error

    def test_no_conflict_when_only_one(self):
        ns = _make_namespace(use_ollama=True, no_ollama=False)
        assert _validate_flags(ns) is None

    def test_no_conflict_default(self):
        ns = _make_namespace()
        assert _validate_flags(ns) is None


# ===========================================================================
# 5. Ignore filter tests
# ===========================================================================

class TestIgnoreFilters:
    def test_ruff_cache_ignored(self):
        assert should_ignore_folder(".ruff_cache") is True

    def test_venv_ignored(self):
        assert should_ignore_folder(".venv") is True

    def test_pycache_ignored(self):
        assert should_ignore_folder("__pycache__") is True

    def test_runtime_ignored(self):
        assert should_ignore_folder("runtime") is True

    def test_output_ignored(self):
        assert should_ignore_folder("output") is True

    def test_outputs_ignored(self):
        assert should_ignore_folder("outputs") is True

    def test_node_modules_ignored(self):
        assert should_ignore_folder("node_modules") is True

    def test_htmlcov_ignored(self):
        assert should_ignore_folder("htmlcov") is True


# ===========================================================================
# 6. Secret file tests
# ===========================================================================

class TestSecretFiles:
    def test_env_file_not_read(self):
        ignored, reason = should_ignore_file(Path(".env"))
        assert ignored is True
        assert reason == "env_file"

    def test_env_local_not_read(self):
        ignored, _ = should_ignore_file(Path(".env.local"))
        assert ignored is True

    def test_env_example_skipped(self):
        """According to policy, .env.example is also skipped for safety."""
        ignored, reason = should_ignore_file(Path(".env.example"))
        assert ignored is True
        assert reason == "env_file"

    def test_pem_file_not_read(self):
        ignored, _ = should_ignore_file(Path("server.pem"))
        assert ignored is True

    def test_id_rsa_not_read(self):
        ignored, _ = should_ignore_file(Path("id_rsa"))
        assert ignored is True


# ===========================================================================
# 7. Secret file category (for file tree masking)
# ===========================================================================

class TestSecretFileCategory:
    def test_env_category(self):
        assert secret_file_category(Path(".env")) == "env file"

    def test_env_local_category(self):
        assert secret_file_category(Path(".env.local")) == "env file"

    def test_env_example_category(self):
        assert secret_file_category(Path(".env.example")) == "env file"

    def test_pem_category(self):
        assert secret_file_category(Path("cert.pem")) == "private key/certificate"

    def test_key_category(self):
        assert secret_file_category(Path("server.key")) == "private key/certificate"

    def test_crt_category(self):
        assert secret_file_category(Path("cert.crt")) == "private key/certificate"

    def test_id_rsa_category(self):
        assert secret_file_category(Path("id_rsa")) == "credential file"

    def test_id_ed25519_category(self):
        assert secret_file_category(Path("id_ed25519")) == "credential file"

    def test_normal_file_no_category(self):
        assert secret_file_category(Path("main.py")) is None


# ===========================================================================
# 8. Structural summary tests
# ===========================================================================

class TestStructuralSummary:
    def test_python_imports_extracted(self):
        content = "import os\nfrom pathlib import Path\n"
        summary = build_structural_summary(
            file_path=Path("test.py"), relative_path="test.py",
            content=content, size=100, priority_score=50,
        )
        assert "os" in summary
        assert "pathlib.Path" in summary

    def test_python_classes_extracted(self):
        content = "class MyService:\n    pass\n"
        summary = build_structural_summary(
            file_path=Path("test.py"), relative_path="test.py",
            content=content, size=100, priority_score=50,
        )
        assert "MyService" in summary

    def test_python_functions_extracted(self):
        content = "def process_data(input, output):\n    pass\n"
        summary = build_structural_summary(
            file_path=Path("test.py"), relative_path="test.py",
            content=content, size=100, priority_score=50,
        )
        assert "process_data" in summary

    def test_python_async_functions_extracted(self):
        content = "import asyncio\nasync def fetch_data(url):\n    pass\n"
        summary = build_structural_summary(
            file_path=Path("test.py"), relative_path="test.py",
            content=content, size=100, priority_score=50,
        )
        assert "fetch_data" in summary
        assert "Async" in summary

    def test_python_env_reads_extracted(self):
        content = "import os\nval = os.environ.get('DATABASE_URL')\n"
        summary = build_structural_summary(
            file_path=Path("test.py"), relative_path="test.py",
            content=content, size=200, priority_score=50,
        )
        assert "DATABASE_URL" in summary


# ===========================================================================
# 9. Large file risk tests
# ===========================================================================

class TestLargeFileRisk:
    def test_100kb_file_is_critical_risk(self):
        risk = large_file_risk_note("main.py", 110 * 1024)
        assert risk is not None
        assert "Large File Risk" in risk
        assert "main.py" in risk

    def test_50kb_file_is_warning(self):
        risk = large_file_risk_note("utils.py", 55 * 1024)
        assert risk is not None
        assert "Warning" in risk

    def test_small_file_no_risk(self):
        risk = large_file_risk_note("config.py", 5 * 1024)
        assert risk is None





# ===========================================================================
# 11. Prompt honesty / evidence metadata
# ===========================================================================

class TestPromptHonesty:
    def test_analysis_metadata_present(self):
        analysis = _make_analysis(mode="fast", ollama_used=False)
        metadata = build_analysis_metadata(analysis)
        assert "Analysis Type" in metadata
        assert "Evidence Level" in metadata
        assert "Full Source Audit" in metadata
        assert "Ollama Used" in metadata
        assert "Included File Evidence Count" in metadata
        assert "Skipped Files Count" in metadata

    def test_evidence_disclaimer_for_static_only(self):
        analysis = _make_analysis(mode="fast", ollama_used=False)
        disclaimer = build_evidence_disclaimer(analysis)
        assert "Do not claim to have performed a full source-code audit" in disclaimer

    def test_limited_evidence_warning(self):
        analysis = _make_analysis(num_files=5)
        disclaimer = build_evidence_disclaimer(analysis)
        assert "Evidence is limited" in disclaimer

    def test_no_disclaimer_for_deep_ollama(self):
        analysis = _make_analysis(mode="deep", ollama_used=True, ollama_error=None, num_files=50)
        disclaimer = build_evidence_disclaimer(analysis)
        assert "Do not claim" not in disclaimer

    def test_special_domain_section_present(self):
        analysis = _make_analysis(is_trading=True)
        section = build_special_domain_section(analysis)
        assert "Trading / Financial Automation" in section
        assert "kill switch" in section.lower()

    def test_special_domain_section_absent(self):
        analysis = _make_analysis(is_trading=False)
        section = build_special_domain_section(analysis)
        assert section == ""


# ===========================================================================
# 12. Cache tests
# ===========================================================================

class TestCache:
    def test_cache_save_and_load(self, tmp_path):
        """Saved cache data should be loadable."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        save_cached(tmp_path, test_file, "fast", {"structural_summary": "test summary"})
        cached = load_cached(tmp_path, test_file, "fast")
        assert cached is not None
        assert cached["structural_summary"] == "test summary"

    def test_cache_miss_when_not_saved(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")
        cached = load_cached(tmp_path, test_file, "fast")
        assert cached is None

    def test_cache_miss_on_file_change(self, tmp_path):
        """If file changes (mtime changes), cache should miss."""
        test_file = tmp_path / "test.py"
        test_file.write_text("v1")

        save_cached(tmp_path, test_file, "fast", {"data": "v1"})

        # Modify file (changes mtime and size)
        import time
        time.sleep(0.1)
        test_file.write_text("v2 - this is different content")

        cached = load_cached(tmp_path, test_file, "fast")
        # Cache key includes mtime+size, so this should be None or different
        # (may produce None because the old key no longer matches)
        assert cached is None

    def test_clear_cache(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        save_cached(tmp_path, test_file, "fast", {"data": "test"})

        count = clear_cache(tmp_path)
        assert count >= 1

        cached = load_cached(tmp_path, test_file, "fast")
        assert cached is None

    def test_cache_path_hashes_relative_path_component(self, tmp_path):
        nested = tmp_path / "dir__name"
        nested.mkdir()
        test_file = nested / "file.py"
        test_file.write_text("print('hello')")

        cache_path = _cache_path(tmp_path, test_file, "fast")
        rel = "dir__name/file.py"
        expected_rel_hash = hashlib.sha256(rel.encode()).hexdigest()[:12]

        assert cache_path.name.startswith(f"{expected_rel_hash}__fast__")
        assert "dir__name" not in cache_path.name
        assert "file.py" not in cache_path.name


# ===========================================================================
# 13. Fast mode purity — no Ollama calls
# ===========================================================================

class TestFastModePurity:
    def test_fast_mode_never_calls_ollama(self):
        """In fast mode, Ollama client functions must never be called."""
        with patch("project_prompter.summarizer.check_ollama_available") as mock_check, \
             patch("project_prompter.summarizer.check_model_exists") as mock_model, \
             patch("project_prompter.summarizer.summarize_file") as mock_summarize, \
             patch("project_prompter.summarizer.summarize_project") as mock_project:

            from project_prompter.summarizer import run_summarization
            from project_prompter.models import TechStack

            options = ScanOptions(
                project_path=Path("."),
                mode="fast",
                use_ollama=False,
            )

            files = [
                ScannedFile(
                    path=Path("test.py"), relative_path="test.py",
                    extension=".py", size=100, priority_score=50,
                    content_preview="def hello(): pass",
                )
            ]

            run_summarization(
                important_files=files,
                tech_stack=TechStack(languages=["Python"]),
                file_tree="test/\n└── test.py",
                model="qwen2.5-coder:1.5b",
                ollama_url="http://localhost:11434",
                use_ollama=False,
                options=options,
            )

            # None of these should have been called
            mock_check.assert_not_called()
            mock_model.assert_not_called()
            mock_summarize.assert_not_called()
            mock_project.assert_not_called()


# ===========================================================================
# 14. Web UI schema test
# ===========================================================================

class TestWebUISchema:
    """Verify /api/analyze accepts default payload without 422."""

    def test_default_payload_accepted(self):
        """The default UI payload must create a valid AnalyzeRequest."""
        try:
            from project_prompter.web import AnalyzeRequest, WEB_AVAILABLE
        except ImportError:
            pytest.skip("FastAPI not available")

        if not WEB_AVAILABLE:
            pytest.skip("FastAPI not available")

        # This is the exact payload the UI sends
        payload = {
            "project_path": "C:/dev/test-project",
            "output_path": "./output",
            "mode": "fast",
            "model": "qwen2.5-coder:1.5b",
            "ollama_url": "http://localhost:11434",
            "max_files": 40,
            "max_chars_per_file": 3000,
            "use_ollama": False,
            "target_model": "all",
            "use_cache": True,
            "clear_cache": False,
        }

        # This must NOT raise ValidationError
        req = AnalyzeRequest(**payload)
        assert req.project_path == "C:/dev/test-project"
        assert req.mode == "fast"
        assert req.use_ollama is False
        assert req.use_cache is True
        assert req.extra_ignore_dirs == []

    def test_minimal_payload_accepted(self):
        """Only project_path is truly required."""
        try:
            from project_prompter.web import AnalyzeRequest, WEB_AVAILABLE
        except ImportError:
            pytest.skip("FastAPI not available")

        if not WEB_AVAILABLE:
            pytest.skip("FastAPI not available")

        req = AnalyzeRequest(project_path="/test")
        assert req.mode == "fast"
        assert req.use_ollama is False
        assert req.max_files is None  # Uses mode default at runtime
        assert req.extra_ignore_dirs == []

    def test_null_max_files_accepted(self):
        """max_files=null means 'use mode default'."""
        try:
            from project_prompter.web import AnalyzeRequest, WEB_AVAILABLE
        except ImportError:
            pytest.skip("FastAPI not available")

        if not WEB_AVAILABLE:
            pytest.skip("FastAPI not available")

        req = AnalyzeRequest(project_path="/test", max_files=None)
        assert req.max_files is None

    def test_extra_ignore_dirs_payload_accepted(self):
        try:
            from project_prompter.web import AnalyzeRequest, WEB_AVAILABLE
        except ImportError:
            pytest.skip("FastAPI not available")

        if not WEB_AVAILABLE:
            pytest.skip("FastAPI not available")

        req = AnalyzeRequest(project_path="/test", extra_ignore_dirs=["fixtures"])
        assert req.extra_ignore_dirs == ["fixtures"]

    def test_invalid_max_files_rejected_by_request_schema(self):
        try:
            from pydantic import ValidationError
            from project_prompter.web import AnalyzeRequest, WEB_AVAILABLE
        except ImportError:
            pytest.skip("FastAPI not available")

        if not WEB_AVAILABLE:
            pytest.skip("FastAPI not available")

        with pytest.raises(ValidationError):
            AnalyzeRequest(project_path="/test", max_files=0)

    def test_invalid_max_chars_rejected_by_request_schema(self):
        try:
            from pydantic import ValidationError
            from project_prompter.web import AnalyzeRequest, WEB_AVAILABLE
        except ImportError:
            pytest.skip("FastAPI not available")

        if not WEB_AVAILABLE:
            pytest.skip("FastAPI not available")

        with pytest.raises(ValidationError):
            AnalyzeRequest(project_path="/test", max_chars_per_file=100)

    def test_invalid_mode_rejected_by_request_schema(self):
        try:
            from pydantic import ValidationError
            from project_prompter.web import AnalyzeRequest, WEB_AVAILABLE
        except ImportError:
            pytest.skip("FastAPI not available")

        if not WEB_AVAILABLE:
            pytest.skip("FastAPI not available")

        with pytest.raises(ValidationError):
            AnalyzeRequest(project_path="/test", mode="turbo")

    def test_scan_store_eviction(self):
        from project_prompter.web import (
            MAX_SCANS,
            _SCAN_EVICTION_BATCH,
            _evict_old_scans,
            _scans,
        )

        previous_scans = dict(_scans)
        _scans.clear()
        try:
            for i in range(MAX_SCANS):
                _scans[f"scan_{i:04d}"] = {"started_at": f"2026-01-01T00:00:{i:04d}Z"}

            assert len(_scans) == MAX_SCANS

            _evict_old_scans()

            assert len(_scans) == MAX_SCANS - _SCAN_EVICTION_BATCH
            assert "scan_0000" not in _scans
            assert f"scan_{MAX_SCANS - 1:04d}" in _scans
        finally:
            _scans.clear()
            _scans.update(previous_scans)

    def test_run_analysis_task_passes_extra_ignore_dirs(self, tmp_path, monkeypatch):
        from project_prompter import analyzer, web

        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.chdir(tmp_path)

        captured = {}

        def fake_analyze_project(options, progress_callback=None):
            captured["options"] = options
            return _make_analysis()

        monkeypatch.setattr(analyzer, "analyze_project", fake_analyze_project)

        scan_id = "extra-ignore-test"
        web._scans[scan_id] = {
            "status": "queued",
            "progress": [],
            "completed_at": None,
            "error": None,
        }
        request = SimpleNamespace(
            project_path=str(project),
            output_path="output",
            mode="fast",
            model="qwen2.5-coder:1.5b",
            ollama_url="http://localhost:11434",
            max_files=None,
            max_chars_per_file=None,
            use_ollama=False,
            target_model="all",
            use_cache=True,
            clear_cache=False,
            extra_ignore_dirs=["fixtures"],
        )

        try:
            asyncio.run(web._run_analysis_task(scan_id, request))
            assert web._scans[scan_id]["status"] == "completed"
            assert captured["options"].extra_ignore_dirs == ["fixtures"]
        finally:
            web._scans.pop(scan_id, None)


# ===========================================================================
# 15. Ollama strict mode
# ===========================================================================

class TestStrictOllama:
    def test_strict_ollama_set_in_options(self):
        opts = _resolve_options(_make_namespace(
            mode="balanced",
            use_ollama=True,
            strict_ollama=True,
        ))
        assert opts.strict_ollama is True
        assert opts.use_ollama is True


def test_analyze_project_does_not_warn_about_existing_env_example_or_tests(tmp_path):
    from project_prompter.analyzer import analyze_project

    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    project.mkdir(exist_ok=True)
    (project / ".env.example").write_text("API_KEY=\n", encoding="utf-8")
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (project / "tests" / "test_main.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    analysis = analyze_project(
        ScanOptions(
            project_path=project,
            output_path=tmp_path / "out",
            max_files=10,
            max_chars_per_file=1000,
            use_ollama=False,
            target_model="generic",
            dry_run=True,
        ),
        progress_callback=lambda _msg: None,
    )

    joined = "\n".join(analysis.risk_notes)
    assert "No .env.example file detected" not in joined
    assert "No test files or testing tools detected" not in joined


def test_analyze_project_does_not_treat_protest_file_as_test_suite(tmp_path):
    from project_prompter.analyzer import analyze_project

    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (project / "protest.py").write_text("print('not a test')\n", encoding="utf-8")

    analysis = analyze_project(
        ScanOptions(
            project_path=project,
            output_path=tmp_path / "out",
            max_files=10,
            max_chars_per_file=1000,
            use_ollama=False,
            target_model="generic",
            dry_run=True,
        ),
        progress_callback=lambda _msg: None,
    )

    joined = "\n".join(analysis.risk_notes)
    assert "No test files or testing tools detected" in joined
