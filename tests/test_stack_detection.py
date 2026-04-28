from project_prompter.detectors import detect_tech_stack
from project_prompter.models import ScannedFile

def test_stack_detection_from_imports_and_docs(tmp_path):
    # Mock some ScannedFile objects representing imports and docs
    
    file1 = ScannedFile(
        path=tmp_path / "main.py",
        relative_path="main.py",
        extension=".py",
        size=100,
        content_preview="from fastapi import FastAPI\nimport celery\nimport openai"
    )
    
    file2 = ScannedFile(
        path=tmp_path / "README.md",
        relative_path="README.md",
        extension=".md",
        size=500,
        content_preview="This project uses postgresql and redis for storage. Also deepgram for audio."
    )
    
    stack = detect_tech_stack(tmp_path, [file1, file2])
    
    assert "FastAPI" in stack.frameworks
    assert "imports" in stack.sources["FastAPI"]
    
    assert "Celery" in stack.frameworks
    assert "imports" in stack.sources["Celery"]
    
    assert "OpenAI" in stack.ai_services
    assert "imports" in stack.sources["OpenAI"]
    
    assert "PostgreSQL" in stack.databases
    assert "docs" in stack.sources["PostgreSQL"]
    
    assert "Redis" in stack.databases
    assert "docs" in stack.sources["Redis"]
    
    assert "Deepgram" in stack.ai_services
    assert "docs" in stack.sources["Deepgram"]

def test_tech_stack_all_detected():
    from project_prompter.models import TechStack
    stack = TechStack()
    stack.add_item("languages", "Python", "config")
    stack.add_item("ai_services", "Gemini", "imports")
    
    all_det = stack.all_detected()
    assert "Python" in all_det
    assert "Gemini" in all_det

