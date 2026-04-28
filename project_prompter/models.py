"""Pydantic data models for the Local Project Prompt Generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

@dataclass
class DomainDetectionResult:
    domain: str
    confidence: str  # low | medium | high
    score: int
    strong_indicator_count: int
    matched_indicators: List[str]
    evidence: List[str]


@dataclass
class ScanOptions:
    """Options controlling how a project scan is performed."""

    project_path: Path
    output_path: Path = field(default_factory=lambda: Path("./output"))
    model: str = "llama3:latest"
    ollama_url: str = "http://localhost:11434"
    max_files: int = 40           # fast mode default
    max_chars_per_file: int = 3000  # fast mode default
    use_ollama: bool = False      # DEFAULT OFF — fast mode
    target_model: str = "all"    # chatgpt | claude | gemini | minimax | generic | all
    format: str = "markdown"
    mode: str = "fast"           # fast | balanced | deep
    use_cache: bool = True
    clear_cache: bool = False
    dry_run: bool = False
    ollama_max_files: int = 10   # how many files to send to Ollama at most
    strict_ollama: bool = False  # if True, fail when Ollama unavailable + --use-ollama
    extra_ignore_dirs: List[str] = field(default_factory=list)


@dataclass
class ScannedFile:
    """Represents a single file discovered during project scanning."""

    path: Path
    relative_path: str
    extension: str
    size: int
    priority_score: int = 0
    redacted: bool = False
    skipped_reason: Optional[str] = None
    content_preview: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class TechStack:
    """Detected technology stack for a project."""

    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    libraries: List[str] = field(default_factory=list)
    databases: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    package_managers: List[str] = field(default_factory=list)
    testing_tools: List[str] = field(default_factory=list)
    ai_services: List[str] = field(default_factory=list)
    sources: Dict[str, set[str]] = field(default_factory=dict)

    def add_item(self, category: str, item: str, source: str) -> None:
        lst = getattr(self, category)
        if item not in lst:
            lst.append(item)
        if item not in self.sources:
            self.sources[item] = set()
        self.sources[item].add(source)

    def all_detected(self) -> List[str]:
        """Return a flat list of all detected technologies."""
        result = []
        for lst in [
            self.languages,
            self.frameworks,
            self.libraries,
            self.databases,
            self.tools,
            self.package_managers,
            self.testing_tools,
            self.ai_services,
        ]:
            result.extend(lst)
        return result

    def is_empty(self) -> bool:
        return len(self.all_detected()) == 0


@dataclass
class RedactionFinding:
    """A secret or sensitive value found and redacted in a source file."""

    file_path: str
    finding_type: str  # e.g. API_KEY, PASSWORD, TOKEN, PRIVATE_KEY
    count: int = 1


@dataclass
class ScanMetadata:
    """Metadata about the scan run itself."""

    scan_id: str
    scanned_at: str
    project_path: str
    total_files_found: int = 0
    files_scanned: int = 0
    files_skipped: int = 0
    files_redacted: int = 0
    ollama_used: bool = False
    ollama_model: str = "llama3:latest"
    ollama_available: bool = False
    ollama_error: Optional[str] = None
    target_model: str = "all"
    duration_seconds: float = 0.0
    mode: str = "fast"
    evidence_level: str = "medium"   # low | medium | high
    domain_result: Optional[DomainDetectionResult] = None


@dataclass
class ProjectAnalysis:
    """Normalized analysis result for a scanned project."""

    project_path: str
    file_tree: str
    tech_stack: TechStack
    important_files: List[ScannedFile] = field(default_factory=list)
    file_summaries: Dict[str, str] = field(default_factory=dict)
    module_summaries: Dict[str, str] = field(default_factory=dict)
    risk_notes: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    redaction_findings: List[RedactionFinding] = field(default_factory=list)
    scan_metadata: Optional[ScanMetadata] = None
    project_summary: str = ""
    domain_result: Optional[DomainDetectionResult] = None
    structural_summaries: Dict[str, str] = field(default_factory=dict)
