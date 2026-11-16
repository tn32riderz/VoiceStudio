"""Sarvam HTTP client: request shape, retries, concurrency, no key in logs."""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from tools.sarvam_asr_proxy.sarvam import SarvamClient, SarvamError, parse_response

KEY = "sk_test_DO_NOT_LOG_0123456789"


def run(coro):
    return asyncio.run(coro)


def make_client(handler, **kwargs):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = SarvamClient(KEY, http=http, sleep=fake_sleep, **kwargs)
    return client, sleeps


OK_BODY = {
    "request_id": "r1",
    "transcript": "இது ஒரு Figma demo",
    "language_code": "ta-IN",
    "timestamps": {"words": ["இது ஒரு", "Figma demo"], "start_time_seconds": [0.2, 1.4], "end_time_seconds": [1.3, 2.6]},
}


def test_request_fields_and_auth_header():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("api-subscription-key")
        seen["body"] = request.read()
        return httpx.Response(200, json=OK_BODY)

    client, _ = make_client(handler)
    result = run(client.transcribe(b"RIFF....", language_code="ta-IN", keyterms=["Figma", "React"]))
    assert seen["url"] == "https://api.sarvam.ai/speech-to-text"
    assert seen["key"] == KEY
    body = seen["body"]
    for field, value in [("model", b"saaras:v4"), ("mode", b"codemix"), ("language_code", b"ta-IN"), ("with_timestamps", b"true")]:
        assert b'name="' + field.encode() + b'"\r\n\r\n' + value in body
    assert b'name="keyterms"\r\n\r\n' + json.dumps(["Figma", "React"]).encode() in body
    assert b'name="file"; filename="chunk.wav"' in body
    assert result.phrases == [("இது ஒரு", 0.2, 1.3), ("Figma demo", 1.4, 2.6)]
    assert result.language_code == "ta-IN"


def test_model_and_mode_overridable_by_env(monkeypatch):
    monkeypatch.setenv("SARVAM_MODEL", "saaras:v3")
    monkeypatch.setenv("SARVAM_MODE", "transcribe")
    client, _ = make_client(lambda r: httpx.Response(200, json=OK_BODY))
    assert (client.model, client.mode) == ("saaras:v3", "transcribe")


def test_retries_429_and_5xx_then_succeeds():
    replies = iter([httpx.Response(429, headers={"retry-after": "2"}), httpx.Response(503), httpx.Response(200, json=OK_BODY)])
    client, sleeps = make_client(lambda r: next(replies))
    assert run(client.transcribe(b"x", language_code="unknown")).transcript
    assert sleeps[0] == 2.0  # Retry-After honoured
    assert 2.0 <= sleeps[1] <= 2.5  # exponential: base 1 s * 2^1 + jitter


def test_retries_network_errors():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json=OK_BODY)

    client, sleeps = make_client(handler)
    run(client.transcribe(b"x", language_code="unknown"))
    assert calls["n"] == 3 and len(sleeps) == 2


def test_gives_up_after_max_attempts():
    client, sleeps = make_client(lambda r: httpx.Response(500), max_attempts=4)
    with pytest.raises(SarvamError) as info:
        run(client.transcribe(b"x", language_code="unknown"))
    assert info.value.status == 500
    assert len(sleeps) == 3


@pytest.mark.parametrize("status", [400, 403, 422])
def test_client_errors_are_not_retried(status):
    client, sleeps = make_client(lambda r: httpx.Response(status, json={"error": {"message": "bad language_code"}}))
    with pytest.raises(SarvamError) as info:
        run(client.transcribe(b"x", language_code="unknown"))
    assert info.value.status == status and "bad language_code" in str(info.value)
    assert sleeps == []


def test_at_most_three_requests_in_flight():
    state = {"now": 0, "peak": 0}

    async def handler(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return httpx.Response(200, json=OK_BODY)

    async def main():
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = SarvamClient(KEY, http=http)
        await asyncio.gather(*(client.transcribe(b"x", language_code="unknown") for _ in range(10)))

    run(main())
    assert state["peak"] == 3


def test_key_never_logged_or_in_repr(caplog):
    caplog.set_level(logging.DEBUG)
    replies = iter([httpx.Response(429), httpx.Response(403, json={"error": {"message": "invalid key"}})])
    client, _ = make_client(lambda r: next(replies))
    with pytest.raises(SarvamError) as info:
        run(client.transcribe(b"AUDIO-BYTES-SECRET", language_code="unknown"))
    for text in (caplog.text, str(info.value), repr(client)):
        assert KEY not in text
        assert "AUDIO-BYTES-SECRET" not in text


def test_parse_response_without_or_with_broken_timestamps():
    assert parse_response({"transcript": " hi ", "language_code": None}).phrases == []
    mismatched = {"transcript": "a b", "timestamps": {"words": ["a", "b"], "start_time_seconds": [0], "end_time_seconds": [1, 2]}}
    assert parse_response(mismatched).phrases == []
    bad = {"transcript": "a", "timestamps": {"words": ["a"], "start_time_seconds": ["x"], "end_time_seconds": [1]}}
    assert parse_response(bad).phrases == []


def test_requires_key():
    with pytest.raises(ValueError):
        SarvamClient("")
