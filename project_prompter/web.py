"""FastAPI web UI backend for the Local Project Prompt Generator."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Response
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
    import uvicorn
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

from . import __version__
from .mode_config import MODE_DEFAULTS, get_mode_defaults
from .models import ScanOptions
from .ollama_client import list_ollama_models, check_ollama_available, validate_ollama_url
from .web_services import build_file_previews
from .web_security import enforce_analyze_rate_limit, validate_extra_ignore_dirs

# In-memory scan store
_scans: Dict[str, Dict[str, Any]] = {}
MAX_SCANS = 100
_SCAN_EVICTION_BATCH = 10
MAX_PREVIEW_CHARS_PER_FILE = 40_000
MAX_TOTAL_PREVIEW_CHARS = 500_000

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_SCAN_ROOT_ENV = "ALLOWED_SCAN_ROOT"
PROJECT_PROMPTER_ALLOWED_SCAN_ROOT_ENV = "PROJECT_PROMPTER_ALLOWED_SCAN_ROOT"
OUTPUT_ROOT_ENV = "OUTPUT_ROOT"
PROJECT_PROMPTER_OUTPUT_ROOT_ENV = "PROJECT_PROMPTER_OUTPUT_ROOT"


# ---------------------------------------------------------------------------
# Request model — defined at module level so FastAPI can resolve it correctly
# ---------------------------------------------------------------------------

if WEB_AVAILABLE:
    class AnalyzeRequest(BaseModel):
        project_path: str
        output_path: str = "./output"
        mode: Literal["fast", "balanced", "deep"] = "fast"
        model: str = "qwen2.5-coder:1.5b"
        ollama_url: str = "http://localhost:11434"
        max_files: Optional[int] = Field(default=None, ge=1, le=500)       # None = use mode default
        max_chars_per_file: Optional[int] = Field(default=None, ge=100, le=200_000)  # None = use mode default
        use_ollama: bool = False
        target_model: str = "all"
        use_cache: bool = True
        clear_cache: bool = False
        extra_ignore_dirs: List[str] = Field(default_factory=list, max_length=200)
else:
    AnalyzeRequest = None  # type: ignore


def _evict_old_scans() -> None:
    """Remove the oldest scans when the in-memory scan store reaches its limit."""
    while len(_scans) >= MAX_SCANS:
        oldest_keys = sorted(
            _scans.keys(),
            key=lambda k: _scans[k].get("started_at", ""),
        )[:_SCAN_EVICTION_BATCH]
        for key in oldest_keys:
            del _scans[key]


def _is_relative_to(path: Path, root: Path) -> bool:
    """Return True when path is root or a descendant of root."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_configured_root(
    env_var: str,
    default: Path | None = None,
    fallback_env_vars: tuple[str, ...] = (),
) -> Path | None:
    value = None
    for candidate in (env_var, *fallback_env_vars):
        value = os.environ.get(candidate)
        if value:
            break

    if not value:
        return default.resolve() if default is not None else None

    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{env_var} must point to an existing directory")
    return root


def _is_sensitive_project_root(path: Path) -> bool:
    if path == Path(path.anchor).resolve():
        return True

    sensitive_roots: list[Path] = []
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot")
        if system_root:
            sensitive_roots.append(Path(system_root).expanduser().resolve())
    else:
        sensitive_roots.extend(Path(p).resolve() for p in ("/etc", "/proc", "/sys", "/dev"))

    return any(path == root or _is_relative_to(path, root) for root in sensitive_roots)


def _validate_project_path(project_path: str) -> Path:
    try:
        raw_path = Path(project_path).expanduser()
        resolved = raw_path.resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("project_path not allowed") from exc

    if not resolved.is_dir() or _is_sensitive_project_root(resolved):
        raise ValueError("project_path not allowed")

    try:
        allowed_root = _resolve_configured_root(
            ALLOWED_SCAN_ROOT_ENV,
            fallback_env_vars=(PROJECT_PROMPTER_ALLOWED_SCAN_ROOT_ENV,),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("project_path not allowed") from exc
    if allowed_root is not None and not _is_relative_to(resolved, allowed_root):
        raise ValueError("project_path not allowed")
    if (
        allowed_root is None
        and not raw_path.is_absolute()
        and not _is_relative_to(resolved, Path.cwd().resolve())
    ):
        raise ValueError("project_path not allowed")

    return resolved


def _validate_output_path(output_path: str) -> Path:
    try:
        resolved = Path(output_path).expanduser().resolve()
        output_root = _resolve_configured_root(
            OUTPUT_ROOT_ENV,
            Path.cwd(),
            fallback_env_vars=(PROJECT_PROMPTER_OUTPUT_ROOT_ENV,),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("output_path not allowed") from exc

    if output_root is None or not _is_relative_to(resolved, output_root):
        raise ValueError("output_path not allowed")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("output_path not allowed")

    return resolved


def _validate_analysis_inputs(request: Any) -> tuple[Path, Path, str]:
    project_path = _validate_project_path(request.project_path)
    output_path = _validate_output_path(request.output_path)

    try:
        ollama_url = validate_ollama_url(request.ollama_url)
    except ValueError as exc:
        raise ValueError("Invalid Ollama URL") from exc

    return project_path, output_path, ollama_url


def create_app(host: str = "127.0.0.1", port: int = 8787) -> "FastAPI":
    """Create and configure the FastAPI application."""
    if not WEB_AVAILABLE:
        raise ImportError("FastAPI and uvicorn are required for the web UI. Install with: pip install fastapi uvicorn")

    app = FastAPI(
        title="Local Project Prompt Generator",
        description="Scan local projects and generate optimized AI prompts — locally, privately.",
        version=__version__,
    )

    # Build CORS allowed origins from the configured host/port so the UI always
    # matches regardless of which address the server was started on.
    cors_origins: List[str] = [f"http://{host}:{port}"]
    # Always include the canonical loopback aliases so tests and default usage work.
    for alias in ("localhost", "127.0.0.1"):
        origin = f"http://{alias}:{port}"
        if origin not in cors_origins:
            cors_origins.append(origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # ---------------------------------------------------------------------------
    # Security-headers middleware — defence-in-depth for browser clients
    # ---------------------------------------------------------------------------

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    # Mount static files if directory exists
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ---------------------------------------------------------------------------
    # Validation error handler — returns readable JSON instead of raw 422
    # ---------------------------------------------------------------------------

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        # Simplify pydantic v2 error format for readability
        readable = [
            {
                "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in errors
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "errors": readable,
                "hint": "Check that all required fields are present and have the correct types.",
            },
        )

    @app.get("/", response_class=HTMLResponse)
    async def serve_ui():
        """Serve the web interface."""
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
        return HTMLResponse(content=_fallback_html())

    @app.get("/api/health")
    async def health():
        """Health check endpoint."""
        return {
            "status": "ok",
            "version": __version__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "security_note": "This tool does not upload code to any external service.",
        }

    @app.get("/api/ollama-models")
    async def ollama_models(ollama_url: str = "http://localhost:11434"):
        """List available Ollama models."""
        try:
            ollama_url = validate_ollama_url(ollama_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Ollama URL") from exc

        available, error = check_ollama_available(ollama_url)
        if not available:
            return JSONResponse(
                status_code=200,
                content={
                    "available": False,
                    "error": error,
                    "models": [],
                },
            )
        models = list_ollama_models(ollama_url)
        # Choose best default: qwen2.5-coder:1.5b > llama3.2:3b > first model
        default_model = "qwen2.5-coder:1.5b"
        if not any(m.startswith("qwen2.5-coder") for m in models):
            if any(m.startswith("llama3.2") for m in models):
                default_model = next(m for m in models if m.startswith("llama3.2"))
            elif models:
                default_model = models[0]
        return {
            "available": True,
            "models": models,
            "default": default_model,
        }

    @app.get("/api/mode-defaults")
    async def mode_defaults():
        """Return default settings for each analysis mode."""
        return MODE_DEFAULTS

    @app.post("/api/analyze")
    async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
        """Start a project analysis scan."""
        try:
            enforce_analyze_rate_limit()
            project_path, output_path, ollama_url = _validate_analysis_inputs(request)
        except ValueError as exc:
            message = str(exc)
            if message.startswith("rate limit exceeded:"):
                retry_after = "60"
                if "|" in message:
                    message, retry_after = message.split("|", 1)
                raise HTTPException(
                    status_code=429,
                    detail=message,
                    headers={"Retry-After": retry_after},
                ) from exc
            raise HTTPException(status_code=400, detail=message) from exc

        request.project_path = str(project_path)
        request.output_path = str(output_path)
        request.ollama_url = ollama_url
        request.extra_ignore_dirs = validate_extra_ignore_dirs(request.extra_ignore_dirs)

        _evict_old_scans()
        scan_id = uuid.uuid4().hex[:20]

        _scans[scan_id] = {
            "scan_id": scan_id,
            "status": "queued",
            "progress": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
            "outputs": {},
            "project_path": request.project_path,
            "mode": request.mode,
        }

        background_tasks.add_task(
            _run_analysis_task,
            scan_id=scan_id,
            request=request,
        )

        return {
            "scan_id": scan_id,
            "status": "queued",
            "message": "Analysis started. Poll /api/results/{scan_id} for status.",
        }

    @app.get("/api/results/{scan_id}")
    async def get_results(scan_id: str):
        """Get the results and status of a scan."""
        if scan_id not in _scans:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")
        return _scans[scan_id]

    @app.get("/api/download/{scan_id}/{filename:path}")
    async def download_file(scan_id: str, filename: str):
        """Download a generated output file."""
        if scan_id not in _scans:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")

        scan = _scans[scan_id]
        if scan["status"] != "completed":
            raise HTTPException(status_code=400, detail="Scan not yet completed.")

        outputs = scan.get("outputs", {})
        if filename not in outputs:
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found in scan outputs.")

        file_path = Path(outputs[filename])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Output file no longer exists: {filename}")

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type="application/octet-stream",
        )

    return app


async def _run_analysis_task(scan_id: str, request: Any) -> None:
    """Background task to run the analysis."""
    from .analyzer import analyze_project
    from .cache_manager import clear_cache as do_clear_cache

    scan = _scans[scan_id]
    scan["status"] = "running"

    def progress(msg: str) -> None:
        scan["progress"].append(msg)

    try:
        # Re-validate inputs inside the background task so any tampered or
        # stale values are caught before starting heavy analysis work.
        project_path, output_base_path, ollama_url = _validate_analysis_inputs(request)
        request.extra_ignore_dirs = validate_extra_ignore_dirs(request.extra_ignore_dirs)
        output_path = output_base_path / scan_id
        mode = request.mode
        defaults = get_mode_defaults(mode)

        # Resolve limits: explicit request values override mode defaults
        max_files = request.max_files if request.max_files is not None else defaults["max_files"]
        max_chars = request.max_chars_per_file if request.max_chars_per_file is not None else defaults["max_chars_per_file"]

        # Fast mode: always disable Ollama
        use_ollama = request.use_ollama
        if mode == "fast":
            use_ollama = False

        options = ScanOptions(
            project_path=project_path,
            output_path=output_path,
            model=request.model,
            ollama_url=ollama_url,
            max_files=max_files,
            max_chars_per_file=max_chars,
            use_ollama=use_ollama,
            target_model=request.target_model,
            mode=mode,
            use_cache=request.use_cache,
            clear_cache=False,  # handled below
            ollama_max_files=defaults["ollama_max_files"],
            extra_ignore_dirs=list(request.extra_ignore_dirs),
        )

        # Clear cache if requested
        if request.clear_cache:
            count = do_clear_cache(project_path)
            progress(f"  Cache cleared: {count} file(s) deleted.")

        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_running_loop()
        analysis = await loop.run_in_executor(
            None,
            lambda: analyze_project(options, progress_callback=progress),
        )

        # Collect output file paths
        outputs = {}
        if output_path.exists():
            for f in output_path.rglob("*"):
                if f.is_file():
                    rel = str(f.relative_to(output_path)).replace("\\", "/")
                    outputs[rel] = str(f)

        # Read file contents for preview
        file_contents, previews_truncated = build_file_previews(
            outputs=outputs,
            per_file_limit=MAX_PREVIEW_CHARS_PER_FILE,
            total_limit=MAX_TOTAL_PREVIEW_CHARS,
        )

        scan["status"] = "completed"
        scan["completed_at"] = datetime.now(timezone.utc).isoformat()
        scan["outputs"] = outputs
        scan["file_contents"] = file_contents
        scan["tech_stack"] = {
            "languages": analysis.tech_stack.languages,
            "frameworks": analysis.tech_stack.frameworks,
            "databases": analysis.tech_stack.databases,
            "tools": analysis.tech_stack.tools,
            "testing_tools": analysis.tech_stack.testing_tools,
        }
        scan["redaction_count"] = len(analysis.redaction_findings)
        scan["files_scanned"] = analysis.scan_metadata.files_scanned if analysis.scan_metadata else 0
        scan["preview_truncated"] = previews_truncated

    except ValueError as e:
        scan["status"] = "failed"
        scan["error"] = str(e)
        scan["completed_at"] = datetime.now(timezone.utc).isoformat()
        progress(f"✗ Analysis failed: {e}")
    except Exception as e:
        scan["status"] = "failed"
        scan["error"] = "Analysis failed. Check server logs for details."
        scan["completed_at"] = datetime.now(timezone.utc).isoformat()
        progress(f"✗ Analysis failed: {e}")


def _fallback_html() -> str:
    """Minimal fallback HTML if static/index.html is missing."""
    return """<!DOCTYPE html>
<html><head><title>Local Project Prompt Generator</title></head>
<body>
<h1>Local Project Prompt Generator</h1>
<p>Static files not found. Please ensure the static/ directory is present.</p>
<p>API is available at <a href="/api/health">/api/health</a></p>
</body></html>"""


def start_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    """Start the uvicorn server."""
    if not WEB_AVAILABLE:
        raise ImportError(
            "FastAPI and uvicorn are required. Install with: pip install fastapi uvicorn"
        )
    app = create_app(host=host, port=port)
    uvicorn.run(app, host=host, port=port, log_level="info")
