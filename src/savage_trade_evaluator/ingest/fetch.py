"""One way to fetch JSON for the ingests that need it to be dependable.

From the sandbox, large or busy responses sometimes arrive truncated. ``urllib``
failed 23 of 30 roster requests that way; ``httpx`` failed none on the same
endpoints. This client is ``httpx`` (gzip on by default) and retries what is worth
retrying: truncated or dropped connections, bodies that are not valid JSON, 429 and 5xx.
A 4xx other than 429 is the caller's mistake and is raised at once.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; savage-trade-evaluator/0.1; research only)"}
TIMEOUT_SECONDS = 40.0


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """A client with the project's headers, a timeout and redirects followed."""
    return httpx.Client(
        headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True, transport=transport
    )


def get_json(client: httpx.Client, url: str, *, retries: int = 5, backoff: float = 0.8) -> Any:
    """GET ``url`` and return the parsed JSON, retrying transient failures.

    Args:
        client: Client from :func:`make_client`.
        url: Absolute URL.
        retries: Attempts before giving up.
        backoff: Seconds to wait after the first failure; grows linearly.

    Returns:
        The decoded JSON body.

    Raises:
        httpx.HTTPStatusError: For a 4xx other than 429, immediately.
        RuntimeError: When every attempt failed, naming the last error.
    """
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.get(url)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                raise
            last = exc
        except (httpx.TransportError, json.JSONDecodeError) as exc:
            last = exc
        logger.warning("attempt %d/%d for %s failed: %s", attempt, retries, url, last)
        time.sleep(backoff * attempt)
    raise RuntimeError(f"{url} failed after {retries} attempts: {last}")
