from project_prompter import web_security


def test_analyze_rate_limit_blocks_when_limit_reached(monkeypatch):
    web_security._analyze_window.clear()
    monkeypatch.setenv(web_security.ANALYZE_RATE_LIMIT_PER_MIN_ENV, "2")

    web_security.enforce_analyze_rate_limit()
    web_security.enforce_analyze_rate_limit()

    try:
        web_security.enforce_analyze_rate_limit()
        raised = False
    except ValueError as exc:
        raised = True
        assert "rate limit exceeded" in str(exc)

    assert raised


def test_analyze_rate_limit_disabled_with_non_positive_value(monkeypatch):
    web_security._analyze_window.clear()
    monkeypatch.setenv(web_security.ANALYZE_RATE_LIMIT_PER_MIN_ENV, "0")

    for _ in range(10):
        web_security.enforce_analyze_rate_limit()
