"""Sprint feature coverage for language support, data science, truncation, version, and dry-run."""

from pathlib import Path

import pytest

from project_prompter.analyzer import analyze_project
from project_prompter.cli import _resolve_options, create_parser
from project_prompter.domain_classifier import detect_domain
from project_prompter.filters import is_allowed_extension
from project_prompter.models import ProjectAnalysis, ScanMetadata, ScanOptions, TechStack
from project_prompter.prompt_templates._common import build_special_domain_section
from project_prompter.scanner import _safe_read
from project_prompter.structural_analyzer import build_structural_summary


def test_rust_go_ruby_extensions_are_allowed():
    assert is_allowed_extension(Path("src/main.rs")) is True
    assert is_allowed_extension(Path("cmd/server.go")) is True
    assert is_allowed_extension(Path("app/models/user.rb")) is True


def test_go_structural_summary_extracts_key_shapes():
    content = """
package main

import (
    "net/http"
    "os"
)

type Server struct {}

const (
    DefaultPort = "8080"
)

func handler(w http.ResponseWriter, r *http.Request) {
    _ = os.Getenv("DATABASE_URL")
}

func main() {
    r.Get("/health", handler)
}
"""
    summary = build_structural_summary(Path("main.go"), "main.go", content, 512, 75)

    assert "Type: Go source" in summary
    assert "Package:" in summary
    assert "main" in summary
    assert "net/http" in summary
    assert "Server struct" in summary
    assert "handler(" in summary
    assert "GET /health" in summary
    assert "DATABASE_URL" in summary
    assert "(empty or no extractable structure)" not in summary


def test_rust_structural_summary_extracts_key_shapes():
    content = """
use std::env;
use serde::Serialize;

pub mod config;

pub struct AppConfig {
    name: String,
}

enum Command {
    Run,
}

trait Service {
    fn execute(&self);
}

impl Service for AppConfig {
    fn execute(&self) {}
}

pub async fn run() {
    let _ = env::var("API_KEY");
    let _client = reqwest::Client::new();
}
"""
    summary = build_structural_summary(Path("lib.rs"), "src/lib.rs", content, 512, 75)

    assert "Type: Rust source" in summary
    assert "std::env" in summary
    assert "config" in summary
    assert "AppConfig struct" in summary
    assert "Command enum" in summary
    assert "Service trait" in summary
    assert "pub async run(" in summary
    assert "API_KEY" in summary
    assert "HTTP/network calls" in summary
    assert "(empty or no extractable structure)" not in summary


def test_ruby_structural_summary_extracts_key_shapes():
    content = """
require "sinatra/base"

module Admin
  class User < ApplicationRecord
    attr_accessor :name
    belongs_to :account

    def self.active(limit = 10)
      ENV.fetch("DATABASE_URL")
    end
  end
end

get "/health" do
  "ok"
end

resources :users
"""
    summary = build_structural_summary(Path("user.rb"), "app/models/user.rb", content, 512, 80)

    assert "Type: Ruby source" in summary
    assert "sinatra/base" in summary
    assert "Admin" in summary
    assert "User < ApplicationRecord" in summary
    assert "self.active(" in summary
    assert "attr_accessor :name" in summary
    assert "belongs_to :account" in summary
    assert "GET /health" in summary
    assert "RESOURCES users" in summary
    assert "DATABASE_URL" in summary
    assert "(empty or no extractable structure)" not in summary


def test_data_science_domain_and_special_section():
    result = detect_domain(
        project_path_str="ml_project",
        file_paths=["notebooks/analysis.ipynb", "src/train.py"],
        structural_summaries={
            "src/train.py": "Imports:\n  - pandas\n  - numpy\nFunctions:\n  - train_model()"
        },
        dependencies=["pandas", "numpy", "jupyter"],
        markdown_contents={"README.md": "Model training with feature engineering and mlflow."},
    )

    assert result.domain == "data_science"
    assert result.confidence in ("medium", "high")

    analysis = ProjectAnalysis(
        project_path="/tmp/ml_project",
        file_tree="",
        tech_stack=TechStack(),
        scan_metadata=ScanMetadata("1", "2026", "/tmp/ml_project"),
        domain_result=result,
    )
    section = build_special_domain_section(analysis)
    assert "Data Science / Machine Learning" in section
    assert "PII" in section
    assert "MLOps" in section


def test_safe_read_keeps_head_and_tail_for_large_files(tmp_path):
    file_path = tmp_path / "large.txt"
    file_path.write_text("H" * 70 + "M" * 60 + "T" * 30, encoding="utf-8")

    content, error = _safe_read(file_path, max_chars=100)

    assert error is None
    assert len(content) <= 100
    assert content.startswith("H" * 37)
    assert content.endswith("T" * 17)
    assert "M" * 20 not in content
    assert "... [ORTA KISIM ATILDI \u2014 106 karakter] ..." in content


def test_safe_read_leaves_small_files_unchanged(tmp_path):
    file_path = tmp_path / "small.txt"
    file_path.write_text("short content", encoding="utf-8")

    content, error = _safe_read(file_path, max_chars=100)

    assert error is None
    assert content == "short content"


def test_exporters_and_web_use_imported_version(monkeypatch):
    import project_prompter.exporters as exporters
    import project_prompter.web as web

    monkeypatch.setattr(exporters, "__version__", "9.9.9")
    analysis = ProjectAnalysis(
        project_path="/tmp/project",
        file_tree="project/\n  main.py",
        tech_stack=TechStack(),
    )

    assert "v9.9.9" in exporters._build_file_tree_md(analysis)

    if not web.WEB_AVAILABLE:
        pytest.skip("FastAPI not available")

    monkeypatch.setattr(web, "__version__", "9.9.9")
    app = web.create_app()
    assert app.version == "9.9.9"


def test_cli_resolves_dry_run_flag():
    args = create_parser().parse_args(["/tmp/project", "--dry-run"])
    assert args.dry_run is True

    options = _resolve_options(args)
    assert options.dry_run is True


def test_analyze_project_dry_run_writes_no_files(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("import pandas as pd\nprint(pd.__version__)\n", encoding="utf-8")
    output_path = tmp_path / "out"
    logs: list[str] = []

    options = ScanOptions(
        project_path=project,
        output_path=output_path,
        max_files=10,
        max_chars_per_file=1000,
        use_ollama=True,
        target_model="generic",
        dry_run=True,
    )

    analysis = analyze_project(options, progress_callback=logs.append)

    assert output_path.exists() is False
    assert analysis.important_files
    assert analysis.scan_metadata is not None
    assert analysis.scan_metadata.ollama_used is False
    assert any("[DRY RUN] Files selected for analysis" in msg for msg in logs)
    assert any("Detected technologies:" in msg for msg in logs)
    assert any("Estimated output files: 7" in msg for msg in logs)
