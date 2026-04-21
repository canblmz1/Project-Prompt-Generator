"""Prompt builder — dispatches to model-specific templates."""

from __future__ import annotations

from typing import Dict, List

from .models import ProjectAnalysis
from .prompt_templates.chatgpt import build_chatgpt_prompt
from .prompt_templates.claude import build_claude_prompt
from .prompt_templates.gemini import build_gemini_prompt
from .prompt_templates.minimax import build_minimax_prompt
from .prompt_templates.generic import build_generic_prompt

ALL_MODELS: List[str] = ["chatgpt", "claude", "gemini", "minimax", "generic"]

BUILDERS = {
    "chatgpt": build_chatgpt_prompt,
    "claude": build_claude_prompt,
    "gemini": build_gemini_prompt,
    "minimax": build_minimax_prompt,
    "generic": build_generic_prompt,
}


def build_prompts(analysis: ProjectAnalysis, target_model: str) -> Dict[str, str]:
    """
    Build prompts for the specified target model(s).

    Args:
        analysis: The normalized project analysis.
        target_model: One of chatgpt|claude|gemini|minimax|generic|all

    Returns:
        Dict mapping model name to prompt string.
    """
    target = target_model.lower().strip()

    if target == "all":
        models = ALL_MODELS
    elif target in BUILDERS:
        models = [target]
    else:
        raise ValueError(
            f"Unknown target model: '{target}'. "
            f"Valid options: {', '.join(ALL_MODELS + ['all'])}"
        )

    return {model: BUILDERS[model](analysis) for model in models}
