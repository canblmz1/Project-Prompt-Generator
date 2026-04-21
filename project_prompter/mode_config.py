"""Analysis mode configuration — centralized defaults for fast/balanced/deep."""

from __future__ import annotations

from typing import Any, Dict


# ---------------------------------------------------------------------------
# Mode defaults
# ---------------------------------------------------------------------------
# These apply ONLY when the user did not explicitly provide a value.
# Explicit CLI / API values always take precedence.

MODE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "fast": {
        "max_files": 40,
        "max_chars_per_file": 3000,
        "ollama_max_files": 0,       # Ollama never used in fast mode
        "use_cache": True,
        "use_ollama": False,         # Ollama disabled
    },
    "balanced": {
        "max_files": 50,
        "max_chars_per_file": 4000,
        "ollama_max_files": 10,
        "use_cache": True,
        "use_ollama": False,         # Off unless --use-ollama given
    },
    "deep": {
        "max_files": 80,
        "max_chars_per_file": 6000,
        "ollama_max_files": 20,
        "use_cache": True,
        "use_ollama": False,         # Off unless --use-ollama given
    },
}

VALID_MODES = tuple(MODE_DEFAULTS.keys())

# Mode descriptions (for CLI help and UI)
MODE_DESCRIPTIONS: Dict[str, str] = {
    "fast": "Fastest. No Ollama. Uses static and structural analysis only.",
    "balanced": "Good default for most projects. Uses structural summaries and optional Ollama for top critical files.",
    "deep": "More detailed but slower. Uses Ollama on selected critical files when enabled.",
}


def get_mode_defaults(mode: str) -> Dict[str, Any]:
    """Return the defaults for a given mode. Raises ValueError for unknown modes."""
    if mode not in MODE_DEFAULTS:
        raise ValueError(
            f"Unknown mode: '{mode}'. Valid modes: {', '.join(VALID_MODES)}"
        )
    return dict(MODE_DEFAULTS[mode])


def evidence_level_for_mode(mode: str, ollama_used: bool) -> str:
    """Determine the evidence level label based on mode and Ollama usage."""
    if mode == "deep" and ollama_used:
        return "high"
    if mode == "balanced":
        return "medium"
    return "limited"


def analysis_type_label(mode: str, ollama_used: bool) -> str:
    """Human-readable analysis type label for prompt metadata."""
    if mode == "deep" and ollama_used:
        return "Deep Architecture Review (Static + Ollama)"
    if mode == "balanced" and ollama_used:
        return "Balanced Architecture Review (Static + Ollama)"
    if mode == "balanced":
        return "Balanced Static Architecture Review"
    return "Limited Static Architecture Review"
