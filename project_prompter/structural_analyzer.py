"""Structural summary generator — AST-based for Python, regex for JS/TS."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Risk / trading keywords to flag
# ---------------------------------------------------------------------------

RISK_KEYWORDS = [
    "risk", "budget", "kill_switch", "killswitch", "kill switch",
    "trade", "order", "execution", "reconciliation", "reconcile",
    "secret", "token", "password", "api_key", "private_key",
    "binance", "spot", "futures", "portfolio", "live", "paper",
    "drawdown", "loss", "stop_loss", "take_profit",
]

LARGE_FILE_WARN_KB = 20    # structural summary only above this
LARGE_FILE_RISK_KB = 50    # architecture risk note
LARGE_FILE_CRITICAL_KB = 100  # high priority risk


def build_structural_summary(
    file_path: Path,
    relative_path: str,
    content: str,
    size: int,
    priority_score: int,
) -> str:
    """
    Build a structural summary for a source file.
    Uses AST for Python, regex for JS/TS, plain preview for others.
    """
    ext = file_path.suffix.lower()
    size_kb = size / 1024

    header = (
        f"### {relative_path}\n"
        f"Type: {_file_type_label(ext)}  "
        f"Size: {size_kb:.1f} KB  "
        f"Priority: {priority_score}\n"
    )

    # Large file risk notes
    risk_prefix = ""
    if size_kb >= LARGE_FILE_CRITICAL_KB:
        risk_prefix = (
            f"⚠ HIGH PRIORITY ARCHITECTURE RISK: {relative_path} is {size_kb:.0f} KB. "
            f"This likely violates single-responsibility. "
            f"Recommend splitting into focused modules.\n\n"
        )
    elif size_kb >= LARGE_FILE_RISK_KB:
        risk_prefix = (
            f"⚠ Large File Risk: {relative_path} is {size_kb:.0f} KB. "
            f"May indicate too many responsibilities. "
            f"Recommend splitting orchestration, config, and business logic.\n\n"
        )

    # Parse structure
    if ext == ".py":
        body = _python_structural_summary(content)
    elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        body = _js_structural_summary(content)
    else:
        # Plain preview for other types
        lines = content.splitlines()[:15]
        body = "Preview:\n" + "\n".join(f"  {l}" for l in lines if l.strip())

    return header + risk_prefix + body


def _file_type_label(ext: str) -> str:
    labels = {
        ".py": "Python source",
        ".ts": "TypeScript source",
        ".tsx": "TypeScript/React",
        ".js": "JavaScript source",
        ".jsx": "JavaScript/React",
        ".json": "JSON config",
        ".yml": "YAML config",
        ".yaml": "YAML config",
        ".toml": "TOML config",
        ".prisma": "Prisma schema",
        ".sql": "SQL",
        ".md": "Markdown",
        ".env.example": "Env template",
    }
    return labels.get(ext, f"{ext} file")


# ---------------------------------------------------------------------------
# Python AST parser
# ---------------------------------------------------------------------------

def _python_structural_summary(content: str) -> str:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        lines = content.splitlines()[:10]
        return "Parse error. Preview:\n" + "\n".join(f"  {l}" for l in lines)

    imports: List[str] = []
    classes: List[str] = []
    functions: List[str] = []
    async_functions: List[str] = []
    decorators: List[str] = []
    env_reads: List[str] = []
    risk_areas: List[str] = []

    for node in ast.walk(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)

        # Classes
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

        # Functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = _format_args(node.args)
            sig = f"{node.name}({args})"
            if isinstance(node, ast.AsyncFunctionDef):
                async_functions.append(sig)
            else:
                functions.append(sig)
            # Decorators
            for dec in node.decorator_list:
                dec_name = _decorator_name(dec)
                if dec_name and dec_name not in decorators:
                    decorators.append(dec_name)

        # os.environ / os.getenv calls
        elif isinstance(node, ast.Call):
            call_str = _call_to_str(node)
            if call_str:
                env_reads.append(call_str)

    # Risk keyword scan
    content_lower = content.lower()
    for kw in RISK_KEYWORDS:
        if kw in content_lower:
            risk_areas.append(kw)

    # Side effects heuristics
    side_effects: List[str] = []
    if any(k in content_lower for k in ("open(", "pathlib", "os.path", "shutil")):
        side_effects.append("Filesystem reads/writes")
    if any(k in content_lower for k in ("requests.", "httpx.", "aiohttp.", "urllib")):
        side_effects.append("HTTP/network calls")
    if any(k in content_lower for k in ("redis", "redis.asyncio")):
        side_effects.append("Redis usage")
    if any(k in content_lower for k in ("sqlalchemy", "session.", "db.query", "cursor.")):
        side_effects.append("Database usage")
    if any(k in content_lower for k in ("subprocess", "os.system", "os.popen")):
        side_effects.append("Subprocess execution")
    if any(k in content_lower for k in ("@app.route", "@router.", "fastapi", "flask")):
        side_effects.append("Route definitions")
    if any(k in content_lower for k in ("basemodel", "pydantic", "dataclass", "schema")):
        side_effects.append("Schema/model definitions")

    parts: List[str] = []

    if imports:
        parts.append("Imports:\n" + "\n".join(f"  - {i}" for i in imports[:15]))
    if classes:
        parts.append("Classes:\n" + "\n".join(f"  - {c}" for c in classes))
    if functions:
        parts.append("Functions:\n" + "\n".join(f"  - {f}" for f in functions[:20]))
    if async_functions:
        parts.append("Async Functions:\n" + "\n".join(f"  - {f}" for f in async_functions[:10]))
    if decorators:
        parts.append("Decorators:\n" + "\n".join(f"  - {d}" for d in decorators[:8]))
    if env_reads:
        parts.append("Environment Variables:\n" + "\n".join(f"  - {e}" for e in env_reads[:10]))
    if side_effects:
        parts.append("External / Side Effects:\n" + "\n".join(f"  - {s}" for s in side_effects))
    if risk_areas:
        unique_risks = list(dict.fromkeys(risk_areas))[:10]
        parts.append("Potential Risk Areas:\n" + "\n".join(f"  - {r}" for r in unique_risks))

    return "\n\n".join(parts) if parts else "(empty or no extractable structure)"


def _format_args(args: ast.arguments) -> str:
    names = [a.arg for a in args.args[:4]]
    if len(args.args) > 4:
        names.append("...")
    return ", ".join(names)


def _decorator_name(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_attr_chain(node)}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return None


def _attr_chain(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_attr_chain(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return "?"


def _call_to_str(node: ast.Call) -> Optional[str]:
    """Extract os.environ.get / os.getenv calls."""
    try:
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ("get", "getenv") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    return arg.value
        if isinstance(node.func, ast.Name) and node.func.id == "getenv" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return arg.value
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# JavaScript / TypeScript regex parser
# ---------------------------------------------------------------------------

def _js_structural_summary(content: str) -> str:
    imports: List[str] = []
    exports: List[str] = []
    classes: List[str] = []
    functions: List[str] = []
    async_functions: List[str] = []
    routes: List[str] = []
    env_reads: List[str] = []
    risk_areas: List[str] = []

    # Imports
    for m in re.finditer(r"^import\s+.+?\s+from\s+['\"](.+?)['\"]", content, re.MULTILINE):
        imports.append(m.group(1))

    # Exports
    for m in re.finditer(r"^export\s+(?:default\s+)?(?:class|function|const|async function)\s+(\w+)", content, re.MULTILINE):
        exports.append(m.group(1))

    # Classes
    for m in re.finditer(r"^(?:export\s+)?class\s+(\w+)", content, re.MULTILINE):
        classes.append(m.group(1))

    # Async functions
    for m in re.finditer(r"async\s+function\s+(\w+)\s*\(([^)]*)\)", content):
        async_functions.append(f"{m.group(1)}({m.group(2)[:40]})")
    for m in re.finditer(r"const\s+(\w+)\s*=\s*async\s*\(([^)]*)\)", content):
        async_functions.append(f"{m.group(1)}({m.group(2)[:40]})")

    # Regular functions
    for m in re.finditer(r"(?<!async\s)function\s+(\w+)\s*\(([^)]*)\)", content):
        functions.append(f"{m.group(1)}({m.group(2)[:40]})")

    # Route definitions (Express / Fastify / Next.js)
    for m in re.finditer(r"\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", content):
        routes.append(f"{m.group(1).upper()} {m.group(2)}")

    # process.env reads
    for m in re.finditer(r"process\.env\.(\w+)", content):
        env_reads.append(m.group(1))

    # Risk keywords
    content_lower = content.lower()
    for kw in RISK_KEYWORDS:
        if kw in content_lower:
            risk_areas.append(kw)

    # Side effects
    side_effects: List[str] = []
    if "fetch(" in content or "axios." in content or "http." in content:
        side_effects.append("HTTP/network calls")
    if "fs." in content or "readFile" in content or "writeFile" in content:
        side_effects.append("Filesystem reads/writes")
    if "redis" in content_lower:
        side_effects.append("Redis usage")
    if "prisma." in content or "sequelize." in content or "typeorm" in content_lower:
        side_effects.append("Database/ORM usage")
    if "subprocess" in content_lower or "exec(" in content or "spawn(" in content:
        side_effects.append("Subprocess execution")

    parts: List[str] = []
    if imports:
        parts.append("Imports:\n" + "\n".join(f"  - {i}" for i in imports[:12]))
    if exports:
        parts.append("Exports:\n" + "\n".join(f"  - {e}" for e in exports[:10]))
    if classes:
        parts.append("Classes:\n" + "\n".join(f"  - {c}" for c in classes))
    if async_functions:
        parts.append("Async Functions:\n" + "\n".join(f"  - {f}" for f in async_functions[:10]))
    if functions:
        parts.append("Functions:\n" + "\n".join(f"  - {f}" for f in functions[:10]))
    if routes:
        parts.append("Routes:\n" + "\n".join(f"  - {r}" for r in routes[:10]))
    if env_reads:
        unique_env = list(dict.fromkeys(env_reads))
        parts.append("Environment Variables:\n" + "\n".join(f"  - {e}" for e in unique_env[:10]))
    if side_effects:
        parts.append("External / Side Effects:\n" + "\n".join(f"  - {s}" for s in side_effects))
    if risk_areas:
        unique_risks = list(dict.fromkeys(risk_areas))[:10]
        parts.append("Potential Risk Areas:\n" + "\n".join(f"  - {r}" for r in unique_risks))

    return "\n\n".join(parts) if parts else "(no extractable structure)"





# ---------------------------------------------------------------------------
# Large file risk notes
# ---------------------------------------------------------------------------

def large_file_risk_note(relative_path: str, size: int) -> Optional[str]:
    """Return a risk note string if the file is large, else None."""
    size_kb = size / 1024
    if size_kb >= LARGE_FILE_CRITICAL_KB:
        return (
            f"Large File Risk: {relative_path} is {size_kb:.0f} KB. "
            f"This may indicate too many responsibilities in a single entry point. "
            f"Recommendation: split orchestration, configuration, runtime loop, "
            f"and business logic into separate modules."
        )
    if size_kb >= LARGE_FILE_RISK_KB:
        return (
            f"Large File Warning: {relative_path} is {size_kb:.0f} KB. "
            f"Consider splitting into smaller focused modules."
        )
    return None
