"""Shared HTTP plumbing for the external API adapters."""
from typing import Any, Optional

import httpx

from app.exceptions import ApiClientError


class BaseApiClient:
    def __init__(self, base_url: str, timeout: float = 10.0, http_client: Optional[httpx.Client] = None):
        # http_client can be injected in tests (e.g. httpx.MockTransport).
        self._http = http_client or httpx.Client(
            base_url=base_url, timeout=timeout, transport=httpx.HTTPTransport(retries=2))

    def _request(self, method: str, url: str, **kwargs) -> Any:
        try:
            resp = self._http.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiClientError(f"{self.__class__.__name__} {method} {url} failed: {exc}") from exc
