"""Focused tests for web/API security hardening."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from project_prompter import web
from project_prompter.filters import SECRET_PATTERNS, redact_secrets
from project_prompter.ollama_client import validate_ollama_url

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - depends on optional web extras
    TestClient = None  # type: ignore


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434",
        "https://127.0.0.1:11434",
        "http://[::1]:11434",
        "  http://localhost:11434  ",
    ],
)
def test_validate_ollama_url_allows_loopback_hosts(url: str):
    assert validate_ollama_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:11434",
        "http://169.254.169.254/latest",
        "file:///tmp/ollama.sock",
        "http://localhost.evil.test:11434",
        "http://127.0.0.1:bad",
    ],
)
def test_validate_ollama_url_rejects_non_local_or_malformed_urls(url: str):
    with pytest.raises(ValueError):
        validate_ollama_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1.evil.test:11434",
        "http://localhost%2eevil.test:11434",
        "http://localhost:11434@example.com",
        "http://[::1]evil:11434",
    ],
)
def test_validate_ollama_url_rejects_host_confusion_inputs(url: str):
    with pytest.raises(ValueError):
        validate_ollama_url(url)


def test_validate_ollama_url_allows_case_insensitive_loopback_host():
    assert validate_ollama_url("HTTP://LOCALHOST:11434") == "HTTP://LOCALHOST:11434"


def test_validate_output_path_blocks_paths_outside_default_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert web._validate_output_path("output") == (tmp_path / "output").resolve()

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    with pytest.raises(ValueError, match="output_path not allowed"):
        web._validate_output_path(str(outside))


def test_validate_project_path_honors_allowed_scan_root(tmp_path, monkeypatch):
    allowed_root = tmp_path / "allowed"
    allowed_project = allowed_root / "project"
    outside_project = tmp_path / "outside"
    allowed_project.mkdir(parents=True)
    outside_project.mkdir()
    monkeypatch.setenv(web.ALLOWED_SCAN_ROOT_ENV, str(allowed_root))

    assert web._validate_project_path(str(allowed_project)) == allowed_project.resolve()
    with pytest.raises(ValueError, match="project_path not allowed"):
        web._validate_project_path(str(outside_project))


def test_validate_project_path_honors_project_prompter_allowed_scan_root_fallback(tmp_path, monkeypatch):
    allowed_root = tmp_path / "allowed"
    allowed_project = allowed_root / "project"
    outside_project = tmp_path / "outside"
    allowed_project.mkdir(parents=True)
    outside_project.mkdir()
    monkeypatch.delenv(web.ALLOWED_SCAN_ROOT_ENV, raising=False)
    monkeypatch.setenv(web.PROJECT_PROMPTER_ALLOWED_SCAN_ROOT_ENV, str(allowed_root))

    assert web._validate_project_path(str(allowed_project)) == allowed_project.resolve()
    with pytest.raises(ValueError, match="project_path not allowed"):
        web._validate_project_path(str(outside_project))


def test_validate_project_path_blocks_relative_escape_by_default(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    outside_project = tmp_path / "outside"
    workspace.mkdir()
    outside_project.mkdir()
    monkeypatch.chdir(workspace)

    with pytest.raises(ValueError, match="project_path not allowed"):
        web._validate_project_path("../outside")


def test_validate_project_path_rejects_filesystem_root():
    root = Path(Path.cwd().anchor).resolve()
    with pytest.raises(ValueError, match="project_path not allowed"):
        web._validate_project_path(str(root))


def test_validate_output_path_honors_project_prompter_output_root_fallback(tmp_path, monkeypatch):
    output_root = tmp_path / "output-root"
    output_root.mkdir()
    monkeypatch.delenv(web.OUTPUT_ROOT_ENV, raising=False)
    monkeypatch.setenv(web.PROJECT_PROMPTER_OUTPUT_ROOT_ENV, str(output_root))

    assert web._validate_output_path(str(output_root / "reports")) == (
        output_root / "reports"
    ).resolve()
    with pytest.raises(ValueError, match="output_path not allowed"):
        web._validate_output_path(str(tmp_path / "reports"))


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_cors_preflight_allows_only_local_web_ui_origin():
    client = TestClient(web.create_app())

    allowed = client.options(
        "/api/analyze",
        headers={
            "Origin": "http://localhost:8787",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    blocked = client.options(
        "/api/analyze",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:8787"
    assert blocked.status_code == 400
    assert "access-control-allow-origin" not in blocked.headers


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_ollama_models_rejects_non_local_url_before_network_call(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Ollama availability check should not run")

    monkeypatch.setattr(web, "check_ollama_available", fail_if_called)
    client = TestClient(web.create_app())

    response = client.get(
        "/api/ollama-models",
        params={"ollama_url": "http://example.com:11434"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Ollama URL"


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_analyze_rejects_invalid_mode_before_queueing(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    before_scans = dict(web._scans)
    client = TestClient(web.create_app())

    response = client.post(
        "/api/analyze",
        json={
            "project_path": str(project),
            "output_path": "output",
            "mode": "turbo",
            "ollama_url": "http://localhost:11434",
        },
    )

    assert response.status_code == 422
    assert web._scans == before_scans


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_analyze_rejects_invalid_ollama_url_body(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    client = TestClient(web.create_app())

    response = client.post(
        "/api/analyze",
        json={
            "project_path": str(project),
            "output_path": "output",
            "ollama_url": "http://example.com:11434",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Ollama URL"


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_analyze_rejects_output_path_escape(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    client = TestClient(web.create_app())
    outside = tmp_path.parent / f"{tmp_path.name}-outside"

    response = client.post(
        "/api/analyze",
        json={
            "project_path": str(project),
            "output_path": str(outside),
            "ollama_url": "http://localhost:11434",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "output_path not allowed"


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_analyze_rejects_project_path_outside_allowed_root_before_queueing(tmp_path, monkeypatch):
    allowed_root = tmp_path / "allowed"
    outside_project = tmp_path / "outside"
    allowed_root.mkdir()
    outside_project.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(web.ALLOWED_SCAN_ROOT_ENV, str(allowed_root))
    before_scans = dict(web._scans)
    client = TestClient(web.create_app())

    response = client.post(
        "/api/analyze",
        json={
            "project_path": str(outside_project),
            "output_path": "output",
            "ollama_url": "http://localhost:11434",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "project_path not allowed"
    assert web._scans == before_scans


def test_run_analysis_task_marks_invalid_ollama_url_failed(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    scan_id = "security-test"
    web._scans[scan_id] = {
        "status": "queued",
        "progress": [],
        "completed_at": None,
        "error": None,
    }
    request = SimpleNamespace(
        project_path=str(project),
        output_path="output",
        ollama_url="http://example.com:11434",
    )

    try:
        asyncio.run(web._run_analysis_task(scan_id, request))

        assert web._scans[scan_id]["status"] == "failed"
        assert web._scans[scan_id]["error"] == "Invalid Ollama URL"
    finally:
        web._scans.pop(scan_id, None)


def test_run_analysis_task_marks_output_path_escape_failed(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project = tmp_path / "project"
    workspace.mkdir()
    project.mkdir()
    monkeypatch.chdir(workspace)
    scan_id = "output-escape-test"
    web._scans[scan_id] = {
        "status": "queued",
        "progress": [],
        "completed_at": None,
        "error": None,
    }
    request = SimpleNamespace(
        project_path=str(project),
        output_path=str(tmp_path / "outside-output"),
        ollama_url="http://localhost:11434",
    )

    try:
        asyncio.run(web._run_analysis_task(scan_id, request))

        assert web._scans[scan_id]["status"] == "failed"
        assert web._scans[scan_id]["error"] == "output_path not allowed"
    finally:
        web._scans.pop(scan_id, None)


def test_connection_string_pattern_is_bounded_and_still_redacts():
    pattern = next(p for name, p, _ in SECRET_PATTERNS if name == "CONNECTION_STRING")
    assert ".*?" not in pattern
    assert "{1,100}" in pattern
    assert "{1,200}" in pattern

    content = 'DATABASE_URL = "postgresql://user:password123@localhost:5432/mydb"'
    redacted, findings = redact_secrets(content)

    assert "password123" not in redacted
    assert ("CONNECTION_STRING", 1) in findings


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_security_headers_present_on_health_endpoint():
    """Responses must include basic defence-in-depth security headers."""
    client = TestClient(web.create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("x-xss-protection") == "1; mode=block"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.skipif(TestClient is None or not web.WEB_AVAILABLE, reason="FastAPI not available")
def test_cors_uses_configured_port():
    """CORS allowed origins should reflect the port passed to create_app."""
    client = TestClient(web.create_app(host="127.0.0.1", port=9090))

    allowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:9090",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:9090"
