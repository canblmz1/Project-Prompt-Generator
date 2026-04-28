"""Tests for prioritizer.py — file prioritization."""

from pathlib import Path

from project_prompter.models import ScannedFile
from project_prompter.prioritizer import compute_priority_score, prioritize_files


def make_file(relative_path: str, size: int = 1000) -> ScannedFile:
    return ScannedFile(
        path=Path(relative_path),
        relative_path=relative_path,
        extension=Path(relative_path).suffix,
        size=size,
    )


class TestComputePriorityScore:
    def test_readme_high_priority(self):
        score = compute_priority_score("README.md")
        assert score >= 80

    def test_package_json_high_priority(self):
        score = compute_priority_score("package.json")
        assert score >= 80

    def test_dockerfile_high_priority(self):
        score = compute_priority_score("Dockerfile")
        assert score >= 80

    def test_main_ts_high_priority(self):
        score = compute_priority_score("src/main.ts")
        assert score >= 70

    def test_index_js_high_priority(self):
        score = compute_priority_score("src/index.js")
        assert score >= 70

    def test_auth_file_high_priority(self):
        score = compute_priority_score("src/auth.ts")
        assert score >= 65

    def test_routes_file_high_priority(self):
        score = compute_priority_score("src/routes.ts")
        assert score >= 65

    def test_schema_prisma_high_priority(self):
        score = compute_priority_score("prisma/schema.prisma")
        assert score >= 75

    def test_middleware_file_priority(self):
        score = compute_priority_score("src/middleware.ts")
        assert score >= 60

    def test_service_file_priority(self):
        score = compute_priority_score("src/user.service.ts")
        assert score >= 50

    def test_test_file_lower_priority(self):
        score = compute_priority_score("src/app.test.ts")
        assert score >= 30

    def test_minified_file_low_priority(self):
        score = compute_priority_score("dist/bundle.min.js")
        assert score <= 10

    def test_generated_file_low_priority(self):
        score = compute_priority_score("generated/types.ts")
        assert score <= 10

    def test_random_file_default_priority(self):
        score = compute_priority_score("src/helpers/string-utils.ts")
        assert score >= 10  # at least default

    def test_tsconfig_high_priority(self):
        score = compute_priority_score("tsconfig.json")
        assert score >= 75

    def test_docker_compose_high_priority(self):
        score = compute_priority_score("docker-compose.yml")
        assert score >= 80


class TestPrioritizeFiles:
    def test_returns_max_files(self):
        files = [make_file(f"src/file{i}.ts") for i in range(200)]
        result = prioritize_files(files, max_files=50)
        assert len(result) <= 50

    def test_high_priority_files_first(self):
        files = [
            make_file("src/random-util.ts"),
            make_file("README.md"),
            make_file("package.json"),
            make_file("src/auth.ts"),
        ]
        result = prioritize_files(files, max_files=10)
        # README and package.json should be near the top
        top_paths = [f.relative_path for f in result[:3]]
        assert "README.md" in top_paths or "package.json" in top_paths

    def test_assigns_priority_scores(self):
        files = [make_file("README.md"), make_file("src/utils.ts")]
        result = prioritize_files(files, max_files=10)
        for f in result:
            assert f.priority_score > 0

    def test_empty_list(self):
        result = prioritize_files([], max_files=10)
        assert result == []

    def test_fewer_files_than_max(self):
        files = [make_file(f"src/file{i}.ts") for i in range(5)]
        result = prioritize_files(files, max_files=50)
        assert len(result) == 5

    def test_sorted_descending(self):
        files = [
            make_file("src/random.ts"),
            make_file("README.md"),
            make_file("src/main.ts"),
        ]
        result = prioritize_files(files, max_files=10)
        scores = [f.priority_score for f in result]
        assert scores == sorted(scores, reverse=True)
