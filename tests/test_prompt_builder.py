"""Tests for prompt generation — all 5 model templates."""

import pytest
from pathlib import Path

from project_prompter.models import (
    ProjectAnalysis,
    RedactionFinding,
    ScanMetadata,
    ScannedFile,
    TechStack,
)
from project_prompter.prompt_builder import build_prompts, ALL_MODELS
from project_prompter.prompt_templates.chatgpt import build_chatgpt_prompt
from project_prompter.prompt_templates.claude import build_claude_prompt
from project_prompter.prompt_templates.gemini import build_gemini_prompt
from project_prompter.prompt_templates.minimax import build_minimax_prompt
from project_prompter.prompt_templates.generic import build_generic_prompt


def make_analysis(
    project_path: str = "/test/project",
    with_redactions: bool = False,
    with_summaries: bool = False,
) -> ProjectAnalysis:
    """Create a minimal ProjectAnalysis for testing."""
    meta = ScanMetadata(
        scan_id="test-scan-001",
        scanned_at="2024-01-01T00:00:00+00:00",
        project_path=project_path,
        total_files_found=50,
        files_scanned=40,
        files_skipped=10,
        files_redacted=2 if with_redactions else 0,
        ollama_used=with_summaries,
        ollama_model="llama3:latest",
        ollama_available=with_summaries,
        ollama_error=None if with_summaries else "Ollama not available",
        target_model="all",
        duration_seconds=5.2,
    )

    stack = TechStack(
        languages=["TypeScript", "JavaScript"],
        frameworks=["React", "Next.js", "Node.js"],
        databases=["PostgreSQL", "Prisma"],
        tools=["Docker", "Vite"],
        package_managers=["npm"],
        testing_tools=["Jest", "Playwright"],
    )

    important_files = [
        ScannedFile(
            path=Path("README.md"),
            relative_path="README.md",
            extension=".md",
            size=2048,
            priority_score=90,
            content_preview="# My Project\nA test project.",
        ),
        ScannedFile(
            path=Path("package.json"),
            relative_path="package.json",
            extension=".json",
            size=1024,
            priority_score=85,
            content_preview='{"name": "my-project"}',
        ),
    ]

    redaction_findings = []
    if with_redactions:
        redaction_findings = [
            RedactionFinding(file_path="src/config.ts", finding_type="API_KEY", count=1),
            RedactionFinding(file_path="src/db.ts", finding_type="PASSWORD", count=2),
        ]

    file_summaries = {}
    if with_summaries:
        file_summaries = {
            "README.md": "This is a Next.js project with TypeScript.",
            "package.json": "Node.js project with React and Next.js dependencies.",
        }

    return ProjectAnalysis(
        project_path=project_path,
        file_tree="my-project/\n├── README.md\n├── package.json\n└── src/\n    └── index.ts",
        tech_stack=stack,
        important_files=important_files,
        file_summaries=file_summaries,
        module_summaries={"src": "Main source module"},
        risk_notes=["No .env.example found", "No test files detected"],
        assumptions=["Static analysis only", "File tree may be incomplete"],
        redaction_findings=redaction_findings,
        scan_metadata=meta,
        project_summary="A Next.js TypeScript project with PostgreSQL database.",
    )


# ---------------------------------------------------------------------------
# ChatGPT prompt tests
# ---------------------------------------------------------------------------

class TestChatGPTPrompt:
    def test_builds_without_error(self):
        analysis = make_analysis()
        prompt = build_chatgpt_prompt(analysis)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_contains_role_section(self):
        prompt = build_chatgpt_prompt(make_analysis())
        assert "Role" in prompt
        assert "senior Tech Lead" in prompt

    def test_contains_mission_section(self):
        prompt = build_chatgpt_prompt(make_analysis())
        assert "Mission" in prompt

    def test_contains_rules_section(self):
        prompt = build_chatgpt_prompt(make_analysis())
        assert "Rules" in prompt
        assert "Do NOT ask questions" in prompt

    def test_contains_tech_stack(self):
        prompt = build_chatgpt_prompt(make_analysis())
        assert "TypeScript" in prompt
        assert "React" in prompt

    def test_contains_analysis_phases(self):
        prompt = build_chatgpt_prompt(make_analysis())
        assert "Analysis Phases" in prompt or "phases" in prompt.lower()

    def test_contains_expected_output(self):
        prompt = build_chatgpt_prompt(make_analysis())
        assert "Expected Output" in prompt or "Executive Summary" in prompt

    def test_contains_project_path(self):
        prompt = build_chatgpt_prompt(make_analysis(project_path="/my/test/project"))
        assert "/my/test/project" in prompt

    def test_contains_redaction_info_when_present(self):
        prompt = build_chatgpt_prompt(make_analysis(with_redactions=True))
        assert "REDACTED" in prompt or "redact" in prompt.lower()

    def test_no_redaction_info_when_absent(self):
        prompt = build_chatgpt_prompt(make_analysis(with_redactions=False))
        assert "No secrets were detected" in prompt or "redact" in prompt.lower()

    def test_contains_file_tree(self):
        prompt = build_chatgpt_prompt(make_analysis())
        assert "README.md" in prompt

    def test_contains_risk_notes(self):
        prompt = build_chatgpt_prompt(make_analysis())
        assert "No .env.example found" in prompt or "risk" in prompt.lower()


# ---------------------------------------------------------------------------
# Claude prompt tests
# ---------------------------------------------------------------------------

class TestClaudePrompt:
    def test_builds_without_error(self):
        prompt = build_claude_prompt(make_analysis())
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_contains_xml_role_tag(self):
        prompt = build_claude_prompt(make_analysis())
        assert "<role>" in prompt
        assert "</role>" in prompt

    def test_contains_xml_context_tag(self):
        prompt = build_claude_prompt(make_analysis())
        assert "<context>" in prompt
        assert "</context>" in prompt

    def test_contains_xml_facts_tag(self):
        prompt = build_claude_prompt(make_analysis())
        assert "<facts>" in prompt
        assert "</facts>" in prompt

    def test_contains_xml_assumptions_tag(self):
        prompt = build_claude_prompt(make_analysis())
        assert "<assumptions>" in prompt
        assert "</assumptions>" in prompt

    def test_contains_xml_instructions_tag(self):
        prompt = build_claude_prompt(make_analysis())
        assert "<instructions>" in prompt
        assert "</instructions>" in prompt

    def test_contains_xml_output_format_tag(self):
        prompt = build_claude_prompt(make_analysis())
        assert "<output_format>" in prompt
        assert "</output_format>" in prompt

    def test_contains_tech_stack(self):
        prompt = build_claude_prompt(make_analysis())
        assert "TypeScript" in prompt

    def test_no_hidden_chain_of_thought(self):
        prompt = build_claude_prompt(make_analysis())
        # Should NOT ask for hidden reasoning
        assert "hidden chain-of-thought" not in prompt.lower()
        assert "private reasoning" not in prompt.lower()

    def test_contains_do_not_ask_questions(self):
        prompt = build_claude_prompt(make_analysis())
        assert "Do not ask questions" in prompt or "do not ask" in prompt.lower()


# ---------------------------------------------------------------------------
# Gemini prompt tests
# ---------------------------------------------------------------------------

class TestGeminiPrompt:
    def test_builds_without_error(self):
        prompt = build_gemini_prompt(make_analysis())
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_contains_numbered_sections(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "## 1." in prompt or "1. Role" in prompt

    def test_contains_role_section(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "Role" in prompt
        assert "senior Tech Lead" in prompt

    def test_contains_project_context(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "Project Context" in prompt

    def test_contains_evidence_section(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "Evidence" in prompt

    def test_contains_tasks_section(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "Tasks" in prompt

    def test_contains_constraints_section(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "Constraints" in prompt

    def test_contains_output_format(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "Output Format" in prompt

    def test_contains_final_deliverable(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "Final Deliverable" in prompt or "deliverable" in prompt.lower()

    def test_contains_tech_stack(self):
        prompt = build_gemini_prompt(make_analysis())
        assert "TypeScript" in prompt


# ---------------------------------------------------------------------------
# MiniMax prompt tests
# ---------------------------------------------------------------------------

class TestMiniMaxPrompt:
    def test_builds_without_error(self):
        prompt = build_minimax_prompt(make_analysis())
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_contains_agent_role(self):
        prompt = build_minimax_prompt(make_analysis())
        assert "Agent Role" in prompt

    def test_contains_objective(self):
        prompt = build_minimax_prompt(make_analysis())
        assert "Objective" in prompt

    def test_contains_input_summary(self):
        prompt = build_minimax_prompt(make_analysis())
        assert "Input Summary" in prompt

    def test_contains_tasks(self):
        prompt = build_minimax_prompt(make_analysis())
        assert "Tasks" in prompt

    def test_contains_priority_rules(self):
        prompt = build_minimax_prompt(make_analysis())
        assert "Priority Rules" in prompt

    def test_contains_output_format(self):
        prompt = build_minimax_prompt(make_analysis())
        assert "Output Format" in prompt

    def test_is_compact(self):
        # MiniMax should be shorter than Claude (which is verbose)
        minimax_prompt = build_minimax_prompt(make_analysis())
        claude_prompt = build_claude_prompt(make_analysis())
        # MiniMax should generally be more compact
        assert len(minimax_prompt) < len(claude_prompt) * 1.5  # reasonable bound

    def test_contains_tech_stack(self):
        prompt = build_minimax_prompt(make_analysis())
        assert "TypeScript" in prompt


# ---------------------------------------------------------------------------
# Generic prompt tests
# ---------------------------------------------------------------------------

class TestGenericPrompt:
    def test_builds_without_error(self):
        prompt = build_generic_prompt(make_analysis())
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_contains_role(self):
        prompt = build_generic_prompt(make_analysis())
        assert "Role" in prompt
        assert "senior Tech Lead" in prompt

    def test_contains_context(self):
        prompt = build_generic_prompt(make_analysis())
        assert "Context" in prompt

    def test_contains_tasks(self):
        prompt = build_generic_prompt(make_analysis())
        assert "Tasks" in prompt

    def test_contains_rules(self):
        prompt = build_generic_prompt(make_analysis())
        assert "Rules" in prompt

    def test_contains_output_format(self):
        prompt = build_generic_prompt(make_analysis())
        assert "Output Format" in prompt

    def test_contains_final_report_expectations(self):
        prompt = build_generic_prompt(make_analysis())
        assert "Final Report" in prompt or "final report" in prompt.lower()

    def test_contains_tech_stack(self):
        prompt = build_generic_prompt(make_analysis())
        assert "TypeScript" in prompt


# ---------------------------------------------------------------------------
# Prompt builder dispatcher tests
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_build_all_prompts(self):
        analysis = make_analysis()
        prompts = build_prompts(analysis, "all")
        assert set(prompts.keys()) == set(ALL_MODELS)

    def test_build_single_chatgpt(self):
        prompts = build_prompts(make_analysis(), "chatgpt")
        assert "chatgpt" in prompts
        assert len(prompts) == 1

    def test_build_single_claude(self):
        prompts = build_prompts(make_analysis(), "claude")
        assert "claude" in prompts
        assert len(prompts) == 1

    def test_build_single_gemini(self):
        prompts = build_prompts(make_analysis(), "gemini")
        assert "gemini" in prompts

    def test_build_single_minimax(self):
        prompts = build_prompts(make_analysis(), "minimax")
        assert "minimax" in prompts

    def test_build_single_generic(self):
        prompts = build_prompts(make_analysis(), "generic")
        assert "generic" in prompts

    def test_invalid_model_raises(self):
        with pytest.raises(ValueError, match="Unknown target model"):
            build_prompts(make_analysis(), "gpt-5-turbo-ultra")

    def test_all_prompts_non_empty(self):
        prompts = build_prompts(make_analysis(), "all")
        for model, prompt in prompts.items():
            assert len(prompt) > 200, f"Prompt for {model} is too short"

    def test_all_prompts_contain_common_rules(self):
        """Every prompt must include the common rules."""
        prompts = build_prompts(make_analysis(), "all")
        for model, prompt in prompts.items():
            assert "senior Tech Lead" in prompt, f"{model} missing role"
            assert "Do not" in prompt or "do not" in prompt, f"{model} missing do-not-ask rule"

    def test_prompts_contain_project_path(self):
        analysis = make_analysis(project_path="/specific/test/path")
        prompts = build_prompts(analysis, "all")
        for model, prompt in prompts.items():
            assert "/specific/test/path" in prompt, f"{model} missing project path"
