"""Client for Sarvam's REST speech-to-text API (``POST /speech-to-text``).

Retries 429, 5xx and network errors with exponential backoff (honouring
``Retry-After``) and allows at most ``max_concurrency`` requests at once,
shared by every caller of the same client. Neither the API key nor audio is
ever logged.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://api.sarvam.ai/speech-to-text"
DEFAULT_MODEL = "saaras:v4"
DEFAULT_MODE = "codemix"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class SarvamError(RuntimeError):
    """Sarvam refused or failed the request. ``status`` is Sarvam's HTTP status (None: network)."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass
class SarvamResult:
    transcript: str
    language_code: Optional[str]
    # Phrase-level timestamps: (text, start_s, end_s) relative to the chunk.
    phrases: list[tuple[str, float, float]] = field(default_factory=list)


def parse_response(body: dict) -> SarvamResult:
    """Read ``transcript``, ``language_code`` and the parallel ``timestamps`` arrays."""
    transcript = (body.get("transcript") or "").strip()
    phrases: list[tuple[str, float, float]] = []
    ts = body.get("timestamps") or {}
    words = ts.get("words") or []
    starts = ts.get("start_time_seconds") or []
    ends = ts.get("end_time_seconds") or []
    if words and len(words) == len(starts) == len(ends):
        for text, start, end in zip(words, starts, ends):
            try:
                start_f, end_f = float(start), float(end)
            except (TypeError, ValueError):
                phrases = []
                break
            text = (text or "").strip()
            if text:
                phrases.append((text, start_f, max(start_f, end_f)))
    return SarvamResult(transcript=transcript, language_code=body.get("language_code"), phrases=phrases)


class SarvamClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        url: str = API_URL,
        max_concurrency: int = 3,
        max_attempts: int = 5,
        base_delay_s: float = 1.0,
        max_delay_s: float = 30.0,
        timeout_s: float = 60.0,
        http: Optional[httpx.AsyncClient] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if not api_key:
            raise ValueError("SARVAM_API_KEY is not set")
        self._api_key = api_key
        self.model = model or os.environ.get("SARVAM_MODEL") or DEFAULT_MODEL
        self.mode = mode or os.environ.get("SARVAM_MODE") or DEFAULT_MODE
        self._url = url
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_attempts = max_attempts
        self._base_delay = base_delay_s
        self._max_delay = max_delay_s
        self._timeout = timeout_s
        # trust_env=False: the key must go only to Sarvam, never via an ambient proxy.
        self._http = http or httpx.AsyncClient(timeout=timeout_s, follow_redirects=False, trust_env=False)
        self._sleep = sleep

    def __repr__(self) -> str:  # never show the key
        return f"SarvamClient(model={self.model!r}, mode={self.mode!r})"

    async def aclose(self) -> None:
        await self._http.aclose()

    def _delay(self, attempt: int, retry_after: Optional[str]) -> float:
        if retry_after:
            try:
                return min(self._max_delay, max(0.0, float(retry_after)))
            except ValueError:
                pass
        backoff = self._base_delay * (2 ** (attempt - 1))
        return min(self._max_delay, backoff + random.uniform(0, self._base_delay / 2))

    async def transcribe(
        self, wav: bytes, *, language_code: str, keyterms: Optional[list[str]] = None
    ) -> SarvamResult:
        data = {
            "model": self.model,
            "mode": self.mode,
            "language_code": language_code,
            "with_timestamps": "true",
        }
        if keyterms:
            data["keyterms"] = json.dumps(keyterms, ensure_ascii=False)
        headers = {"api-subscription-key": self._api_key}
        async with self._semaphore:
            for attempt in range(1, self._max_attempts + 1):
                retry_after = None
                try:
                    response = await self._http.post(
                        self._url,
                        headers=headers,
                        data=data,
                        files={"file": ("chunk.wav", wav, "audio/wav")},
                        timeout=self._timeout,
                    )
                except httpx.HTTPError as exc:
                    status, reason = None, type(exc).__name__
                else:
                    if response.status_code < 300:
                        try:
                            return parse_response(response.json())
                        except ValueError as exc:
                            raise SarvamError("Sarvam returned a response that is not JSON", 502) from exc
                    status, reason = response.status_code, f"HTTP {response.status_code}"
                    retry_after = response.headers.get("retry-after")
                    if status not in RETRY_STATUSES:
                        raise SarvamError(f"Sarvam rejected the request ({reason}): {_safe_detail(response)}", status)
                if attempt == self._max_attempts:
                    raise SarvamError(f"Sarvam failed after {attempt} attempts ({reason})", status)
                delay = self._delay(attempt, retry_after)
                logger.warning("Sarvam %s; retry %d/%d in %.1f s", reason, attempt, self._max_attempts - 1, delay)
                await self._sleep(delay)
        raise AssertionError("unreachable")


def _safe_detail(response: httpx.Response) -> str:
    """Sarvam's error message, shortened. It describes the request, not the audio or key."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)[:200]
        return str(body.get("message") or body.get("detail") or body)[:200]
    return str(body)[:200]
