"""Domain classifier to detect the specific domain of a project."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Optional

from .models import DomainDetectionResult

# ---------------------------------------------------------------------------
# Domain Indicators Configuration
# ---------------------------------------------------------------------------

@dataclass
class DomainConfig:
    name: str
    strong_indicators: List[str]
    weak_indicators: List[str]

# The words below are considered generic SaaS / tech words. 
# They shouldn't trigger any specific domain by themselves.
_GENERIC_WORDS = {
    "api_key", "token", "secret", "password", "risk", "budget", "cost", "billing",
    "usage", "rate_limit", "rate limiter", "auth", "jwt", "redis", "queue", "worker",
    "job", "websocket", "reconciliation", "order", "dashboard", "admin", "user",
    "subscription", "payment", "gemini", "openrouter", "fastapi", "celery", "s3",
    "signed url", "pdf", "github", "pytest", "docker", "cli", "config", "cache",
    "upload", "image", "editor"
}

DOMAINS: List[DomainConfig] = [
    DomainConfig(
        name="trading_fintech",
        strong_indicators=[
            "binance", "coinbase", "bybit", "kraken", "crypto exchange", "trading bot",
            "spot trading", "futures", "market order", "limit order", "stop loss",
            "take profit", "position sizing", "trade execution", "order execution",
            "trade journal", "open position", "close position", "portfolio", "pnl",
            "profit and loss", "exchange websocket"
        ],
        weak_indicators=[
            "risk", "budget", "api_key", "reconciliation", "rate_limit", "websocket", "order"
        ]
    ),
    DomainConfig(
        name="audio_ai_saas",
        strong_indicators=[
            "audio upload", "audio file", "voice analysis", "ses analizi", "speech-to-text",
            "transcription", "transcript", "transcribe", "deepgram", "whisper", "diarization",
            "speaker diarization", "audio analysis", "pdf report", "report generation from transcript",
            "llm analysis of transcript", "temp_audios", "background transcription"
        ],
        weak_indicators=[
            "gemini", "openrouter", "fastapi", "celery", "redis", "s3", "signed url", "pdf",
            "rate limiting", "usage tracking", "billing"
        ]
    ),
    DomainConfig(
        name="ecommerce",
        strong_indicators=[
            "cart", "checkout", "product catalog", "inventory", "sku", "order item",
            "shipment", "shipping address", "payment intent", "stripe checkout", "coupon",
            "discount", "merchant"
        ],
        weak_indicators=[
            "payment", "order", "user", "admin", "dashboard", "billing"
        ]
    ),
    DomainConfig(
        name="content_cms",
        strong_indicators=[
            "article", "post editor", "page builder", "cms", "content management", "slug",
            "taxonomy", "category", "author profile", "publish workflow", "draft post",
            "media library"
        ],
        weak_indicators=[
            "admin", "dashboard", "user", "upload", "image", "editor"
        ]
    ),
    DomainConfig(
        name="devtool",
        strong_indicators=[
            "code analysis", "project scanner", "prompt generator", "static analyzer",
            "developer tool", "cli tool", "ast parser", "source scanner", "repo analyzer",
            "lint", "code quality"
        ],
        weak_indicators=[
            "github", "pytest", "docker", "cli", "config", "cache"
        ]
    )
]

# ---------------------------------------------------------------------------
# Scoring System
# ---------------------------------------------------------------------------
# Strong indicator in project name/path: +5
# Strong indicator in file path: +5
# Strong indicator in class/function name: +4
# Strong indicator in markdown heading/title: +4
# Strong indicator in dependency/import/config: +3
# Strong indicator in structural summary/body preview: +2
# Weak indicator: +1

def _match_indicator(text: str, indicator: str) -> bool:
    """Check if an indicator (which may be multi-word) is in the text."""
    # Use word boundary or direct substring if it contains spaces/special chars
    if not text or not indicator:
        return False
    # Simple lowercase substring match is robust enough for these indicators,
    # but we should ensure we don't match partial innocent words if indicator is a single short word.
    text_lower = text.lower()
    indicator_lower = indicator.lower()
    
    if len(indicator_lower) <= 4 and indicator_lower.isalpha():
        # Short words need word boundary to avoid partial matches (e.g. 'sku' in 'askubuntu')
        pattern = r'\b' + re.escape(indicator_lower) + r'\b'
        return bool(re.search(pattern, text_lower))
    else:
        return indicator_lower in text_lower

def detect_domain(
    project_path_str: str,
    file_paths: List[str],
    structural_summaries: Dict[str, str],
    dependencies: List[str],
    markdown_contents: Dict[str, str]
) -> DomainDetectionResult:
    """
    Detect the project domain based on scoring heuristics.
    
    Args:
        project_path_str: The base directory of the project.
        file_paths: List of all files in the project (including ignored ones if applicable).
        structural_summaries: Dict of relative_path to structural summary content.
        dependencies: Flat list of detected dependencies/imports.
        markdown_contents: Dict of relative_path to markdown file contents.
    """
    project_name = Path(project_path_str).name
    
    domain_scores: Dict[str, int] = {}
    domain_strong_counts: Dict[str, int] = {}
    domain_matched: Dict[str, Set[str]] = {}
    domain_evidence: Dict[str, List[str]] = {}
    
    for d in DOMAINS:
        domain_scores[d.name] = 0
        domain_strong_counts[d.name] = 0
        domain_matched[d.name] = set()
        domain_evidence[d.name] = []
        
    for d in DOMAINS:
        c_name = d.name
        
        def add_score(indicator: str, points: int, is_strong: bool, source: str):
            domain_scores[c_name] += points
            domain_matched[c_name].add(indicator)
            domain_evidence[c_name].append(f"[{'Strong' if is_strong else 'Weak'}] '{indicator}' in {source} (+{points})")
            if is_strong:
                domain_strong_counts[c_name] += 1
                
        # 1. Project name/path (+5 strong, +1 weak)
        for ind in d.strong_indicators:
            if _match_indicator(project_name, ind):
                add_score(ind, 5, True, "project name")
        for ind in d.weak_indicators:
            if _match_indicator(project_name, ind):
                add_score(ind, 1, False, "project name")
                
        # 2. File paths (+5 strong, +1 weak)
        for fp in file_paths:
            for ind in d.strong_indicators:
                if _match_indicator(fp, ind):
                    add_score(ind, 5, True, f"file path ({fp})")
            for ind in d.weak_indicators:
                if _match_indicator(fp, ind):
                    add_score(ind, 1, False, f"file path ({fp})")
                    
        # 3. Structural summaries (classes/functions +4, body/other +2 strong, +1 weak)
        for fp, summary in structural_summaries.items():
            # Rough split: if it's Classes/Functions, give +4, else +2
            is_class_func = "Classes:" in summary or "Functions:" in summary or "Async Functions:" in summary
            for ind in d.strong_indicators:
                if _match_indicator(summary, ind):
                    points = 4 if is_class_func else 2
                    source = f"structure ({'classes/funcs' if is_class_func else 'body'}) in {fp}"
                    add_score(ind, points, True, source)
            for ind in d.weak_indicators:
                if _match_indicator(summary, ind):
                    add_score(ind, 1, False, f"structure in {fp}")
                    
        # 4. Markdown contents (+4 strong, +1 weak)
        for fp, content in markdown_contents.items():
            for ind in d.strong_indicators:
                if _match_indicator(content, ind):
                    add_score(ind, 4, True, f"markdown content in {fp}")
            for ind in d.weak_indicators:
                if _match_indicator(content, ind):
                    add_score(ind, 1, False, f"markdown content in {fp}")
                    
        # 5. Dependencies (+3 strong, +1 weak)
        dep_text = " ".join(dependencies)
        for ind in d.strong_indicators:
            if _match_indicator(dep_text, ind):
                add_score(ind, 3, True, "dependencies/imports")
        for ind in d.weak_indicators:
            if _match_indicator(dep_text, ind):
                add_score(ind, 1, False, "dependencies/imports")

    # Selection Algorithm
    best_domain = "generic"
    best_score = -1
    best_strong_count = -1
    best_confidence = "low"
    
    candidates = []
    
    for d in DOMAINS:
        score = domain_scores[d.name]
        strong_count = domain_strong_counts[d.name]
        
        # Determine confidence
        if score >= 12 and strong_count >= 3:
            confidence = "high"
        elif score >= 8 and strong_count >= 2:
            confidence = "medium"
        else:
            confidence = "low"
            
        # Rule: Special domain seçmek için score >= 8 AND strong_indicator_count >= 2 AND confidence != low
        if score >= 8 and strong_count >= 2 and confidence != "low":
            candidates.append({
                "name": d.name,
                "score": score,
                "strong_count": strong_count,
                "confidence": confidence,
                "matched": list(domain_matched[d.name]),
                "evidence": domain_evidence[d.name]
            })
            
    if not candidates:
        return DomainDetectionResult(
            domain="generic",
            confidence="low",
            score=0,
            strong_indicator_count=0,
            matched_indicators=[],
            evidence=[]
        )
        
    # Sort candidates according to rules:
    # 5. En yüksek score'u seç.
    # 6. Score eşitse strong_indicator_count yüksek olanı seç.
    # 7. Hâlâ eşitse confidence yüksek olanı seç (high > medium).
    # Confidence numeric sort mapping:
    conf_val = {"high": 2, "medium": 1, "low": 0}
    
    candidates.sort(key=lambda x: (x["score"], x["strong_count"], conf_val[x["confidence"]]), reverse=True)
    
    winner = candidates[0]
    
    return DomainDetectionResult(
        domain=winner["name"],
        confidence=winner["confidence"],
        score=winner["score"],
        strong_indicator_count=winner["strong_count"],
        matched_indicators=winner["matched"],
        evidence=winner["evidence"]
    )
