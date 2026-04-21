"""CLI entry point for the Local Project Prompt Generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .mode_config import MODE_DEFAULTS, MODE_DESCRIPTIONS, VALID_MODES
from .models import ScanOptions


def create_parser() -> argparse.ArgumentParser:
    mode_help_lines = "\n".join(
        f"    {m}: {MODE_DESCRIPTIONS[m]}" for m in VALID_MODES
    )

    parser = argparse.ArgumentParser(
        prog="project-prompter",
        description=(
            "Local Project Prompt Generator — "
            "Scan a local project and generate optimized AI prompts. "
            "No code is uploaded to any cloud service."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Modes:
{mode_help_lines}

Examples:
  project-prompter ./my-project
  project-prompter ./my-project --mode fast --target-model all
  project-prompter ./my-project --mode balanced --use-ollama --model qwen2.5-coder:1.5b
  project-prompter ./my-project --mode deep --use-ollama --model qwen2.5-coder:3b
  project-prompter ./my-project --no-ollama --target-model all
  project-prompter --ui
  project-prompter --ui --host 0.0.0.0 --port 8787
  project-prompter --clear-cache-only ./my-project

Security note:
  This tool never uploads project files to any external service.
  It only communicates with a local Ollama instance (if enabled).
  Generated prompts must be manually copied to cloud AI services.
        """,
    )

    parser.add_argument(
        "project_path",
        nargs="?",
        help="Path to the local project directory to scan.",
    )

    parser.add_argument(
        "--output",
        default="./output",
        metavar="PATH",
        help="Output directory for generated files (default: ./output)",
    )

    # -----------------------------------------------------------------------
    # Mode system
    # -----------------------------------------------------------------------
    parser.add_argument(
        "--mode",
        default="fast",
        choices=list(VALID_MODES),
        help="Analysis mode: fast|balanced|deep (default: fast)",
    )

    # -----------------------------------------------------------------------
    # Ollama flags
    # -----------------------------------------------------------------------
    parser.add_argument(
        "--model",
        default="qwen2.5-coder:1.5b",
        metavar="MODEL",
        help="Ollama model to use for summarization (default: qwen2.5-coder:1.5b)",
    )

    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        metavar="URL",
        help="Ollama API base URL (default: http://localhost:11434)",
    )

    parser.add_argument(
        "--use-ollama",
        action="store_true",
        default=False,
        help="Enable Ollama summarization for critical files.",
    )

    parser.add_argument(
        "--no-ollama",
        action="store_true",
        default=False,
        help="Disable Ollama summarization (default behavior).",
    )

    parser.add_argument(
        "--strict-ollama",
        action="store_true",
        default=False,
        help="Fail if Ollama is unavailable when --use-ollama is set.",
    )

    # -----------------------------------------------------------------------
    # Limits (explicit values override mode defaults)
    # -----------------------------------------------------------------------
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of files to include (default: set by mode)",
    )

    parser.add_argument(
        "--max-chars-per-file",
        type=int,
        default=None,
        metavar="N",
        help="Maximum characters to read per file (default: set by mode)",
    )

    # -----------------------------------------------------------------------
    # Cache flags
    # -----------------------------------------------------------------------
    parser.add_argument(
        "--use-cache",
        action="store_true",
        default=False,
        help="Enable cache (default behavior for all modes).",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable cache — re-analyze all files.",
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        default=False,
        help="Clear cache before analysis, then continue.",
    )

    parser.add_argument(
        "--clear-cache-only",
        action="store_true",
        default=False,
        help="Clear cache and exit without running analysis.",
    )

    # -----------------------------------------------------------------------
    # Output / target
    # -----------------------------------------------------------------------
    parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown"],
        help="Output format (default: markdown)",
    )

    parser.add_argument(
        "--target-model",
        default="all",
        choices=["chatgpt", "claude", "gemini", "minimax", "generic", "all"],
        metavar="MODEL",
        help="Target AI model for prompt generation: chatgpt|claude|gemini|minimax|generic|all (default: all)",
    )

    # -----------------------------------------------------------------------
    # Web UI
    # -----------------------------------------------------------------------
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Start the local web UI instead of running a CLI scan.",
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help="Host for the web UI server (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        metavar="PORT",
        help="Port for the web UI server (default: 8787)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def _validate_flags(args: argparse.Namespace) -> str | None:
    """Validate mutually exclusive flags. Returns error message or None."""
    if args.use_ollama and args.no_ollama:
        return "Conflicting flags: --use-ollama and --no-ollama cannot be used together."
    if args.use_cache and args.no_cache:
        return "Conflicting flags: --use-cache and --no-cache cannot be used together."
    return None


def _resolve_options(args: argparse.Namespace) -> ScanOptions:
    """Resolve CLI args into ScanOptions, applying mode defaults for unset values."""
    mode = args.mode
    defaults = MODE_DEFAULTS[mode]

    # Ollama resolution:
    #   --use-ollama → True
    #   --no-ollama  → False
    #   neither      → mode default (always False, but explicit for clarity)
    if args.use_ollama:
        use_ollama = True
    elif args.no_ollama:
        use_ollama = False
    else:
        use_ollama = defaults["use_ollama"]

    # Fast mode: Ollama is NEVER used, even if --use-ollama was combined with --mode fast
    if mode == "fast":
        use_ollama = False

    # Cache resolution
    if args.no_cache:
        use_cache = False
    elif args.use_cache:
        use_cache = True
    else:
        use_cache = defaults["use_cache"]

    # Limits: explicit CLI values override mode defaults
    max_files = args.max_files if args.max_files is not None else defaults["max_files"]
    max_chars = args.max_chars_per_file if args.max_chars_per_file is not None else defaults["max_chars_per_file"]

    return ScanOptions(
        project_path=Path(args.project_path),
        output_path=Path(args.output),
        model=args.model,
        ollama_url=args.ollama_url,
        max_files=max_files,
        max_chars_per_file=max_chars,
        use_ollama=use_ollama,
        target_model=args.target_model,
        format=args.format,
        mode=mode,
        use_cache=use_cache,
        clear_cache=args.clear_cache,
        ollama_max_files=defaults["ollama_max_files"],
        strict_ollama=args.strict_ollama,
    )


def main() -> int:
    """Main CLI entry point. Returns exit code."""
    parser = create_parser()
    args = parser.parse_args()

    # --ui mode
    if args.ui:
        return _start_ui(args)

    # --clear-cache-only mode
    if args.clear_cache_only:
        return _clear_cache_only(args)

    # CLI scan mode
    if not args.project_path:
        parser.print_help()
        print("\nError: project_path is required unless --ui is specified.", file=sys.stderr)
        return 1

    # Validate conflicting flags
    error = _validate_flags(args)
    if error:
        print(f"\nError: {error}", file=sys.stderr)
        return 1

    return _run_scan(args)


def _run_scan(args: argparse.Namespace) -> int:
    """Run a CLI project scan."""
    from .analyzer import analyze_project

    project_path = Path(args.project_path)

    if not project_path.exists():
        print(f"Error: Project path does not exist: {project_path}", file=sys.stderr)
        return 1

    if not project_path.is_dir():
        print(f"Error: Project path is not a directory: {project_path}", file=sys.stderr)
        return 1

    options = _resolve_options(args)

    # Clear cache before analysis if requested
    if options.clear_cache:
        from .cache_manager import clear_cache
        count = clear_cache(project_path.resolve())
        print(f"Cache cleared: {count} file(s) deleted.")

    print(f"Local Project Prompt Generator v{__version__}")
    print(f"Project: {project_path.resolve()}")
    print(f"Mode: {options.mode}")
    print(f"Target model: {options.target_model}")
    print(f"Ollama: {'disabled' if not options.use_ollama else f'{options.model} @ {options.ollama_url}'}")
    print(f"Max files: {options.max_files} | Max chars/file: {options.max_chars_per_file}")
    print(f"Cache: {'enabled' if options.use_cache else 'disabled'}")
    print()

    if options.mode == "deep":
        print("⚠ Deep mode may take longer on large projects.")
        print()

    try:
        analyze_project(options, progress_callback=print)
        print(f"\n✓ Output written to: {Path(args.output).resolve()}")
        return 0
    except ValueError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 1


def _clear_cache_only(args: argparse.Namespace) -> int:
    """Clear cache and exit without running analysis."""
    from .cache_manager import clear_cache

    if not args.project_path:
        print("Error: project_path is required for --clear-cache-only.", file=sys.stderr)
        return 1

    project_path = Path(args.project_path).resolve()
    if not project_path.exists():
        print(f"Error: Project path does not exist: {project_path}", file=sys.stderr)
        return 1

    count = clear_cache(project_path)
    print(f"Cache cleared: {count} file(s) deleted from {project_path}.")
    return 0


def _start_ui(args: argparse.Namespace) -> int:
    """Start the local web UI."""
    try:
        from .web import start_server
        print(f"Local Project Prompt Generator v{__version__}")
        print(f"Starting web UI at http://{args.host}:{args.port}")
        print("Press Ctrl+C to stop.")
        start_server(host=args.host, port=args.port)
        return 0
    except ImportError as e:
        print(f"Error: Web UI dependencies not available: {e}", file=sys.stderr)
        print("Install with: pip install 'project-prompter[web]'", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nWeb UI stopped.")
        return 0
    except Exception as e:
        print(f"Error starting web UI: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
