"""Gemini-optimized prompt template with explicit numbered task breakdown."""

from __future__ import annotations

from ..models import ProjectAnalysis
from ._common import build_common_prompt_sections, build_tech_stack_table


def build_gemini_prompt(analysis: ProjectAnalysis) -> str:
    """
    Build a Gemini-optimized prompt from a ProjectAnalysis.

    Style: explicit numbered sections, clear separation of context/evidence/tasks/output.
    """
    stack = analysis.tech_stack
    meta = analysis.scan_metadata

    prompt = f"""## 1. Role

You are a senior Tech Lead, software architect, security reviewer, and code quality expert.
You have been given a locally generated pre-analysis summary of a software project.
No source files were uploaded to any cloud service — this summary was produced by a local tool.

---

## 2. Project Context

**Project Path:** `{analysis.project_path}`

**Project Summary:**
{analysis.project_summary or 'No Ollama summary available. Use the evidence sections below.'}

**Scan Information:**
- Scan ID: {meta.scan_id if meta else 'N/A'}
- Scanned At: {meta.scanned_at if meta else 'N/A'}
- Files Scanned: {meta.files_scanned if meta else 'N/A'}
- Files Skipped: {meta.files_skipped if meta else 'N/A'}
- Files with Redacted Secrets: {meta.files_redacted if meta else 'N/A'}
- Ollama Summarization Used: {meta.ollama_used if meta else 'N/A'}
{f'- Ollama Note: {meta.ollama_error}' if meta and meta.ollama_error else ''}

---

## 3. Evidence

### 3.1 Detected Technology Stack

{build_tech_stack_table(stack)}

### 3.2 File Tree

```
{analysis.file_tree}
```

### 3.3 Important Files

{_build_important_files(analysis)}

### 3.4 File Summaries

{_build_file_summaries(analysis)}

### 3.5 Risk Notes

{_build_risks(analysis)}

### 3.6 Redaction Report

{_build_redaction(analysis)}

---

## 4. Tasks

Complete each of the following analysis tasks in order. Do not skip any task.
Do not ask questions — make reasonable assumptions where information is missing.

**Task 1: Understand Project Purpose**
- Identify what the project does and who uses it.
- Note the project type (web app, API, CLI tool, library, etc.).

**Task 2: Review Architecture**
- Identify the architectural pattern (monolith, microservices, layered, etc.).
- Evaluate separation of concerns and module boundaries.
- Note architectural strengths and weaknesses.

**Task 3: Review Technology Stack**
- Confirm or correct the detected technologies.
- Evaluate whether the stack is appropriate for the project type.
- Identify any outdated, risky, or missing dependencies.

**Task 4: Review Folder Structure**
- Evaluate the organization and naming conventions.
- Identify any structural issues or anti-patterns.

**Task 5: Review Database and Data Model**
- Describe the database setup and ORM usage.
- Evaluate schema design, relationships, and migration strategy.
- Note any data integrity or performance concerns.

**Task 6: Review Authentication and Authorization**
- Describe how auth is implemented.
- Identify any gaps, weaknesses, or missing protections.

**Task 7: Review Security Risks**
- Check for hardcoded secrets, injection risks, missing validation.
- Check CORS, rate limiting, input sanitization.
- Note any critical security issues.

**Task 8: Review Code Quality**
- Identify patterns and anti-patterns.
- Evaluate complexity, duplication, and readability.
- Note maintainability concerns.

**Task 9: Review Test Coverage**
- Describe what testing exists.
- Identify critical paths that appear untested.
- Recommend testing improvements.

**Task 10: Review Deployment and Build Risks**
- Evaluate Docker, CI/CD, and environment configuration.
- Note any deployment risks or missing configurations.

**Task 11: Produce Prioritized Action Plan**
- List all findings by priority (Critical → High → Medium → Low).
- Provide specific, actionable recommendations for each.

---

## 5. Constraints

- Complete all 11 tasks before writing the final report.
- Do NOT ask clarifying questions.
- Clearly separate facts from assumptions.
- Label assumptions explicitly (e.g., "Assumption: ...").
- Treat the pre-analysis as evidence, not absolute truth.
- Do not claim to have read files not included in the summary.
- Mention uncertainty where needed.
- Prioritize security and architecture findings.

---

## 6. Output Format

Produce a structured technical report with these sections:

1. **Executive Summary** (3-5 sentences)
2. **Stack Confirmation** (confirm/correct detected technologies)
3. **Architecture Review** (pattern, strengths, weaknesses)
4. **Security Findings** (table: Finding | Severity | File/Area | Recommendation)
5. **Database Review** (schema, ORM, migrations, risks)
6. **Code Quality Review** (patterns, anti-patterns, maintainability)
7. **Testing Gaps** (coverage assessment, missing tests)
8. **Risk Table** (Risk | Likelihood | Impact | Priority)
9. **Refactor Plan** (P1/P2/P3 prioritized improvements)
10. **Final Verdict** (health score 1-10 + top 3 immediate actions)

---

{build_common_prompt_sections(analysis)}

---

## 7. Final Deliverable

After completing all 11 analysis tasks, produce the full technical report as described in Section 6.
Be specific, actionable, and thorough.
Use tables and lists where they improve clarity.
Flag critical security issues prominently.

_Generated by Local Project Prompt Generator v1.0.0_
"""
    return prompt.strip()


def _build_important_files(analysis: ProjectAnalysis) -> str:
    if not analysis.important_files:
        return "_No important files identified._"
    lines = []
    for f in analysis.important_files[:30]:
        note = " *(contains redacted secrets)*" if f.redacted else ""
        lines.append(f"- `{f.relative_path}` — priority score: {f.priority_score}{note}")
    return "\n".join(lines)


def _build_file_summaries(analysis: ProjectAnalysis) -> str:
    if not analysis.file_summaries:
        return "_No file summaries available (static analysis mode)._"
    lines = []
    for path, summary in list(analysis.file_summaries.items())[:40]:
        lines.append(f"**`{path}`**\n{summary}\n")
    return "\n".join(lines)


def _build_risks(analysis: ProjectAnalysis) -> str:
    if not analysis.risk_notes:
        return "_No specific risk notes generated._"
    return "\n".join(f"- {note}" for note in analysis.risk_notes)


def _build_redaction(analysis: ProjectAnalysis) -> str:
    if not analysis.redaction_findings:
        return "_No secrets were detected or redacted._"
    lines = ["The following secret patterns were detected and redacted before this prompt was generated:"]
    for finding in analysis.redaction_findings:
        lines.append(f"- `{finding.file_path}`: **{finding.finding_type}** — {finding.count} occurrence(s)")
    lines.append("\n> Secret values are NOT included in this prompt.")
    return "\n".join(lines)
