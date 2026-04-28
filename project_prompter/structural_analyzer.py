"""Structural summary generator — AST-based for Python, regex for JS/TS."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Optional

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
    elif ext == ".go":
        body = _go_structural_summary(content)
    elif ext == ".rs":
        body = _rust_structural_summary(content)
    elif ext == ".rb":
        body = _ruby_structural_summary(content)
    else:
        # Plain preview for other types
        lines = content.splitlines()[:15]
        body = "Preview:\n" + "\n".join(f"  {line}" for line in lines if line.strip())

    return header + risk_prefix + body


def _file_type_label(ext: str) -> str:
    labels = {
        ".py": "Python source",
        ".ts": "TypeScript source",
        ".tsx": "TypeScript/React",
        ".js": "JavaScript source",
        ".jsx": "JavaScript/React",
        ".go": "Go source",
        ".rb": "Ruby source",
        ".rs": "Rust source",
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
        return "Parse error. Preview:\n" + "\n".join(f"  {line}" for line in lines)

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
# Go regex parser
# ---------------------------------------------------------------------------

def _go_structural_summary(content: str) -> str:
    packages: List[str] = []
    imports: List[str] = []
    functions: List[str] = []
    types: List[str] = []
    constants: List[str] = []
    variables: List[str] = []
    routes: List[str] = []
    env_reads: List[str] = []
    risk_areas: List[str] = []

    package_match = re.search(r"^\s*package\s+([A-Za-z_]\w*)", content, re.MULTILINE)
    if package_match:
        packages.append(package_match.group(1))

    for block in re.finditer(r"^\s*import\s*\((.*?)^\s*\)", content, re.MULTILINE | re.DOTALL):
        for m in re.finditer(r'(?:[A-Za-z_][\w.]*\s+)?["`]([^"`]+)["`]', block.group(1)):
            imports.append(m.group(1))
    for m in re.finditer(r'^\s*import\s+(?:[A-Za-z_][\w.]*\s+)?["`]([^"`]+)["`]', content, re.MULTILINE):
        imports.append(m.group(1))

    for m in re.finditer(r"^\s*func\s+(?:\([^)]*\)\s+)?([A-Za-z_]\w*)\s*\(([^)]*)\)", content, re.MULTILINE):
        functions.append(f"{m.group(1)}({m.group(2)[:60].strip()})")

    for m in re.finditer(r"^\s*type\s+([A-Za-z_]\w*)\s+(struct|interface)\b", content, re.MULTILINE):
        types.append(f"{m.group(1)} {m.group(2)}")

    for block in re.finditer(r"^\s*(const|var)\s*\((.*?)^\s*\)", content, re.MULTILINE | re.DOTALL):
        target = constants if block.group(1) == "const" else variables
        for line in block.group(2).splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("//"):
                target.append(stripped[:80])
    for m in re.finditer(r"^\s*const\s+([A-Za-z_]\w*)", content, re.MULTILINE):
        constants.append(m.group(1))
    for m in re.finditer(r"^\s*var\s+([A-Za-z_]\w*)", content, re.MULTILINE):
        variables.append(m.group(1))

    route_pattern = (
        r"\b(?:r|router|mux|e|app|api|http)\."
        r"(GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete|Patch|HandleFunc)\s*"
        r"\(\s*[\"`]([^\"`]+)[\"`]"
    )
    for m in re.finditer(route_pattern, content):
        method = "ANY" if m.group(1) == "HandleFunc" else m.group(1).upper()
        routes.append(f"{method} {m.group(2)}")

    for m in re.finditer(r"os\.Getenv\(\s*[\"`]([^\"`]+)[\"`]\s*\)", content):
        env_reads.append(m.group(1))

    content_lower = content.lower()
    for kw in RISK_KEYWORDS:
        if kw in content_lower:
            risk_areas.append(kw)

    side_effects: List[str] = []
    if "net/http" in content or "http." in content:
        side_effects.append("HTTP/network calls or server routes")
    if "os." in content or "ioutil." in content or "bufio." in content:
        side_effects.append("Filesystem/process environment access")
    if any(k in content_lower for k in ("database/sql", "gorm", "sqlx", "redis")):
        side_effects.append("Database/cache usage")

    parts: List[str] = []
    if packages:
        parts.append("Package:\n" + "\n".join(f"  - {p}" for p in packages[:1]))
    if imports:
        unique_imports = list(dict.fromkeys(imports))
        parts.append("Imports:\n" + "\n".join(f"  - {i}" for i in unique_imports[:12]))
    if types:
        parts.append("Types:\n" + "\n".join(f"  - {t}" for t in types[:12]))
    if functions:
        parts.append("Functions:\n" + "\n".join(f"  - {f}" for f in functions[:20]))
    if constants:
        parts.append("Constants:\n" + "\n".join(f"  - {c}" for c in constants[:5]))
    if variables:
        parts.append("Variables:\n" + "\n".join(f"  - {v}" for v in variables[:5]))
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

    return "\n\n".join(parts) if parts else "(empty or no extractable structure)"


# ---------------------------------------------------------------------------
# Rust regex parser
# ---------------------------------------------------------------------------

def _rust_structural_summary(content: str) -> str:
    uses: List[str] = []
    functions: List[str] = []
    types: List[str] = []
    impls: List[str] = []
    modules: List[str] = []
    env_reads: List[str] = []
    risk_areas: List[str] = []

    for m in re.finditer(r"^\s*use\s+([^;]+);", content, re.MULTILINE):
        uses.append(m.group(1).strip())

    fn_pattern = (
        r"^\s*((?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn)\s+"
        r"([A-Za-z_]\w*)\s*\(([^)]*)\)"
    )
    for m in re.finditer(fn_pattern, content, re.MULTILINE):
        prefix = "async " if "async" in m.group(1) else ""
        visibility = "pub " if "pub" in m.group(1) else ""
        functions.append(f"{visibility}{prefix}{m.group(2)}({m.group(3)[:60].strip()})")

    for m in re.finditer(r"^\s*(?:pub\s+)?(struct|enum|trait)\s+([A-Za-z_]\w*)", content, re.MULTILINE):
        types.append(f"{m.group(2)} {m.group(1)}")

    for m in re.finditer(r"^\s*impl(?:<[^>]+>)?\s+([^{]+)\{", content, re.MULTILINE):
        impls.append(m.group(1).strip())

    for m in re.finditer(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_]\w*)\s*[;{]", content, re.MULTILINE):
        modules.append(m.group(1))

    for m in re.finditer(r"(?:std::)?env::var\(\s*[\"']([^\"']+)[\"']\s*\)", content):
        env_reads.append(m.group(1))
    for m in re.finditer(r"env!\(\s*[\"']([^\"']+)[\"']\s*\)", content):
        env_reads.append(m.group(1))

    content_lower = content.lower()
    for kw in RISK_KEYWORDS:
        if kw in content_lower:
            risk_areas.append(kw)

    side_effects: List[str] = []
    if "tokio::" in content:
        side_effects.append("Tokio async runtime")
    if "reqwest" in content_lower:
        side_effects.append("HTTP/network calls")
    if "sqlx" in content_lower:
        side_effects.append("Database usage")
    if "serde" in content_lower:
        side_effects.append("Serialization/deserialization")

    parts: List[str] = []
    if uses:
        unique_uses = list(dict.fromkeys(uses))
        parts.append("Uses:\n" + "\n".join(f"  - {u}" for u in unique_uses[:12]))
    if modules:
        parts.append("Modules:\n" + "\n".join(f"  - {m}" for m in modules[:12]))
    if types:
        parts.append("Types:\n" + "\n".join(f"  - {t}" for t in types[:12]))
    if impls:
        parts.append("Impl Blocks:\n" + "\n".join(f"  - {i}" for i in impls[:12]))
    if functions:
        parts.append("Functions:\n" + "\n".join(f"  - {f}" for f in functions[:20]))
    if env_reads:
        unique_env = list(dict.fromkeys(env_reads))
        parts.append("Environment Variables:\n" + "\n".join(f"  - {e}" for e in unique_env[:10]))
    if side_effects:
        parts.append("External / Side Effects:\n" + "\n".join(f"  - {s}" for s in side_effects))
    if risk_areas:
        unique_risks = list(dict.fromkeys(risk_areas))[:10]
        parts.append("Potential Risk Areas:\n" + "\n".join(f"  - {r}" for r in unique_risks))

    return "\n\n".join(parts) if parts else "(empty or no extractable structure)"


# ---------------------------------------------------------------------------
# Ruby regex parser
# ---------------------------------------------------------------------------

def _ruby_structural_summary(content: str) -> str:
    requires: List[str] = []
    modules: List[str] = []
    classes: List[str] = []
    methods: List[str] = []
    attrs: List[str] = []
    associations: List[str] = []
    routes: List[str] = []
    env_reads: List[str] = []
    risk_areas: List[str] = []

    for m in re.finditer(r"^\s*require(?:_relative)?\s+[\"']([^\"']+)[\"']", content, re.MULTILINE):
        requires.append(m.group(1))

    name_pattern = r"[A-Z][A-Za-z_0-9]*(?:::[A-Z][A-Za-z_0-9]*)*"
    for m in re.finditer(rf"^\s*module\s+({name_pattern})", content, re.MULTILINE):
        modules.append(m.group(1))
    for m in re.finditer(rf"^\s*class\s+({name_pattern})(?:\s*<\s*({name_pattern}))?", content, re.MULTILINE):
        base = f" < {m.group(2)}" if m.group(2) else ""
        classes.append(f"{m.group(1)}{base}")

    method_pattern = r"^\s*def\s+((?:self\.)?[A-Za-z_]\w*[!?=]?)\s*(?:\(([^)]*)\)|([^\n#]*))"
    for m in re.finditer(method_pattern, content, re.MULTILINE):
        args = (m.group(2) if m.group(2) is not None else m.group(3)).strip()
        methods.append(f"{m.group(1)}({args[:60]})")

    for m in re.finditer(r"^\s*(attr_accessor|attr_reader|attr_writer)\s+([^\n#]+)", content, re.MULTILINE):
        attrs.append(f"{m.group(1)} {m.group(2).strip()[:80]}")

    for m in re.finditer(r"^\s*(belongs_to|has_many|has_one)\s+:([A-Za-z_]\w*)", content, re.MULTILINE):
        associations.append(f"{m.group(1)} :{m.group(2)}")

    for m in re.finditer(r"^\s*(get|post|put|patch|delete)\s+[\"']([^\"']+)[\"']", content, re.MULTILINE):
        routes.append(f"{m.group(1).upper()} {m.group(2)}")
    for m in re.finditer(r"^\s*resources\s+:?([A-Za-z_]\w*)", content, re.MULTILINE):
        routes.append(f"RESOURCES {m.group(1)}")

    for m in re.finditer(r"ENV\[\s*[\"']([^\"']+)[\"']\s*\]", content):
        env_reads.append(m.group(1))
    for m in re.finditer(r"ENV\.fetch\(\s*[\"']([^\"']+)[\"']", content):
        env_reads.append(m.group(1))

    content_lower = content.lower()
    for kw in RISK_KEYWORDS:
        if kw in content_lower:
            risk_areas.append(kw)

    side_effects: List[str] = []
    if any(k in content_lower for k in ("net::http", "faraday", "httparty")):
        side_effects.append("HTTP/network calls")
    if any(k in content_lower for k in ("activerecord", "belongs_to", "has_many", "has_one")):
        side_effects.append("ActiveRecord models/associations")
    if any(k in content_lower for k in ("file.open", "file.read", "file.write")):
        side_effects.append("Filesystem reads/writes")

    parts: List[str] = []
    if requires:
        unique_requires = list(dict.fromkeys(requires))
        parts.append("Requires:\n" + "\n".join(f"  - {r}" for r in unique_requires[:12]))
    if modules:
        parts.append("Modules:\n" + "\n".join(f"  - {m}" for m in modules[:12]))
    if classes:
        parts.append("Classes:\n" + "\n".join(f"  - {c}" for c in classes[:12]))
    if methods:
        parts.append("Methods:\n" + "\n".join(f"  - {m}" for m in methods[:20]))
    if attrs:
        parts.append("Attributes:\n" + "\n".join(f"  - {a}" for a in attrs[:10]))
    if associations:
        parts.append("Associations:\n" + "\n".join(f"  - {a}" for a in associations[:10]))
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

    return "\n\n".join(parts) if parts else "(empty or no extractable structure)"





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
