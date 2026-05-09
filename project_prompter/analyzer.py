"""Main analysis orchestrator — ties all phases together."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from .detectors import detect_tech_stack
from .exporters import export_all
from .mode_config import evidence_level_for_mode
from .models import (
    ProjectAnalysis,
    ScanMetadata,
    ScanOptions,
    ScannedFile,
    TechStack,
)
from .prioritizer import prioritize_files
from .prompt_builder import build_prompts
from .scanner import build_file_tree, scan_project
from .domain_classifier import detect_domain
from .summarizer import run_summarization


def analyze_project(
    options: ScanOptions,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> ProjectAnalysis:
    """
    Run a full project analysis and export all outputs.

    Args:
        options: Scan configuration.
        progress_callback: Optional callable for progress messages.

    Returns:
        The completed ProjectAnalysis.
    """

    def log(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    start_time = time.time()
    scan_id = str(uuid.uuid4())[:8]
    scanned_at = datetime.now(timezone.utc).isoformat()

    project_root = Path(options.project_path).resolve()

    if not project_root.exists():
        raise ValueError(f"Project path does not exist: {project_root}")
    if not project_root.is_dir():
        raise ValueError(f"Project path is not a directory: {project_root}")

    log(f"Scanning project: {project_root}")
    log(f"  Mode: {options.mode} | Ollama: {'enabled' if options.use_ollama else 'disabled'}")

    # Phase 1: Build file tree
    log("  Building file tree...")
    file_tree = build_file_tree(
        project_root,
        extra_ignore_dirs=options.extra_ignore_dirs,
    )

    # Phase 2: Scan files
    log("  Scanning files...")
    all_files, redaction_findings = scan_project(
        project_root,
        max_files=options.max_files * 3,  # scan more, prioritize later
        max_chars_per_file=options.max_chars_per_file,
        extra_ignore_dirs=options.extra_ignore_dirs,
    )

    total_found = len(all_files)
    skipped = [f for f in all_files if f.skipped_reason]
    scannable = [f for f in all_files if not f.skipped_reason]

    log(f"  Found {total_found} files, {len(scannable)} scannable, {len(skipped)} skipped")

    # Phase 3: Detect tech stack
    log("  Detecting technology stack...")
    tech_stack = detect_tech_stack(project_root, all_files)
    log(f"  Stack: {', '.join(tech_stack.all_detected()) or 'Unknown'}")

    # Phase 4: Prioritize files
    log("  Prioritizing files...")
    important_files = prioritize_files(scannable, options.max_files)
    log(f"  Selected {len(important_files)} important files for analysis")

    # Phase 5: Generate risk notes
    risk_notes = _generate_risk_notes(
        tech_stack,
        redaction_findings,
        important_files,
        all_files,
    )

    # Phase 6: Summarize. Dry-run stops before cache, Ollama, prompt, or export writes.
    if options.dry_run:
        log("  Dry run enabled. Skipping summarization, prompt generation, and export.")
        file_summaries = {}
        module_summaries = {}
        project_summary = _dry_run_project_summary(tech_stack, options.mode)
        ollama_used = False
        ollama_error = None
    else:
        log("  Running summarization...")
        file_summaries, module_summaries, project_summary, ollama_used, ollama_error = run_summarization(
            important_files=important_files,
            tech_stack=tech_stack,
            file_tree=file_tree,
            model=options.model,
            ollama_url=options.ollama_url,
            use_ollama=options.use_ollama,
            options=options,
            progress_callback=progress_callback,
        )

        # Handle strict Ollama: if --strict-ollama and Ollama failed, raise error
        if options.strict_ollama and options.use_ollama and not ollama_used and ollama_error:
            raise ValueError(
                f"Strict Ollama mode: Ollama is unavailable.\n{ollama_error}\n"
                "Remove --strict-ollama to continue with static analysis only."
            )

    duration = time.time() - start_time

    # 1. Structural summaries
    structural_summaries = {k: v for k, v in file_summaries.items()}
    
    # 2. Markdown contents
    markdown_contents = {}
    for f in all_files:
        if f.extension == ".md" and f.content_preview:
            # Sadece doc dosyaları veya çok bilinenler: README, CLAUDE, vd.
            markdown_contents[f.relative_path] = f.content_preview
            
    # 3. Dependencies
    # TechStack objesinden isimleri düz liste olarak alabiliriz:
    dependencies = tech_stack.all_detected()

    # Detect project domain using the new classifier
    domain_result = detect_domain(
        project_path_str=str(project_root),
        file_paths=[f.relative_path for f in all_files],
        structural_summaries=structural_summaries,
        dependencies=dependencies,
        markdown_contents=markdown_contents
    )

    # Evidence level
    ev_level = evidence_level_for_mode(options.mode, ollama_used)

    # Build metadata
    meta = ScanMetadata(
        scan_id=scan_id,
        scanned_at=scanned_at,
        project_path=str(project_root),
        total_files_found=total_found,
        files_scanned=len(scannable),
        files_skipped=len(skipped),
        files_redacted=len(set(f.file_path for f in redaction_findings)),
        ollama_used=ollama_used,
        ollama_model=options.model,
        ollama_available=ollama_used,
        ollama_error=ollama_error,
        target_model=options.target_model,
        duration_seconds=duration,
        mode=options.mode,
        evidence_level=ev_level,
        domain_result=domain_result,
    )

    assumptions = _build_assumptions(options, ollama_used, ollama_error)

    # Tracking logic for special domain
    # handled later by prompt builder, but we can add risk notes early if we want.
    # We will let prompt generation handle it. But we shouldn't add the generic trading text here anymore,
    # except maybe a generic risk note. Actually, the user asked to remove the old risk note and handle via Domain Result.

    # .env.example skip note (for security report clarity)
    env_example_skipped = any(
        f.skipped_reason == "env_file" and ".env.example" in f.relative_path
        for f in all_files
    )
    if env_example_skipped:
        risk_notes.append(
            "INFO: .env.example was skipped for safety. "
            "Environment templates are not read to prevent accidental secret exposure."
        )

    analysis = ProjectAnalysis(
        project_path=str(project_root),
        file_tree=file_tree,
        tech_stack=tech_stack,
        important_files=important_files,
        file_summaries=file_summaries,
        module_summaries=module_summaries,
        risk_notes=risk_notes,
        assumptions=assumptions,
        redaction_findings=redaction_findings,
        scan_metadata=meta,
        project_summary=project_summary,
        domain_result=domain_result,
        structural_summaries=structural_summaries,
    )

    if options.dry_run:
        _log_dry_run_summary(log, project_root, options, important_files, tech_stack)
        log(f"DRY RUN complete in {duration:.1f}s. No output files were written.")
        return analysis

    # Phase 7: Build prompts
    log(f"  Building prompts for target: {options.target_model}...")
    prompts = build_prompts(analysis, options.target_model)

    # Phase 8: Export
    log(f"  Exporting to: {options.output_path}")
    created_files = export_all(analysis, prompts, options)

    log(f"Analysis complete in {duration:.1f}s")
    log("  Output files:")
    for f in created_files:
        log(f"    {f}")

    return analysis


def _dry_run_project_summary(tech_stack: TechStack, mode: str) -> str:
    """Build a short in-memory summary for dry-run analysis results."""
    tech = _format_detected_tech(tech_stack)
    return (
        f"Dry run completed (mode: {mode}). "
        f"Detected technologies: {tech}. "
        "No summarization, prompt generation, cache writes, or exports were performed."
    )


def _log_dry_run_summary(
    log: Callable[[str], None],
    project_root: Path,
    options: ScanOptions,
    important_files: List[ScannedFile],
    tech_stack: TechStack,
) -> None:
    """Print the dry-run preview expected by the CLI."""
    prompt_count = _target_prompt_count(options.target_model)
    report_count = 6
    estimated_outputs = report_count + prompt_count

    log(f"[DRY RUN] Project: {project_root}")
    log(f"[DRY RUN] Mode: {options.mode} | Target model: {options.target_model}")
    log("[DRY RUN] Files selected for analysis (priority order):")
    if important_files:
        for scanned_file in important_files[:50]:
            log(f"  [{scanned_file.priority_score}] {scanned_file.relative_path}")
        if len(important_files) > 50:
            log(f"  ... {len(important_files) - 50} more file(s)")
    else:
        log("  (none)")
    log(f"[DRY RUN] Detected technologies: {_format_detected_tech(tech_stack)}")
    log(
        f"[DRY RUN] Estimated output files: {estimated_outputs} "
        f"({report_count} reports + {prompt_count} prompt file(s))"
    )
    log("[DRY RUN] Remove --dry-run to write outputs.")


def _target_prompt_count(target_model: str) -> int:
    return 5 if target_model == "all" else 1


def _format_detected_tech(tech_stack: TechStack) -> str:
    return ", ".join(tech_stack.all_detected()) or "Unknown"


def _generate_risk_notes(
    tech_stack: TechStack,
    redaction_findings: list,
    important_files: List[ScannedFile],
    all_files: List[ScannedFile],
) -> List[str]:
    """Generate risk notes based on static analysis."""
    notes = []

    if redaction_findings:
        count = len(redaction_findings)
        files = list(set(f.file_path for f in redaction_findings))
        notes.append(
            f"WARNING: {count} secret pattern(s) detected and redacted in {len(files)} file(s): "
            f"{', '.join(files[:5])}{'...' if len(files) > 5 else ''}"
        )

    # Check for .env.example (good practice)
    env_example = any(
        f.relative_path == ".env.example" or f.relative_path.endswith("/.env.example")
        for f in all_files
    )
    if not env_example and tech_stack.frameworks:
        notes.append("No .env.example file detected — consider adding one to document required environment variables.")

    # Check for test files
    has_tests = any(
        ".test." in f.relative_path or ".spec." in f.relative_path or "/test" in f.relative_path
        for f in all_files
    )
    if not has_tests and not tech_stack.testing_tools:
        notes.append("No test files or testing tools detected — consider adding a test suite.")

    # Check for Docker
    if "Docker" not in tech_stack.tools:
        notes.append("No Docker configuration detected — containerization may improve deployment consistency.")

    # Check for auth files
    has_auth = any(
        "auth" in f.relative_path.lower() or "security" in f.relative_path.lower()
        for f in all_files
    )
    if not has_auth and tech_stack.frameworks:
        notes.append("No explicit authentication/authorization files detected — verify auth implementation.")

    # Redacted files warning
    redacted_files = [f for f in important_files if f.redacted]
    if redacted_files:
        notes.append(
            f"{len(redacted_files)} source file(s) contained secrets that were redacted before analysis. "
            "Review these files and move secrets to environment variables."
        )

    return notes


def _build_assumptions(
    options: ScanOptions,
    ollama_used: bool,
    ollama_error: Optional[str],
) -> List[str]:
    """Build a list of assumptions for the analysis."""
    assumptions = [
        "File tree and file summaries represent a snapshot at scan time.",
        "Technology detection is based on config files and dependency manifests — not runtime behavior.",
        "Priority scoring is heuristic-based and may not perfectly reflect actual importance.",
        "Secret redaction uses pattern matching — some secrets may not be detected.",
    ]

    if not ollama_used:
        if ollama_error:
            assumptions.append(
                f"Ollama summarization was unavailable ({ollama_error}). "
                "File summaries are based on static analysis only."
            )
        else:
            assumptions.append(
                "Ollama summarization was disabled. File summaries are based on static analysis only."
            )
    else:
        assumptions.append(
            f"File summaries were generated by Ollama model '{options.model}' and may contain inaccuracies."
        )

    if options.max_files < 120:
        assumptions.append(
            f"File limit was set to {options.max_files} — some files may not be included in the analysis."
        )

    return assumptions
