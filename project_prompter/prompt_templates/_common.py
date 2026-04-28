"""Common prompt helpers — shared across all model-specific templates."""

from __future__ import annotations

from ..models import ProjectAnalysis

# ---------------------------------------------------------------------------
# Special Domain Risk Sections
# ---------------------------------------------------------------------------

SPECIAL_DOMAIN_SECTIONS = {
    "trading_fintech": """
## Special Domain Risk: Trading / Financial Automation

⚠ This project appears to involve trading or financial automation.
Pay special attention to:

- API key permissions and scoping
- Live vs paper/test mode separation
- Order validation and protective controls
- Kill switch and emergency stop behavior
- Reconciliation after failed or partial financial operations
- Exchange/API downtime handling
- Retry behavior and idempotency
- Rate limiting compliance
- Audit logging for financial operations
""",
    "audio_ai_saas": """
## Special Domain Risk: Audio Analysis / AI SaaS

⚠ This project appears to be an Audio Analysis / AI SaaS.
Pay special attention to:

- Audio upload validation and file type enforcement
- Maximum file size and duration limits
- Temporary audio cleanup and retention policy
- User ownership checks for analysis jobs and reports
- External AI API key handling
- Prompt injection through transcript content
- PII leakage in transcripts and generated reports
- PDF generation safety
- Background job isolation
- Object storage permissions and signed URL expiry
- Rate limiting and abuse prevention
- Cost controls for transcription and LLM usage
""",
    "ecommerce": """
## Special Domain Risk: E-commerce / Payments

⚠ This project appears to be an E-commerce or Payments system.
Pay special attention to:

- Payment provider integration safety
- Order state transitions
- Inventory consistency
- Checkout abuse prevention
- Coupon/discount validation
- PII handling for addresses and customer profiles
- Refund and cancellation workflows
- Webhook verification and idempotency
""",
    "content_cms": """
## Special Domain Risk: Content / CMS

⚠ This project appears to be a Content Management System (CMS).
Pay special attention to:

- Stored XSS in rich text/content fields
- Upload validation for media files
- Draft/publish permission boundaries
- Slug uniqueness and routing conflicts
- Content moderation workflow
- Role-based access for editors/admins
""",
    "devtool": """
## Special Domain Risk: Developer Tooling

⚠ This project appears to be a Developer Tool or CLI.
Pay special attention to:

- Secret redaction correctness
- Local file access boundaries
- Ignore rules and privacy protection
- Handling of large repositories
- Prompt honesty and evidence limits
- Cache invalidation
- Safe treatment of binary/generated files
""",
    "data_science": """
## Special Domain Risk: Data Science / Machine Learning

This project appears to involve data science or machine learning.
Pay special attention to:

- PII and sensitive data in datasets
- Hardcoded credentials in notebooks
- Privacy, size, and retention of model weight files (.pkl, .h5, .pt)
- Training-data poisoning risk, especially with external data sources
- GPU and cloud compute cost controls
- Random seed reproducibility
- Reliability of model outputs and hallucination risk
- MLOps, model versioning, and experiment tracking
"""
}


def build_analysis_metadata(analysis: ProjectAnalysis) -> str:
    """Build the analysis metadata block for prompt honesty."""
    meta = analysis.scan_metadata
    if not meta:
        return ""

    included_files = len(analysis.important_files)
    skipped_files = meta.files_skipped
    
    domain_result = analysis.domain_result
    
    metadata = [
        "## Analysis Metadata\n\n",
        "| Field | Value |\n",
        "|---|---|\n",
        f"| Analysis Type | {_analysis_type(meta)} |\n",
        f"| Evidence Level | {meta.evidence_level.capitalize()} |\n",
        "| Full Source Audit | No |\n",
        f"| Ollama Used | {meta.ollama_used} |\n",
        f"| Included File Evidence Count | {included_files} |\n",
        f"| Skipped Files Count | {skipped_files} |\n",
        f"| Mode | {meta.mode} |\n"
    ]
    
    if domain_result:
        metadata.append(f"| Detected Domain | {domain_result.domain} |\n")
        metadata.append(f"| Domain Confidence | {domain_result.confidence} |\n")
        
        if domain_result.domain != "generic":
            metadata.append(f"| Domain Score | {domain_result.score} |\n")
            if domain_result.matched_indicators:
                indicators = ", ".join(domain_result.matched_indicators)
                metadata.append(f"| Domain Indicators | {indicators} |\n")

    return "".join(metadata)


def _analysis_type(meta) -> str:
    """Determine analysis type label from metadata."""
    if meta.mode == "deep" and meta.ollama_used:
        return "Deep Architecture Review (Static + Ollama)"
    if meta.mode == "balanced" and meta.ollama_used:
        return "Balanced Architecture Review (Static + Ollama)"
    if meta.mode == "balanced":
        return "Balanced Static Architecture Review"
    return "Limited Static Architecture Review"


def build_evidence_disclaimer(analysis: ProjectAnalysis) -> str:
    """Build evidence-level disclaimer for the prompt."""
    meta = analysis.scan_metadata
    if not meta:
        return ""

    parts = []

    # Structural-only disclaimer
    if not meta.ollama_used:
        parts.append(
            "Do not claim to have performed a full source-code audit. "
            "Base findings only on file tree, structural summaries, config previews, and included evidence."
        )

    # Limited file count disclaimer
    included = len(analysis.important_files)
    if included < 20:
        parts.append(
            "Evidence is limited. Produce a limited architecture and risk review, "
            "not a definitive security audit."
        )

    # Ollama unavailable note
    if meta.ollama_error and not meta.ollama_used:
        parts.append(
            f"Ollama was unavailable: {meta.ollama_error}. Static-only analysis was used."
        )

    if not parts:
        return ""

    return "## Evidence Disclaimer\n\n" + "\n\n".join(f"> ⚠ {p}" for p in parts) + "\n"


def build_special_domain_section(analysis: ProjectAnalysis) -> str:
    """Return the special domain risk section if detected, empty string otherwise."""
    domain_result = analysis.domain_result
    
    if not domain_result or domain_result.domain == "generic":
        return ""
        
    if domain_result.confidence in ("medium", "high") and domain_result.domain in SPECIAL_DOMAIN_SECTIONS:
        return SPECIAL_DOMAIN_SECTIONS[domain_result.domain].strip() + "\n"
        
    return ""


def build_tech_stack_table(stack) -> str:
    """Build the markdown table for detected technology stack, including sources."""
    rows = []
    
    def _fmt(category: str) -> str:
        lst = getattr(stack, category, [])
        if not lst:
            return ""
        parts = []
        for item in lst:
            sources = stack.sources.get(item, set())
            if sources:
                src_str = ", ".join(sorted(sources))
                parts.append(f"{item} ({src_str})")
            else:
                parts.append(item)
        return ", ".join(parts)

    cats = [
        ("Languages", "languages"),
        ("Frameworks", "frameworks"),
        ("Libraries", "libraries"),
        ("Databases / ORM", "databases"),
        ("Tools", "tools"),
        ("Package Managers", "package_managers"),
        ("Testing", "testing_tools"),
        ("AI Services", "ai_services"),
    ]

    for label, attr in cats:
        val = _fmt(attr)
        if val:
            rows.append(f"| {label} | {val} |")

    if rows:
        return "| Category | Detected |\n|---|---|\n" + "\n".join(rows)
    return "_No technologies detected._"

def build_common_prompt_sections(analysis: ProjectAnalysis) -> str:
    """Build all common sections (metadata + disclaimer + special domain risk) as a combined string."""
    sections = []

    metadata = build_analysis_metadata(analysis)
    if metadata:
        sections.append(metadata)

    disclaimer = build_evidence_disclaimer(analysis)
    if disclaimer:
        sections.append(disclaimer)

    domain_section = build_special_domain_section(analysis)
    if domain_section:
        sections.append(domain_section)

    return "\n---\n\n".join(sections)
