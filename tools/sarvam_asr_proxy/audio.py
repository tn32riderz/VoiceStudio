"""Decode, chunk and re-encode audio for Sarvam's 30-second REST limit."""
from __future__ import annotations

import io
import shutil
import subprocess
import wave
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16_000
MAX_CHUNK_S = 28.0
# Where to look for a cut: the last stretch before the limit. Long enough to
# contain a pause in normal speech, short enough to keep chunks near 28 s.
SEARCH_WINDOW_S = 8.0
FRAME_S = 0.02


class AudioDecodeError(RuntimeError):
    """The upload could not be decoded as audio."""


@dataclass(frozen=True)
class Chunk:
    start: int  # sample index, inclusive
    end: int  # sample index, exclusive

    @property
    def start_s(self) -> float:
        return self.start / SAMPLE_RATE

    @property
    def end_s(self) -> float:
        return self.end / SAMPLE_RATE


def decode_to_mono16k(path: str, *, ffmpeg: str | None = None) -> np.ndarray:
    """Decode any ffmpeg-readable file to float32 mono samples at 16 kHz."""
    exe = ffmpeg or shutil.which("ffmpeg")
    if not exe:
        raise AudioDecodeError("ffmpeg is not installed")
    cmd = [
        exe, "-nostdin", "-hide_banner", "-loglevel", "error",
        # Local files only: an upload that is really a playlist or manifest
        # must not make ffmpeg fetch the URLs inside it (same rule as
        # backend/services/ffmpeg_utils.py).
        "-protocol_whitelist", "file,pipe",
        "-i", path, "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        # ffmpeg's message names only the format problem, never audio content.
        reason = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["unknown error"]
        raise AudioDecodeError(f"could not decode audio: {reason[0][:200]}")
    return np.frombuffer(proc.stdout, dtype="<f4").astype(np.float32, copy=False)


def _frame_energy(samples: np.ndarray, frame: int) -> np.ndarray:
    usable = len(samples) // frame * frame
    if usable == 0:
        return np.zeros(0, dtype=np.float32)
    frames = samples[:usable].reshape(-1, frame).astype(np.float64)
    return np.sqrt(np.mean(frames * frames, axis=1))


def split_at_silence(
    samples: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    max_chunk_s: float = MAX_CHUNK_S,
    search_window_s: float = SEARCH_WINDOW_S,
    frame_s: float = FRAME_S,
) -> list[Chunk]:
    """Split into contiguous chunks of at most ``max_chunk_s``.

    Each cut is placed at the centre of the quietest frame in the last
    ``search_window_s`` before the limit, so a cut falls in a pause rather
    than inside a word. The chunks cover every sample exactly once.
    """
    total = len(samples)
    if total == 0:
        return []
    max_len = int(max_chunk_s * sample_rate)
    window = min(int(search_window_s * sample_rate), max_len - 1)
    frame = max(1, int(frame_s * sample_rate))
    chunks: list[Chunk] = []
    start = 0
    while total - start > max_len:
        search_from = start + max_len - window
        region = samples[search_from : start + max_len]
        energy = _frame_energy(region, frame)
        if energy.size:
            quietest = int(np.argmin(energy))
            cut = search_from + quietest * frame + frame // 2
        else:
            cut = start + max_len
        cut = min(max(cut, start + 1), start + max_len)
        chunks.append(Chunk(start, cut))
        start = cut
    chunks.append(Chunk(start, total))
    return chunks


def to_wav_bytes(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode float samples as 16-bit PCM mono WAV."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buf.getvalue()
