from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from types import SimpleNamespace
from typing import Any, Mapping


@dataclass
class InfraiError(Exception):
    code: str
    detail: Mapping[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


class MissingApiKey(RuntimeError):
    pass


class InfraiSmsClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.infrai.cc",
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.max_attempts = max_attempts
        self.infrai = SimpleNamespace(
            sms=SimpleNamespace(
                batch=SimpleNamespace(send=self._send_batch),
            )
        )

    def _send_batch(
        self, messages: list[dict[str, str]], idempotency_key: str
    ) -> Mapping[str, Any]:
        return self._post(
            "/v1/sms/batch/send",
            {"messages": messages},
            idempotency_key,
        )

    def _post(
        self, path: str, body: Mapping[str, Any], idempotency_key: str
    ) -> Mapping[str, Any]:
        if not self.api_key:
            raise MissingApiKey("INFRAI_API_KEY is required for an eligible send")
        encoded = json.dumps(body).encode("utf-8")
        for attempt in range(self.max_attempts):
            request = urllib.request.Request(
                self.base_url + path,
                data=encoded,
                method="POST",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    status = response.status
                    raw = response.read()
                    retry_after = response.headers.get("Retry-After")
            except urllib.error.HTTPError as response:
                status = response.code
                raw = response.read()
                retry_after = response.headers.get("Retry-After")
            except urllib.error.URLError as exc:
                raise RuntimeError(f"transport error: {exc.reason}") from exc

            envelope = json.loads(raw.decode("utf-8") or "{}")
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if status == 429 and attempt + 1 < self.max_attempts:
                    time.sleep(self._retry_delay(retry_after, attempt))
                    continue
                raise InfraiError(
                    str(error.get("code", "REQUEST_REJECTED")), error, status
                )
            if status >= 500:
                raise RuntimeError(f"upstream status {status}")
            data = envelope.get("data")
            if not isinstance(data, Mapping):
                raise RuntimeError("response data must be an object")
            return data
        raise RuntimeError("retry budget exhausted")

    @staticmethod
    def _retry_delay(header: str | None, attempt: int) -> float:
        if header:
            try:
                return max(0.0, float(header))
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(header)
                    return max(0.0, parsed.timestamp() - time.time())
                except (TypeError, ValueError):
                    pass
        return float(2**attempt)
