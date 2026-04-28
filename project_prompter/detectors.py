"""Technology stack detection from project files, dependencies, imports, and docs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .models import TechStack, ScannedFile


# ---------------------------------------------------------------------------
# Common dependency groups
# ---------------------------------------------------------------------------

DATA_SCIENCE_DEPS: Dict[str, str] = {
    "jupyter": "Jupyter",
    "notebook": "Jupyter",
    "ipykernel": "Jupyter",
    "pandas": "pandas",
    "numpy": "numpy",
    "scikit-learn": "scikit-learn",
    "sklearn": "sklearn",
    "tensorflow": "TensorFlow",
    "torch": "PyTorch",
    "pytorch": "PyTorch",
    "keras": "Keras",
    "mlflow": "MLflow",
    "wandb": "wandb",
    "huggingface-hub": "huggingface",
    "transformers": "Transformers",
    "matplotlib": "Matplotlib",
    "seaborn": "Seaborn",
    "plotly": "Plotly",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """Safely read and parse a JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None

def _read_text(path: Path) -> str:
    """Safely read a text file."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def _file_exists(root: Path, *parts: str) -> bool:
    return (root / Path(*parts)).exists()

def _any_file_exists(root: Path, names: List[str]) -> bool:
    return any(_file_exists(root, n) for n in names)

def _glob_exists(root: Path, pattern: str) -> bool:
    return any(True for _ in root.rglob(pattern))


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

def detect_tech_stack(project_root: Path, all_files: List[ScannedFile]) -> TechStack:
    """
    Detect the technology stack of a project by inspecting config files,
    dependencies, imports, and markdown documentation.
    """
    stack = TechStack()

    _detect_javascript(project_root, stack)
    _detect_python(project_root, stack)
    _detect_php(project_root, stack)
    _detect_java(project_root, stack)
    _detect_csharp(project_root, stack)
    _detect_databases(project_root, stack)
    _detect_docker(project_root, stack)
    
    _detect_from_imports(all_files, stack)
    _detect_from_docs(all_files, stack)

    return stack


# ---------------------------------------------------------------------------
# JavaScript / TypeScript / Node ecosystem
# ---------------------------------------------------------------------------

def _detect_javascript(root: Path, stack: TechStack) -> None:
    pkg_path = root / "package.json"
    if not pkg_path.exists():
        return

    stack.add_item("languages", "JavaScript", "config")
    stack.add_item("package_managers", "npm", "config")

    pkg = _read_json(pkg_path) or {}
    all_deps: Dict[str, str] = {}
    all_deps.update(pkg.get("dependencies", {}))
    all_deps.update(pkg.get("devDependencies", {}))

    dep_names = set(all_deps.keys())

    if "typescript" in dep_names or _file_exists(root, "tsconfig.json"):
        stack.add_item("languages", "TypeScript", "config")

    if "react" in dep_names:
        stack.add_item("frameworks", "React", "config")

    if "next" in dep_names or _any_file_exists(root, ["next.config.js", "next.config.mjs", "next.config.ts"]):
        stack.add_item("frameworks", "Next.js", "config")

    if "vite" in dep_names or _any_file_exists(root, ["vite.config.ts", "vite.config.js", "vite.config.mjs"]):
        stack.add_item("tools", "Vite", "config")

    if "electron" in dep_names or _any_file_exists(root, ["electron.vite.config.ts", "electron.vite.config.js"]):
        stack.add_item("frameworks", "Electron", "config")

    if _file_exists(root, "pnpm-lock.yaml"):
        stack.add_item("package_managers", "pnpm", "config")
    if _file_exists(root, "yarn.lock"):
        stack.add_item("package_managers", "yarn", "config")

    if "jest" in dep_names or _file_exists(root, "jest.config.js") or _file_exists(root, "jest.config.ts"):
        stack.add_item("testing_tools", "Jest", "config")
    if "vitest" in dep_names or _file_exists(root, "vitest.config.ts") or _file_exists(root, "vitest.config.js"):
        stack.add_item("testing_tools", "Vitest", "config")
    if "playwright" in dep_names or "@playwright/test" in dep_names:
        stack.add_item("testing_tools", "Playwright", "config")
    if "cypress" in dep_names:
        stack.add_item("testing_tools", "Cypress", "config")

    if "prisma" in dep_names or "@prisma/client" in dep_names:
        stack.add_item("databases", "Prisma", "config")
    if "sequelize" in dep_names:
        stack.add_item("databases", "Sequelize", "config")
    if "typeorm" in dep_names:
        stack.add_item("databases", "TypeORM", "config")

    stack.add_item("frameworks", "Node.js", "config")


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

def _detect_python(root: Path, stack: TechStack) -> None:
    has_python = (
        _file_exists(root, "requirements.txt")
        or _file_exists(root, "pyproject.toml")
        or _file_exists(root, "Pipfile")
        or _file_exists(root, "setup.py")
        or _file_exists(root, "setup.cfg")
        or _glob_exists(root, "*.py")
    )

    if not has_python:
        return

    stack.add_item("languages", "Python", "config")

    if _file_exists(root, "Pipfile") or _file_exists(root, "Pipfile.lock"):
        stack.add_item("package_managers", "pipenv", "config")
    if _file_exists(root, "pyproject.toml"):
        stack.add_item("package_managers", "pip/poetry", "config")
    elif _file_exists(root, "requirements.txt"):
        stack.add_item("package_managers", "pip", "config")

    reqs = _collect_python_deps(root)

    if "fastapi" in reqs:
        stack.add_item("frameworks", "FastAPI", "config")
    if "django" in reqs or _file_exists(root, "manage.py"):
        stack.add_item("frameworks", "Django", "config")
    if "flask" in reqs:
        stack.add_item("frameworks", "Flask", "config")
    if "celery" in reqs:
        stack.add_item("frameworks", "Celery", "config")

    if "sqlalchemy" in reqs:
        stack.add_item("databases", "SQLAlchemy", "config")
    if "redis" in reqs:
        stack.add_item("databases", "Redis", "config")

    if "pytest" in reqs or _file_exists(root, "pytest.ini") or _file_exists(root, "conftest.py"):
        stack.add_item("testing_tools", "Pytest", "config")

    # Common AI APIs
    if "openai" in reqs:
        stack.add_item("ai_services", "OpenAI", "config")
    if "anthropic" in reqs:
        stack.add_item("ai_services", "Anthropic", "config")
    if "google-generativeai" in reqs:
        stack.add_item("ai_services", "Gemini", "config")
    if "deepgram-sdk" in reqs:
        stack.add_item("ai_services", "Deepgram", "config")

    for dep_name, label in DATA_SCIENCE_DEPS.items():
        if dep_name in reqs:
            stack.add_item("libraries", label, "config")

def _collect_python_deps(root: Path) -> Set[str]:
    deps: Set[str] = set()
    req_path = root / "requirements.txt"
    if req_path.exists():
        for line in _read_text(req_path).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                name = line.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip().lower()
                deps.add(name)

    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists():
        content = _read_text(pyproject_path).lower()
        known_pkgs = [
            "fastapi", "django", "flask", "sqlalchemy", "pytest", "uvicorn",
            "pydantic", "celery", "redis", "openai", "deepgram", "anthropic",
            *DATA_SCIENCE_DEPS.keys(),
        ]
        for pkg in known_pkgs:
            if pkg in content:
                deps.add(pkg)

    pipfile_path = root / "Pipfile"
    if pipfile_path.exists():
        content = _read_text(pipfile_path).lower()
        known_pkgs = [
            "fastapi", "django", "flask", "sqlalchemy", "pytest", "uvicorn",
            "pydantic", "celery", "redis", "openai", "deepgram", "anthropic",
            *DATA_SCIENCE_DEPS.keys(),
        ]
        for pkg in known_pkgs:
            if pkg in content:
                deps.add(pkg)

    return deps


# ---------------------------------------------------------------------------
# PHP / Laravel
# ---------------------------------------------------------------------------

def _detect_php(root: Path, stack: TechStack) -> None:
    has_php = _file_exists(root, "composer.json") or _glob_exists(root, "*.php")
    if not has_php:
        return

    stack.add_item("languages", "PHP", "config")

    if _file_exists(root, "composer.json"):
        stack.add_item("package_managers", "Composer", "config")
        composer = _read_json(root / "composer.json") or {}
        all_deps: Dict[str, str] = {}
        all_deps.update(composer.get("require", {}))
        all_deps.update(composer.get("require-dev", {}))
        dep_names = set(all_deps.keys())

        if "laravel/framework" in dep_names or _file_exists(root, "artisan"):
            stack.add_item("frameworks", "Laravel", "config")


# ---------------------------------------------------------------------------
# Java / Spring Boot / Maven / Gradle
# ---------------------------------------------------------------------------

def _detect_java(root: Path, stack: TechStack) -> None:
    has_java = (
        _file_exists(root, "pom.xml")
        or _file_exists(root, "build.gradle")
        or _file_exists(root, "build.gradle.kts")
        or _glob_exists(root, "*.java")
    )
    if not has_java:
        return

    stack.add_item("languages", "Java", "config")

    if _file_exists(root, "pom.xml"):
        stack.add_item("tools", "Maven", "config")
        pom_content = _read_text(root / "pom.xml").lower()
        if "spring-boot" in pom_content or "spring-boot-starter" in pom_content:
            stack.add_item("frameworks", "Spring Boot", "config")

    if _file_exists(root, "build.gradle") or _file_exists(root, "build.gradle.kts"):
        stack.add_item("tools", "Gradle", "config")
        gradle_content = ""
        if _file_exists(root, "build.gradle"):
            gradle_content = _read_text(root / "build.gradle").lower()
        elif _file_exists(root, "build.gradle.kts"):
            gradle_content = _read_text(root / "build.gradle.kts").lower()
        if "spring-boot" in gradle_content:
            stack.add_item("frameworks", "Spring Boot", "config")


# ---------------------------------------------------------------------------
# C# / .NET
# ---------------------------------------------------------------------------

def _detect_csharp(root: Path, stack: TechStack) -> None:
    has_csharp = _glob_exists(root, "*.csproj") or _glob_exists(root, "*.cs")
    if not has_csharp:
        return

    stack.add_item("languages", "C#", "config")
    stack.add_item("frameworks", ".NET", "config")

    if _file_exists(root, "appsettings.json"):
        stack.add_item("tools", "ASP.NET Core", "config")


# ---------------------------------------------------------------------------
# Databases
# ---------------------------------------------------------------------------

def _detect_databases(root: Path, stack: TechStack) -> None:
    if _file_exists(root, "prisma", "schema.prisma") or _glob_exists(root, "schema.prisma"):
        stack.add_item("databases", "Prisma", "config")
        schema_files = list(root.rglob("schema.prisma"))
        for sf in schema_files:
            content = _read_text(sf).lower()
            if "postgresql" in content or "postgres" in content:
                stack.add_item("databases", "PostgreSQL", "config")
            if "sqlite" in content:
                stack.add_item("databases", "SQLite", "config")

    for dc_name in ["docker-compose.yml", "docker-compose.yaml"]:
        dc_path = root / dc_name
        if dc_path.exists():
            content = _read_text(dc_path).lower()
            if "postgres" in content:
                stack.add_item("databases", "PostgreSQL", "config")
            if "sqlite" in content:
                stack.add_item("databases", "SQLite", "config")
            if "mysql" in content:
                stack.add_item("databases", "MySQL", "config")
            if "redis" in content:
                stack.add_item("databases", "Redis", "config")
            if "mongodb" in content:
                stack.add_item("databases", "MongoDB", "config")


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

def _detect_docker(root: Path, stack: TechStack) -> None:
    if _file_exists(root, "Dockerfile") or _file_exists(root, "docker-compose.yml") or _file_exists(root, "docker-compose.yaml"):
        stack.add_item("tools", "Docker", "config")


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

def _detect_from_imports(all_files: List[ScannedFile], stack: TechStack) -> None:
    for f in all_files:
        if not f.content_preview:
            continue
        
        c_lower = f.content_preview.lower()
        if f.extension == ".py":
            if "import fastapi" in c_lower or "from fastapi" in c_lower:
                stack.add_item("frameworks", "FastAPI", "imports")
            if "import celery" in c_lower or "from celery" in c_lower:
                stack.add_item("frameworks", "Celery", "imports")
            if "import redis" in c_lower:
                stack.add_item("databases", "Redis", "imports")
            if "from anthropic" in c_lower or "import anthropic" in c_lower:
                stack.add_item("ai_services", "Anthropic", "imports")
            if "from openai" in c_lower or "import openai" in c_lower:
                stack.add_item("ai_services", "OpenAI", "imports")
            if "import google.generativeai" in c_lower or "gemini" in c_lower:
                if "gemini" in c_lower and ("google" in c_lower or "ai" in c_lower):
                    stack.add_item("ai_services", "Gemini", "imports")
            if "deepgram" in c_lower:
                stack.add_item("ai_services", "Deepgram", "imports")
            if "import pandas" in c_lower or "from pandas" in c_lower:
                stack.add_item("libraries", "pandas", "imports")
            if "import numpy" in c_lower or "from numpy" in c_lower:
                stack.add_item("libraries", "numpy", "imports")
            if "import sklearn" in c_lower or "from sklearn" in c_lower:
                stack.add_item("libraries", "sklearn", "imports")
            if "import torch" in c_lower or "from torch" in c_lower:
                stack.add_item("libraries", "PyTorch", "imports")
            if "import tensorflow" in c_lower or "from tensorflow" in c_lower:
                stack.add_item("libraries", "TensorFlow", "imports")
            if "import keras" in c_lower or "from keras" in c_lower:
                stack.add_item("libraries", "Keras", "imports")
            if "import matplotlib" in c_lower or "from matplotlib" in c_lower:
                stack.add_item("libraries", "Matplotlib", "imports")
            if "import seaborn" in c_lower or "from seaborn" in c_lower:
                stack.add_item("libraries", "Seaborn", "imports")


# ---------------------------------------------------------------------------
# Documented Stack
# ---------------------------------------------------------------------------

def _detect_from_docs(all_files: List[ScannedFile], stack: TechStack) -> None:
    doc_files = ["readme.md", "claude.md", "project_analysis.md", "tech.md"]
    for f in all_files:
        name = f.path.name.lower()
        if name in doc_files and f.content_preview:
            c = f.content_preview.lower()
            
            if "fastapi" in c:
                stack.add_item("frameworks", "FastAPI", "docs")
            if "celery" in c:
                stack.add_item("frameworks", "Celery", "docs")
            if "postgresql" in c or "postgres" in c:
                stack.add_item("databases", "PostgreSQL", "docs")
            if "redis" in c:
                stack.add_item("databases", "Redis", "docs")
            if "deepgram" in c:
                stack.add_item("ai_services", "Deepgram", "docs")
            if "gemini" in c:
                stack.add_item("ai_services", "Gemini", "docs")
            if "openrouter" in c:
                stack.add_item("ai_services", "OpenRouter", "docs")
            if "openai" in c:
                stack.add_item("ai_services", "OpenAI", "docs")
            if "anthropic" in c or "claude" in c:
                stack.add_item("ai_services", "Anthropic", "docs")
