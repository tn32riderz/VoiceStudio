"""Chunk -> recognise -> offset timestamps -> OpenAI ``verbose_json`` segments."""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Optional, Protocol

import numpy as np

from . import audio, languages
from .sarvam import SarvamResult


class Recognizer(Protocol):
    async def transcribe(
        self, wav: bytes, *, language_code: str, keyterms: Optional[list[str]] = None
    ) -> SarvamResult: ...


def _segments_for_chunk(chunk: audio.Chunk, result: SarvamResult) -> list[dict]:
    """Phrase timestamps shifted by the chunk start; without timestamps, the whole chunk."""
    lo, hi = chunk.start_s, chunk.end_s
    if result.phrases:
        out = []
        for text, start, end in result.phrases:
            s = min(max(lo + start, lo), hi)
            e = min(max(lo + end, s), hi)
            out.append({"start": round(s, 3), "end": round(e, 3), "text": text})
        return out
    if result.transcript:
        return [{"start": round(lo, 3), "end": round(hi, 3), "text": result.transcript}]
    return []


async def transcribe_samples(
    samples: np.ndarray,
    recognizer: Recognizer,
    *,
    language: Optional[str] = None,
    keyterms: Optional[list[str]] = None,
) -> dict:
    """Return ``{text, language, duration, segments}`` for 16 kHz mono samples.

    Chunks are sent concurrently; the recognizer enforces its own limit.
    """
    language_code = languages.to_sarvam(language)
    chunks = audio.split_at_silence(samples)
    results = await asyncio.gather(*(
        recognizer.transcribe(
            audio.to_wav_bytes(samples[c.start : c.end]),
            language_code=language_code,
            keyterms=keyterms,
        )
        for c in chunks
    ))
    segments: list[dict] = []
    for chunk, result in zip(chunks, results):
        segments.extend(_segments_for_chunk(chunk, result))
    for i, seg in enumerate(segments):
        seg["id"] = i
    detected = Counter(languages.to_iso(r.language_code) for r in results if r.transcript)
    detected.pop(None, None)
    if language_code != languages.UNKNOWN:
        lang = languages.to_iso(language_code)
    elif detected:
        lang = detected.most_common(1)[0][0]
    else:
        lang = None
    return {
        "text": " ".join(seg["text"] for seg in segments),
        "language": lang or (language or "unknown"),
        "duration": round(len(samples) / audio.SAMPLE_RATE, 3),
        "segments": [{"id": s["id"], "start": s["start"], "end": s["end"], "text": s["text"]} for s in segments],
    }
