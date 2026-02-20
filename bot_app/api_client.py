from __future__ import annotations

from typing import Any, Optional, Tuple

import requests
from requests import Response


class WorkerApiClient:
    def __init__(self, base_url: str, bot_secret: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = {"Bot-Secret": bot_secret}

    def post(self, endpoint: str, data: Optional[dict[str, Any]] = None) -> Optional[Response]:
        payload = data or {}
        url = f"{self.base_url}{endpoint}"
        try:
            return requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException:
            return None

    def post_json(self, endpoint: str, data: Optional[dict[str, Any]] = None) -> Tuple[Optional[int], Any]:
        response = self.post(endpoint, data)
        if response is None:
            return None, None
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, None
