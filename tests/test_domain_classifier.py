import pytest
from project_prompter.domain_classifier import detect_domain

def build_deps(words):
    return [words]

def test_generic_project_no_special_domain_section():
    result = detect_domain(
        project_path_str="my_random_project",
        file_paths=["src/main.py", "utils.js"],
        structural_summaries={"src/main.py": "def do_something(): pass"},
        dependencies=["pytest", "requests"],
        markdown_contents={}
    )
    assert result.domain == "generic"
    assert result.confidence == "low"

def test_generic_api_terms_do_not_trigger_domain():
    # Only generic terms and weak indicators
    result = detect_domain(
        project_path_str="api_server",
        file_paths=["src/auth.py", "src/payment.py", "src/billing.py"],
        structural_summaries={"src/auth.py": "api_key, token, password, risk, budget"},
        dependencies=["fastapi", "redis", "celery"],
        markdown_contents={"README.md": "queue worker job webhook websocket"}
    )
    # They might give some score to ecommerce or fintech due to weak indicators,
    # but without strong indicators, generic should be selected.
    assert result.domain == "generic"

def test_voice_project_detects_audio_ai_saas():
    result = detect_domain(
        project_path_str="ses_analizi_projesi",
        file_paths=["app/audio_upload.py", "transcription.py", "temp_audios/test.mp3"],
        structural_summaries={"app/audio_upload.py": "def upload(): pass"},
        dependencies=["deepgram", "fastapi"],
        markdown_contents={"README.md": "Voice analysis and PDF report generation"}
    )
    assert result.domain == "audio_ai_saas"
    assert result.confidence in ["medium", "high"]

def test_voice_project_does_not_detect_trading():
    result = detect_domain(
        project_path_str="ses_analizi_projesi",
        file_paths=["app/audio_upload.py"],
        structural_summaries={},
        dependencies=["deepgram", "fastapi"],
        markdown_contents={"README.md": "Voice analysis budget risk api_key order"}
    )
    assert result.domain == "audio_ai_saas"

def test_binance_project_detects_trading_fintech():
    result = detect_domain(
        project_path_str="binance_bot",
        file_paths=["src/trading_bot.py", "src/execution.py"],
        structural_summaries={"src/trading_bot.py": "def market_order(): pass"},
        dependencies=["ccxt", "binance"],
        markdown_contents={"README.md": "spot trading and futures kill switch"}
    )
    assert result.domain == "trading_fintech"
    assert result.confidence in ["medium", "high"]

def test_ecommerce_project_detects_ecommerce():
    result = detect_domain(
        project_path_str="shop_backend",
        file_paths=["src/cart.py", "src/checkout.py"],
        structural_summaries={"src/cart.py": "def add_product_catalog(): pass"},
        dependencies=["stripe"],
        markdown_contents={"README.md": "stripe checkout, inventory, sku"}
    )
    assert result.domain == "ecommerce"

def test_cms_project_detects_content_cms():
    result = detect_domain(
        project_path_str="blog_engine",
        file_paths=["src/post_editor.py"],
        structural_summaries={},
        dependencies=[],
        markdown_contents={"README.md": "content management taxonomy category draft post publish workflow"}
    )
    assert result.domain == "content_cms"

def test_devtool_project_detects_devtool():
    result = detect_domain(
        project_path_str="repo_analyzer",
        file_paths=["src/static_analyzer.py"],
        structural_summaries={},
        dependencies=[],
        markdown_contents={"README.md": "developer tool for code quality and prompt generator"}
    )
    assert result.domain == "devtool"

def test_weak_indicators_alone_do_not_trigger_domain():
    # Only weak indicators for trading: risk, budget, api_key, reconciliation, rate_limit, websocket, order
    result = detect_domain(
        project_path_str="custom_app",
        file_paths=["src/reconciliation.py", "src/order_processor.py"],
        structural_summaries={"src/order_processor.py": "def handle_order(): pass"},
        dependencies=["websockets"],
        markdown_contents={"README.md": "This app handles rate_limit and budget risk."}
    )
    # Even if score is high from weak indicators, strong_indicator_count is 0 -> special domain needs >= 2
    assert result.domain == "generic"

def test_domain_metadata_present_in_prompt():
    from project_prompter.prompt_templates._common import build_analysis_metadata
    from project_prompter.models import ProjectAnalysis, ScanMetadata, DomainDetectionResult, TechStack
    
    meta = ScanMetadata("123", "2024", "path", mode="fast")
    domain = DomainDetectionResult("audio_ai_saas", "high", 15, 4, ["deepgram", "transcribe"], [])
    analysis = ProjectAnalysis("/path", "", TechStack(), [], {}, {}, [], [], [], meta, "", domain_result=domain)
    
    metadata_text = build_analysis_metadata(analysis)
    assert "| Detected Domain | audio_ai_saas |" in metadata_text
    assert "| Domain Confidence | high |" in metadata_text
    assert "| Domain Score | 15 |" in metadata_text
    assert "| Domain Indicators | deepgram, transcribe |" in metadata_text

def test_generic_prompt_has_no_special_domain_section():
    from project_prompter.prompt_templates._common import build_special_domain_section
    from project_prompter.models import ProjectAnalysis, ScanMetadata, DomainDetectionResult, TechStack
    
    domain = DomainDetectionResult("generic", "low", 0, 0, [], [])
    analysis = ProjectAnalysis("/path", "", TechStack(), [], {}, {}, [], [], [], None, "", domain_result=domain)
    
    section = build_special_domain_section(analysis)
    assert section == ""
