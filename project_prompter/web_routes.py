"""Route-level helpers for web API composition."""

from __future__ import annotations

HEALTH_PATH = "/api/health"
ANALYZE_PATH = "/api/analyze"
RESULTS_PATH = "/api/results/{scan_id}"
DOWNLOAD_PATH = "/api/download/{scan_id}/{filename:path}"
