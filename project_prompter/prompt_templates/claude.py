"""Claude-optimized prompt template using XML-like structure."""

from __future__ import annotations

from ..models import ProjectAnalysis
from ._common import build_common_prompt_sections, build_tech_stack_table


def build_claude_prompt(analysis: ProjectAnalysis) -> str:
    """
    Build a Claude-optimized prompt from a ProjectAnalysis.

    Style: XML-like sections, long structured context, separated facts/assumptions/risks.
    """
    stack = analysis.tech_stack
    meta = analysis.scan_metadata

    facts = _build_facts(analysis)
    assumptions = _build_assumptions(analysis)
    file_summaries = _build_file_summaries(analysis)
    risk_notes = _build_risks(analysis)
    redaction_note = _build_redaction(analysis)
    file_tree = analysis.file_tree
    project_summary = analysis.project_summary or "No Ollama summary available. Use static analysis data below."
    tech_table = build_tech_stack_table(stack)

    prompt = f"""<role>
You are a senior Tech Lead, software architect, security reviewer, and code quality expert.
Your task is to perform a thorough, careful analysis of a software project based on a locally generated pre-analysis summary.
This summary was produced by a local tool — no source files were uploaded to any cloud service.
</role>

<context>
{project_summary}

Project Path: {analysis.project_path}
</context>

<facts>
{facts}
</facts>

<assumptions>
{assumptions}
</assumptions>

<tech_stack>
{tech_table}
</tech_stack>

<file_tree>
{file_tree}
</file_tree>

<important_files>
{_build_important_files(analysis)}
</important_files>

<file_summaries>
{file_summaries}
</file_summaries>

<risk_notes>
{risk_notes}
</risk_notes>

<redaction_report>
{redaction_note}
</redaction_report>

<instructions>
Analyze this project carefully and completely. Work through each of the following phases before writing your final report:

1. Understand the project's purpose and intended users.
2. Review the overall architecture — patterns, layers, separation of concerns.
3. Review the technology stack — appropriateness, risks, outdated dependencies.
4. Review the folder structure — organization, maintainability, naming conventions.
5. Review the database and data model — schema design, ORM usage, migration strategy.
6. Review authentication and authorization — mechanisms, gaps, security posture.
7. Review security risks — secrets exposure, injection risks, input validation, CORS, rate limiting.
8. Review code quality — patterns, anti-patterns, complexity, duplication, readability.
9. Review test coverage — what is tested, what is missing, test quality.
10. Review deployment and build risks — Docker, CI/CD, environment configuration.
11. Produce a prioritized action plan.

Do not ask questions until all phases are completed.
If information is missing, make reasonable assumptions and label them clearly.
Clearly separate facts from assumptions throughout your analysis.
Prioritize critical security and architecture risks.
Treat the pre-analysis as evidence, not as absolute truth.
Mention uncertainty where needed.
Do not claim to have read files that were not included in the summary.
</instructions>

<output_format>
Produce a structured written analysis with the following sections:

1. Executive Summary
   - 3-5 sentences describing the project, its purpose, and overall health.

2. Detected Stack Confirmation
   - Confirm or correct the detected technologies.
   - Note any inconsistencies or missing detections.

3. Architecture Review
   - Describe the architecture pattern.
   - Identify strengths and weaknesses.
   - Note any architectural risks.

4. Security Findings
   - List each finding with: description, severity (Critical/High/Medium/Low), affected file(s), and recommendation.
   - Highlight any critical issues prominently.

5. Database Review
   - Describe the data model and ORM usage.
   - Note schema design concerns, migration strategy, and data integrity risks.

6. Code Quality Review
   - Describe patterns and anti-patterns observed.
   - Note maintainability, complexity, and duplication concerns.

7. Testing Gaps
   - Describe what testing exists.
   - List critical paths that appear untested.
   - Recommend testing improvements.

8. Risk Table
   - Format: Risk | Likelihood | Impact | Priority | Recommendation

9. Refactor Plan
   - Prioritized list of improvements (P1 = critical, P2 = important, P3 = nice-to-have).

10. Final Verdict
    - Overall project health score (1-10) with justification.
    - Top 3 immediate actions.
</output_format>

<analysis_quality>
{build_common_prompt_sections(analysis)}
</analysis_quality>

<scan_metadata>
Scan ID: {meta.scan_id if meta else 'N/A'}
Scanned At: {meta.scanned_at if meta else 'N/A'}
Files Scanned: {meta.files_scanned if meta else 'N/A'}
Files Skipped: {meta.files_skipped if meta else 'N/A'}
Files Redacted: {meta.files_redacted if meta else 'N/A'}
Ollama Used: {meta.ollama_used if meta else 'N/A'}
{f'Ollama Note: {meta.ollama_error}' if meta and meta.ollama_error else ''}
Generated by: Local Project Prompt Generator v1.0.0
</scan_metadata>"""

    return prompt.strip()


def _build_facts(analysis: ProjectAnalysis) -> str:
    meta = analysis.scan_metadata
    lines = [
        f"- Project path: {analysis.project_path}",
        f"- Files scanned: {meta.files_scanned if meta else 'N/A'}",
        f"- Files skipped: {meta.files_skipped if meta else 'N/A'}",
        f"- Files with redacted secrets: {meta.files_redacted if meta else 'N/A'}",
        f"- Ollama summarization used: {meta.ollama_used if meta else 'N/A'}",
    ]
    if analysis.tech_stack.languages:
        lines.append(f"- Detected languages: {', '.join(analysis.tech_stack.languages)}")
    if analysis.tech_stack.frameworks:
        lines.append(f"- Detected frameworks: {', '.join(analysis.tech_stack.frameworks)}")
    if analysis.redaction_findings:
        lines.append(f"- Secret patterns found and redacted: {len(analysis.redaction_findings)} finding(s)")
    return "\n".join(lines)


def _build_assumptions(analysis: ProjectAnalysis) -> str:
    if analysis.assumptions:
        return "\n".join(f"- {a}" for a in analysis.assumptions)
    return (
        "- File summaries are based on static analysis or local Ollama summarization.\n"
        "- The file tree may not reflect all files if limits were applied.\n"
        "- Technology detection is based on config files and dependency manifests.\n"
        "- Secret redaction may not catch all sensitive values — treat with caution."
    )


def _build_important_files(analysis: ProjectAnalysis) -> str:
    if not analysis.important_files:
        return "No important files identified."
    lines = []
    for f in analysis.important_files[:30]:
        note = " [REDACTED]" if f.redacted else ""
        lines.append(f"- {f.relative_path} (score: {f.priority_score}){note}")
    return "\n".join(lines)


def _build_file_summaries(analysis: ProjectAnalysis) -> str:
    if not analysis.file_summaries:
        return "No file summaries available."
    lines = []
    for path, summary in list(analysis.file_summaries.items())[:40]:
        lines.append(f"[{path}]\n{summary}\n")
    return "\n".join(lines)


def _build_risks(analysis: ProjectAnalysis) -> str:
    if not analysis.risk_notes:
        return "No specific risk notes generated."
    return "\n".join(f"- {note}" for note in analysis.risk_notes)


def _build_redaction(analysis: ProjectAnalysis) -> str:
    if not analysis.redaction_findings:
        return "No secrets were detected or redacted."
    lines = ["The following secret patterns were detected and redacted:"]
    for finding in analysis.redaction_findings:
        lines.append(f"- {finding.file_path}: {finding.finding_type} ({finding.count} occurrence(s))")
    lines.append("\nSecret values are NOT included in this prompt. They were replaced with placeholders.")
    return "\n".join(lines)
