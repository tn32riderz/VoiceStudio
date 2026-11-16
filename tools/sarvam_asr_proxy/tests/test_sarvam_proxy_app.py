"""End-to-end through the FastAPI app with a fake Sarvam: offsets, formats, errors."""
from __future__ import annotations

import logging

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tools.sarvam_asr_proxy import audio
from tools.sarvam_asr_proxy.app import create_app
from tools.sarvam_asr_proxy.sarvam import SarvamError, SarvamResult

SR = audio.SAMPLE_RATE


class FakeSarvam:
    """Returns one or two phrases per chunk, timed relative to the chunk."""

    def __init__(self, *, timestamps=True, fail=None, language_code="ta-IN"):
        self.calls = []
        self.timestamps = timestamps
        self.fail = fail
        self.language_code = language_code

    async def transcribe(self, wav, *, language_code, keyterms=None):
        self.calls.append({"language_code": language_code, "keyterms": keyterms, "bytes": len(wav)})
        if self.fail:
            raise self.fail
        n = len(self.calls)
        phrases = [(f"chunk{n} first", 0.5, 2.0), (f"chunk{n} second", 3.0, 4.25)] if self.timestamps else []
        return SarvamResult(transcript=f"chunk{n} first chunk{n} second", language_code=self.language_code, phrases=phrases)


def speech_with_pause(total_s=50.0, pause_at=23.0, pause_s=0.6):
    t = np.arange(int(total_s * SR)) / SR
    samples = (0.4 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    samples[int(pause_at * SR) : int((pause_at + pause_s) * SR)] = 0
    return samples


def client_for(fake, samples=None, keyterms=("Figma",)):
    samples = speech_with_pause() if samples is None else samples
    app = create_app(recognizer_factory=lambda: fake, decoder=lambda path: samples, keyterms_loader=lambda: list(keyterms))
    return TestClient(app)


def post(client, **form):
    return client.post("/v1/audio/transcriptions", files={"file": ("a.wav", b"fake", "audio/wav")}, data=form)


def test_models_lists_the_proxy_model():
    body = client_for(FakeSarvam()).get("/v1/models").json()
    assert [m["id"] for m in body["data"]] == ["saaras-v4-codemix"]


def test_verbose_json_offsets_timestamps_by_chunk_start():
    fake = FakeSarvam()
    body = post(client_for(fake), model="saaras-v4-codemix", language="ta", response_format="verbose_json").json()
    assert len(fake.calls) == 2
    cut = body["segments"][2]["start"] - 0.5  # second chunk's first phrase starts 0.5 s into it
    assert 23.0 <= cut <= 23.6
    assert [s["id"] for s in body["segments"]] == [0, 1, 2, 3]
    assert body["segments"][0] == {"id": 0, "start": 0.5, "end": 2.0, "text": "chunk1 first"}
    assert body["segments"][3]["end"] == pytest.approx(cut + 4.25, abs=1e-3)
    assert body["duration"] == 50.0
    assert body["language"] == "ta"
    assert body["text"] == "chunk1 first chunk1 second chunk2 first chunk2 second"


def test_language_and_keyterms_reach_sarvam():
    fake = FakeSarvam()
    post(client_for(fake), language="ta", response_format="verbose_json")
    assert all(c["language_code"] == "ta-IN" and c["keyterms"] == ["Figma"] for c in fake.calls)


def test_missing_language_auto_detects_and_reports_detected():
    fake = FakeSarvam(language_code="hi-IN")
    body = post(client_for(fake), response_format="verbose_json").json()
    assert {c["language_code"] for c in fake.calls} == {"unknown"}
    assert body["language"] == "hi"


def test_chunk_without_timestamps_becomes_one_segment():
    body = post(client_for(FakeSarvam(timestamps=False)), response_format="verbose_json").json()
    assert len(body["segments"]) == 2
    first, second = body["segments"]
    assert first["start"] == 0.0 and first["end"] == second["start"]
    assert second["end"] == 50.0
    assert first["text"] == "chunk1 first chunk1 second"


def test_json_and_text_formats():
    assert post(client_for(FakeSarvam()), response_format="json").json() == {
        "text": "chunk1 first chunk1 second chunk2 first chunk2 second"
    }
    resp = post(client_for(FakeSarvam()), response_format="text")
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text == "chunk1 first chunk1 second chunk2 first chunk2 second"


def test_default_format_is_json():
    assert set(post(client_for(FakeSarvam())).json()) == {"text"}


def test_unsupported_format_is_rejected():
    resp = post(client_for(FakeSarvam()), response_format="srt")
    assert resp.status_code == 400


def test_phrases_are_clamped_inside_their_chunk():
    class Overrun(FakeSarvam):
        async def transcribe(self, wav, **kw):
            return SarvamResult("x", "ta-IN", [("x", -1.0, 99.0)])

    body = post(client_for(Overrun(), samples=speech_with_pause(10.0, 5.0)), response_format="verbose_json").json()
    assert body["segments"] == [{"id": 0, "start": 0.0, "end": 10.0, "text": "x"}]


def test_no_key_returns_503(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    client = TestClient(create_app(decoder=lambda p: speech_with_pause()))
    assert post(client).status_code == 503


@pytest.mark.parametrize(("status", "expected"), [(429, 429), (403, 502), (None, 502)])
def test_upstream_errors_are_mapped(status, expected):
    resp = post(client_for(FakeSarvam(fail=SarvamError("nope", status))), response_format="verbose_json")
    assert resp.status_code == expected
    assert resp.json()["error"]["type"] == "upstream_error"


def test_logs_have_no_transcript_or_key(caplog, monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_should_never_appear")
    caplog.set_level(logging.DEBUG)
    post(client_for(FakeSarvam()), response_format="verbose_json")
    assert "sk_should_never_appear" not in caplog.text
    assert "chunk1 first" not in caplog.text


def test_main_refuses_non_loopback_host():
    from tools.sarvam_asr_proxy.__main__ import main

    with pytest.raises(SystemExit):
        main(["--host", "0.0.0.0"])
