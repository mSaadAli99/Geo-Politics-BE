"""HTTP session with timeouts, retries, and a custom user agent."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "GeoPoliticsAI/1.0 (educational geopolitics research; contact: local-dev)"
TIMEOUT_SECONDS = 10


def build_session() -> requests.Session:
    """Session that retries three times with backoff on transient failures."""
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = USER_AGENT
    return session
