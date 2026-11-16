"""Timing guard rails (personal v1, change 4): rushed-line flagging, the
check/shorten endpoints, and the segment-edge fade."""
import pytest
import torch

from services import timing_guard
from services.dub_mix import EDGE_FADE_SECONDS, fade_segment_edges
from services.speech_rate import expected_duration


def _line(text, slot, **kw):
    return {"id": "a", "text": text, "start": 10.0, "end": 10.0 + slot, **kw}


def test_rushed_threshold_is_exclusive_and_per_language():
    text = "x" * 26                      # en: 13 cps -> 2.0 s of speech
    exact = expected_duration(text, "en")
    assert timing_guard.flag_lines([_line(text, exact / 1.26)], "en")[0]["kind"] == "rushed"
    assert timing_guard.flag_lines([_line(text, exact / 1.24)], "en") == []
    assert timing_guard.flag_lines([_line(text, exact)], "en") == []
    # a language with a slower table rate flags the same text sooner
    assert timing_guard.flag_lines([_line("x" * 20, 1.0)], "th")[0]["kind"] == "rushed"


def test_impossible_wins_and_unusable_lines_are_skipped():
    flagged = timing_guard.flag_lines([
        _line("x" * 100, 1.0, plan_status="impossible"),
        {"id": "b", "text": "", "start": 0, "end": 2},
        {"id": "c", "text": "hello", "start": 5, "end": 5},
        _line("short", 5.0, plan_status="tight"),
    ], "en")
    assert [(f["id"], f["kind"]) for f in flagged] == [("a", "impossible")]


@pytest.mark.asyncio
async def test_timing_check_endpoint():
    from api.routers import dub_translate
    req = dub_translate.TimingCheckRequest(lang="en", segments=[
        dub_translate.TimingLine(id="s1", text="x" * 60, start=0, end=2),
        dub_translate.TimingLine(id="s2", text="fine", start=2, end=6),
    ])
    out = await dub_translate.dub_timing_check(req)
    assert out["rushed_ratio"] == 1.25
    assert [(f["id"], f["kind"]) for f in out["flagged"]] == [("s1", "rushed")]


@pytest.mark.asyncio
async def test_shorten_uses_condensation_and_rejects_empty_slot(monkeypatch):
    from fastapi import HTTPException
    from api.routers import dub_translate
    from services import speech_rate

    seen = {}

    def fake(text, **kw):
        seen.update(kw)
        return {"text": "short", "rate_ratio": 0.9, "attempts": 1}

    monkeypatch.setattr(speech_rate, "adjust_for_slot", fake)
    out = await dub_translate.dub_shorten(dub_translate.ShortenRequest(
        text="a much longer line", start=1, end=3, lang="es", source_text="src"))
    assert out == {"text": "short", "changed": True, "rate_ratio": 0.9, "error": None}
    assert seen["slot_seconds"] == 2 and seen["strict"] is True

    with pytest.raises(HTTPException):
        await dub_translate.dub_shorten(dub_translate.ShortenRequest(
            text="x", start=3, end=3, lang="es"))


def test_edge_fade_ramps_both_ends_and_keeps_the_middle():
    sr = 1000
    n = int(EDGE_FADE_SECONDS * sr)
    audio = torch.ones(1, 200)
    fade_segment_edges(audio, sr)
    assert audio[0, 0].item() == 0.0 and audio[0, -1].item() == 0.0
    assert audio[0, :n].is_floating_point() and torch.all(audio[0, 1:n] > 0)
    assert torch.all(audio[0, :n - 1] <= audio[0, 1:n])          # rising in
    assert torch.all(audio[0, -n:-1] >= audio[0, -n + 1:])       # falling out
    assert torch.all(audio[0, n:-n] == 1.0)


def test_edge_fade_skips_segments_too_short_for_two_ramps():
    audio = torch.ones(1, 20)               # 15 samples per ramp at 1 kHz
    fade_segment_edges(audio, 1000)
    assert torch.all(audio == 1.0)


def test_rushed_threshold_matches_the_frontend_constant():
    import re
    from pathlib import Path

    ts = Path(__file__).resolve().parents[1] / (
        "electron/src/renderer/src/features/dub/dub-timing-gate.ts")
    match = re.search(r"RUSHED_RATIO\s*=\s*([\d.]+)", ts.read_text(encoding="utf-8"))
    assert match and float(match.group(1)) == timing_guard.RUSHED_RATIO
