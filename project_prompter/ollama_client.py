"""Ollama local API client — optimized, with model preflight check."""

from __future__ import annotations

import json
from typing import List, Optional, Tuple
from urllib import request, error as urllib_error


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3:latest"
REQUEST_TIMEOUT = 90  # seconds — reduced from 120

# Optimized generation options: short, focused, low temperature
OLLAMA_OPTIONS = {
    "temperature": 0.1,
    "num_ctx": 4096,
    "num_predict": 300,
}


def check_ollama_available(ollama_url: str = DEFAULT_OLLAMA_URL) -> Tuple[bool, Optional[str]]:
    """Check if Ollama is running and reachable."""
    try:
        req = request.Request(f"{ollama_url.rstrip('/')}/api/tags", method="GET")
        with request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, None
            return False, f"Ollama returned HTTP {resp.status}"
    except urllib_error.URLError as e:
        return False, f"Ollama not reachable at {ollama_url}: {e.reason}"
    except Exception as e:
        return False, f"Ollama check failed: {e}"


def list_ollama_models(ollama_url: str = DEFAULT_OLLAMA_URL) -> List[str]:
    """List available Ollama models. Returns empty list on failure."""
    try:
        req = request.Request(f"{ollama_url.rstrip('/')}/api/tags", method="GET")
        with request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            return [m.get("name", "") for m in models if m.get("name")]
    except Exception:
        return []


def check_model_exists(
    model: str,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> Tuple[bool, List[str]]:
    """
    Check if a specific model is available in Ollama.

    Returns:
        (model_exists, available_models_list)
    """
    available = list_ollama_models(ollama_url)
    # Exact match or prefix match (e.g. "llama3" matches "llama3:latest")
    exists = any(
        m == model or m.startswith(model.split(":")[0] + ":")
        for m in available
    )
    return exists, available


def summarize_file(
    content: str,
    file_path: str,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> Tuple[Optional[str], Optional[str]]:
    """Ask Ollama to summarize a single file. Short prompt, short response."""
    # Keep prompt compact — structural summary already extracted the skeleton
    prompt = (
        f"Summarize this source file in 2-3 sentences. "
        f"Focus on: purpose, key responsibilities, notable risks.\n\n"
        f"File: {file_path}\n\n"
        f"```\n{content[:2000]}\n```\n\nSummary:"
    )
    return _generate(prompt, model, ollama_url)


def summarize_project(
    module_summaries: dict[str, str],
    tech_stack_text: str,
    file_tree: str,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> Tuple[Optional[str], Optional[str]]:
    """Ask Ollama for a compact project-level summary."""
    modules_text = "\n".join(
        f"- {name}: {summary[:200]}" for name, summary in list(module_summaries.items())[:8]
    )
    prompt = (
        f"Write a 3-5 sentence project summary based on:\n"
        f"Stack: {tech_stack_text}\n"
        f"Modules: {modules_text}\n"
        f"Project Summary:"
    )
    return _generate(prompt, model, ollama_url)


def _generate(
    prompt: str,
    model: str,
    ollama_url: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Call Ollama /api/generate with optimized options."""
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",
            "options": OLLAMA_OPTIONS,
        }
    ).encode("utf-8")

    try:
        req = request.Request(
            f"{ollama_url.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            response_text = data.get("response", "").strip()
            if not response_text:
                return None, "Ollama returned empty response"
            return response_text, None
    except urllib_error.URLError as e:
        return None, f"Ollama request failed: {e.reason}"
    except Exception as e:
        return None, f"Ollama error: {e}"
