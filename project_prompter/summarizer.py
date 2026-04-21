"""Summarization orchestrator — structural analysis first, optional Ollama on top."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .cache_manager import load_cached, save_cached
from .models import ScannedFile, ScanOptions, TechStack
from .ollama_client import (
    check_model_exists,
    check_ollama_available,
    summarize_file,
    summarize_project,
)
from .structural_analyzer import (
    LARGE_FILE_WARN_KB,
    build_structural_summary,
    large_file_risk_note,
)

# Files matching these patterns are skipped for Ollama (not worth the cost)
_OLLAMA_SKIP_PATTERNS = (
    ".test.", ".spec.", "_test.", "_spec.",
    "test_", "__test__",
    ".min.", ".generated.",
    "migration", "seed",
)


def run_summarization(
    important_files: List[ScannedFile],
    tech_stack: TechStack,
    file_tree: str,
    model: str,
    ollama_url: str,
    use_ollama: bool,
    options: Optional[ScanOptions] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[Dict[str, str], Dict[str, str], str, bool, Optional[str]]:
    """
    Orchestrate structural + optional Ollama summarization.

    Returns:
        (file_summaries, module_summaries, project_summary, ollama_used, ollama_error)
    """

    def log(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    project_root = Path(options.project_path) if options else None
    mode = options.mode if options else "fast"
    use_cache = options.use_cache if options else True
    ollama_max_files = options.ollama_max_files if options else 10

    structural_summaries: Dict[str, str] = {}
    file_summaries: Dict[str, str] = {}
    module_summaries: Dict[str, str] = {}
    project_summary = ""
    ollama_used = False
    ollama_error: Optional[str] = None
    large_file_risks: List[str] = []

    # -----------------------------------------------------------------------
    # Phase 1: Structural summaries for all important files (always runs)
    # -----------------------------------------------------------------------
    log(f"  Building structural summaries ({len(important_files)} files)...")

    for scanned_file in important_files:
        if not scanned_file.content_preview:
            continue

        # Try cache first
        cached = None
        if use_cache and project_root:
            cached = load_cached(project_root, scanned_file.path, mode)

        if cached and "structural_summary" in cached:
            structural_summaries[scanned_file.relative_path] = cached["structural_summary"]
        else:
            summary = build_structural_summary(
                file_path=scanned_file.path,
                relative_path=scanned_file.relative_path,
                content=scanned_file.content_preview,
                size=scanned_file.size,
                priority_score=scanned_file.priority_score,
            )
            structural_summaries[scanned_file.relative_path] = summary

            if use_cache and project_root:
                save_cached(project_root, scanned_file.path, mode, {"structural_summary": summary})

        # Large file risk notes
        risk = large_file_risk_note(scanned_file.relative_path, scanned_file.size)
        if risk:
            large_file_risks.append(risk)

    # Use structural summaries as the base file_summaries
    file_summaries = dict(structural_summaries)

    # -----------------------------------------------------------------------
    # Phase 2: Optional Ollama enhancement on critical files only
    # -----------------------------------------------------------------------
    if not use_ollama:
        log("  Ollama disabled. Using structural analysis only.")
    else:
        # Check availability
        available, err = check_ollama_available(ollama_url)
        if not available:
            ollama_error = err or "Ollama not available"
            log(f"  ⚠ Ollama unavailable: {ollama_error}")
            log("  Continuing with structural analysis only.")
        else:
            # Preflight: check model exists
            model_ok, available_models = check_model_exists(model, ollama_url)
            if not model_ok:
                model_list = "\n".join(f"  - {m}" for m in available_models[:10])
                ollama_error = (
                    f"Ollama model not found: {model}\n"
                    f"Available models:\n{model_list or '  (none)'}"
                )
                log(f"  ✗ {ollama_error}")
                log("  Falling back to structural analysis only.")
            else:
                log(f"  ✓ Ollama ready. Model: {model}")
                ollama_used = True

                # Select only top critical files for Ollama — skip test/lock/generated
                critical_files = _select_ollama_files(important_files, ollama_max_files)
                log(f"  Sending {len(critical_files)} critical files to Ollama...")

                for i, scanned_file in enumerate(critical_files):
                    if not scanned_file.content_preview:
                        continue

                    # Check cache for Ollama summary
                    ollama_cache_key = f"{mode}_ollama_{model}"
                    cached = None
                    if use_cache and project_root:
                        cached = load_cached(project_root, scanned_file.path, ollama_cache_key)

                    if cached and "ollama_summary" in cached:
                        log(f"    [cache] {scanned_file.relative_path}")
                        file_summaries[scanned_file.relative_path] = cached["ollama_summary"]
                        continue

                    log(f"    [{i+1}/{len(critical_files)}] {scanned_file.relative_path}")

                    # Send structural summary to Ollama, not raw content
                    content_to_send = structural_summaries.get(
                        scanned_file.relative_path,
                        scanned_file.content_preview[:2000],
                    )

                    summary, err = summarize_file(
                        content_to_send,
                        scanned_file.relative_path,
                        model=model,
                        ollama_url=ollama_url,
                    )
                    if err:
                        log(f"    ⚠ {err}")
                        # Keep structural summary
                    else:
                        enhanced = (
                            structural_summaries.get(scanned_file.relative_path, "") +
                            f"\n\nOllama Analysis:\n{summary}"
                        )
                        file_summaries[scanned_file.relative_path] = enhanced
                        if use_cache and project_root:
                            save_cached(
                                project_root, scanned_file.path, ollama_cache_key,
                                {"ollama_summary": enhanced},
                            )

    # -----------------------------------------------------------------------
    # Phase 3: Module summaries (grouped by top-level dir)
    # -----------------------------------------------------------------------
    module_groups = _group_into_modules(file_summaries)
    for module_name, module_files in module_groups.items():
        file_list = ", ".join(module_files.keys())
        module_summaries[module_name] = f"Module '{module_name}': {file_list}"

    # -----------------------------------------------------------------------
    # Phase 4: Project summary
    # -----------------------------------------------------------------------
    tech_text = _tech_stack_text(tech_stack)

    if ollama_used:
        log("  Generating project summary via Ollama...")
        summary, err = summarize_project(
            module_summaries, tech_text, file_tree,
            model=model, ollama_url=ollama_url,
        )
        project_summary = summary if summary else _static_project_summary(tech_stack, file_tree, mode)
    else:
        project_summary = _static_project_summary(tech_stack, file_tree, mode)

    # Append large file risks to project summary
    if large_file_risks:
        project_summary += "\n\n## Large File Risks\n" + "\n".join(f"- {r}" for r in large_file_risks)

    return file_summaries, module_summaries, project_summary, ollama_used, ollama_error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _select_ollama_files(files: List[ScannedFile], max_count: int) -> List[ScannedFile]:
    """Select only the most critical files for Ollama — skip test/lock/generated."""
    eligible = []
    for f in files:
        rp = f.relative_path.lower()
        # Skip test files, lock files, generated, large files
        if any(pat in rp for pat in _OLLAMA_SKIP_PATTERNS):
            continue
        if f.size > LARGE_FILE_WARN_KB * 1024:
            continue  # too large — structural summary is enough
        if f.skipped_reason:
            continue
        eligible.append(f)

    # Sort by priority descending, take top N
    eligible.sort(key=lambda x: x.priority_score, reverse=True)
    return eligible[:max_count]


def _static_project_summary(tech_stack: TechStack, file_tree: str, mode: str) -> str:
    tech = _tech_stack_text(tech_stack)
    return (
        f"Static analysis completed (mode: {mode}, Ollama: disabled). "
        f"Detected technologies: {tech}. "
        f"Structural summaries were generated for all important files. "
        f"Review the file tree and structural summaries for architecture insights."
    )


def _tech_stack_text(tech_stack: TechStack) -> str:
    parts = []
    if tech_stack.languages:
        parts.append(f"Languages: {', '.join(tech_stack.languages)}")
    if tech_stack.frameworks:
        parts.append(f"Frameworks: {', '.join(tech_stack.frameworks)}")
    if tech_stack.databases:
        parts.append(f"Databases: {', '.join(tech_stack.databases)}")
    if tech_stack.tools:
        parts.append(f"Tools: {', '.join(tech_stack.tools)}")
    if tech_stack.testing_tools:
        parts.append(f"Testing: {', '.join(tech_stack.testing_tools)}")
    return "; ".join(parts) if parts else "Unknown"


def _group_into_modules(file_summaries: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    groups: Dict[str, Dict[str, str]] = {}
    for path, summary in file_summaries.items():
        parts = path.replace("\\", "/").split("/")
        module = parts[0] if len(parts) > 1 else "root"
        if module not in groups:
            groups[module] = {}
        groups[module][path] = summary
    return groups
