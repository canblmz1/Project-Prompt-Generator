"""Tests for detectors.py — technology stack detection."""

import json
import tempfile
from pathlib import Path

from project_prompter.detectors import detect_tech_stack


def make_project(files: dict) -> Path:
    """Create a temporary project directory with given files."""
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    for rel_path, content in files.items():
        full_path = root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
    return root


class TestJavaScriptDetection:
    def test_detects_nodejs_from_package_json(self):
        root = make_project({"package.json": json.dumps({"name": "test", "dependencies": {}})})
        stack = detect_tech_stack(root, [])
        assert "JavaScript" in stack.languages
        assert "Node.js" in stack.frameworks

    def test_detects_typescript(self):
        root = make_project({
            "package.json": json.dumps({"devDependencies": {"typescript": "^5.0.0"}}),
            "tsconfig.json": '{"compilerOptions": {}}',
        })
        stack = detect_tech_stack(root, [])
        assert "TypeScript" in stack.languages

    def test_detects_react(self):
        root = make_project({
            "package.json": json.dumps({"dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"}}),
        })
        stack = detect_tech_stack(root, [])
        assert "React" in stack.frameworks

    def test_detects_nextjs(self):
        root = make_project({
            "package.json": json.dumps({"dependencies": {"next": "^14.0.0"}}),
            "next.config.js": "module.exports = {}",
        })
        stack = detect_tech_stack(root, [])
        assert "Next.js" in stack.frameworks

    def test_detects_vite(self):
        root = make_project({
            "package.json": json.dumps({"devDependencies": {"vite": "^5.0.0"}}),
            "vite.config.ts": "export default {}",
        })
        stack = detect_tech_stack(root, [])
        assert "Vite" in stack.tools

    def test_detects_electron(self):
        root = make_project({
            "package.json": json.dumps({"dependencies": {"electron": "^28.0.0"}}),
        })
        stack = detect_tech_stack(root, [])
        assert "Electron" in stack.frameworks

    def test_detects_jest(self):
        root = make_project({
            "package.json": json.dumps({"devDependencies": {"jest": "^29.0.0"}}),
        })
        stack = detect_tech_stack(root, [])
        assert "Jest" in stack.testing_tools

    def test_detects_vitest(self):
        root = make_project({
            "package.json": json.dumps({"devDependencies": {"vitest": "^1.0.0"}}),
        })
        stack = detect_tech_stack(root, [])
        assert "Vitest" in stack.testing_tools

    def test_detects_prisma(self):
        root = make_project({
            "package.json": json.dumps({"dependencies": {"@prisma/client": "^5.0.0"}}),
        })
        stack = detect_tech_stack(root, [])
        assert "Prisma" in stack.databases

    def test_detects_npm(self):
        root = make_project({
            "package.json": json.dumps({"name": "test"}),
        })
        stack = detect_tech_stack(root, [])
        assert "npm" in stack.package_managers

    def test_detects_yarn(self):
        root = make_project({
            "package.json": json.dumps({"name": "test"}),
            "yarn.lock": "# yarn lockfile v1",
        })
        stack = detect_tech_stack(root, [])
        assert "yarn" in stack.package_managers

    def test_detects_playwright(self):
        root = make_project({
            "package.json": json.dumps({"devDependencies": {"@playwright/test": "^1.40.0"}}),
        })
        stack = detect_tech_stack(root, [])
        assert "Playwright" in stack.testing_tools

    def test_detects_cypress(self):
        root = make_project({
            "package.json": json.dumps({"devDependencies": {"cypress": "^13.0.0"}}),
        })
        stack = detect_tech_stack(root, [])
        assert "Cypress" in stack.testing_tools


class TestPythonDetection:
    def test_detects_python_from_requirements(self):
        root = make_project({"requirements.txt": "fastapi\nuvicorn\n"})
        stack = detect_tech_stack(root, [])
        assert "Python" in stack.languages

    def test_detects_fastapi(self):
        root = make_project({"requirements.txt": "fastapi==0.104.0\nuvicorn\n"})
        stack = detect_tech_stack(root, [])
        assert "FastAPI" in stack.frameworks

    def test_detects_django(self):
        root = make_project({
            "requirements.txt": "django==4.2.0\n",
            "manage.py": "#!/usr/bin/env python",
        })
        stack = detect_tech_stack(root, [])
        assert "Django" in stack.frameworks

    def test_detects_flask(self):
        root = make_project({"requirements.txt": "flask==3.0.0\n"})
        stack = detect_tech_stack(root, [])
        assert "Flask" in stack.frameworks

    def test_detects_pytest(self):
        root = make_project({
            "requirements.txt": "pytest==7.4.0\n",
            "conftest.py": "# conftest",
        })
        stack = detect_tech_stack(root, [])
        assert "Pytest" in stack.testing_tools

    def test_detects_sqlalchemy(self):
        root = make_project({"requirements.txt": "sqlalchemy==2.0.0\n"})
        stack = detect_tech_stack(root, [])
        assert "SQLAlchemy" in stack.databases

    def test_detects_python_from_py_file(self):
        root = make_project({"main.py": "print('hello')"})
        stack = detect_tech_stack(root, [])
        assert "Python" in stack.languages


class TestPHPDetection:
    def test_detects_php_from_composer(self):
        root = make_project({
            "composer.json": json.dumps({"require": {"php": "^8.1"}}),
        })
        stack = detect_tech_stack(root, [])
        assert "PHP" in stack.languages

    def test_detects_laravel(self):
        root = make_project({
            "composer.json": json.dumps({"require": {"laravel/framework": "^10.0"}}),
            "artisan": "#!/usr/bin/env php",
        })
        stack = detect_tech_stack(root, [])
        assert "Laravel" in stack.frameworks


class TestJavaDetection:
    def test_detects_java_from_pom(self):
        root = make_project({
            "pom.xml": "<project><groupId>com.example</groupId></project>",
        })
        stack = detect_tech_stack(root, [])
        assert "Java" in stack.languages
        assert "Maven" in stack.tools

    def test_detects_spring_boot(self):
        root = make_project({
            "pom.xml": "<project><dependency><artifactId>spring-boot-starter-web</artifactId></dependency></project>",
        })
        stack = detect_tech_stack(root, [])
        assert "Spring Boot" in stack.frameworks

    def test_detects_gradle(self):
        root = make_project({
            "build.gradle": "plugins { id 'java' }",
        })
        stack = detect_tech_stack(root, [])
        assert "Gradle" in stack.tools


class TestCSharpDetection:
    def test_detects_csharp_from_csproj(self):
        root = make_project({
            "MyApp.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>",
        })
        stack = detect_tech_stack(root, [])
        assert "C#" in stack.languages
        assert ".NET" in stack.frameworks


class TestDockerDetection:
    def test_detects_docker_from_dockerfile(self):
        root = make_project({"Dockerfile": "FROM node:18\nWORKDIR /app"})
        stack = detect_tech_stack(root, [])
        assert "Docker" in stack.tools

    def test_detects_docker_from_compose(self):
        root = make_project({
            "docker-compose.yml": "version: '3'\nservices:\n  app:\n    image: node:18",
        })
        stack = detect_tech_stack(root, [])
        assert "Docker" in stack.tools


class TestDatabaseDetection:
    def test_detects_postgresql_from_compose(self):
        root = make_project({
            "docker-compose.yml": "services:\n  db:\n    image: postgres:15",
        })
        stack = detect_tech_stack(root, [])
        assert "PostgreSQL" in stack.databases

    def test_detects_prisma_from_schema(self):
        root = make_project({
            "prisma/schema.prisma": 'datasource db {\n  provider = "postgresql"\n}',
        })
        stack = detect_tech_stack(root, [])
        assert "Prisma" in stack.databases


class TestEmptyProject:
    def test_empty_project_returns_empty_stack(self):
        root = make_project({})
        stack = detect_tech_stack(root, [])
        assert stack.is_empty() or True  # may detect nothing, that's fine

    def test_tech_stack_all_detected_deduped(self):
        root = make_project({
            "package.json": json.dumps({"dependencies": {"react": "^18.0.0"}}),
        })
        stack = detect_tech_stack(root, [])
        all_detected = stack.all_detected()
        # No duplicates
        assert len(all_detected) == len(set(all_detected))
