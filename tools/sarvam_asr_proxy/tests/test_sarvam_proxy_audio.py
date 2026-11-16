"""Chunk boundaries, silence cuts and WAV encoding."""
from __future__ import annotations

import io
import shutil
import subprocess
import wave

import numpy as np
import pytest

from tools.sarvam_asr_proxy import audio

SR = audio.SAMPLE_RATE


def tone(seconds: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_short_audio_is_one_chunk():
    chunks = audio.split_at_silence(tone(10))
    assert chunks == [audio.Chunk(0, 10 * SR)]


def test_empty_audio_has_no_chunks():
    assert audio.split_at_silence(np.zeros(0, dtype=np.float32)) == []


def test_exactly_max_length_is_one_chunk():
    assert len(audio.split_at_silence(tone(28))) == 1


def test_cut_lands_in_the_pause():
    # Speech 0-23.0 s, pause 23.0-23.6 s, speech to 50 s.
    samples = np.concatenate([tone(23.0), silence(0.6), tone(26.4)])
    chunks = audio.split_at_silence(samples)
    assert len(chunks) == 2
    assert 23.0 <= chunks[0].end_s <= 23.6


def test_cut_picks_the_quietest_of_several_pauses():
    # A soft dip at 21 s and true silence at 25 s, both inside the search window.
    samples = np.concatenate([tone(21.0), tone(0.3, amp=0.05), tone(3.7), silence(0.4), tone(20)])
    first = audio.split_at_silence(samples)[0]
    assert 25.0 <= first.end_s <= 25.4


def test_chunks_are_contiguous_bounded_and_cover_everything():
    rng = np.random.default_rng(0)
    samples = (rng.standard_normal(SR * 125) * 0.1).astype(np.float32)
    samples[SR * 50 : SR * 51] = 0  # one pause; the rest has none
    chunks = audio.split_at_silence(samples)
    assert chunks[0].start == 0 and chunks[-1].end == len(samples)
    for a, b in zip(chunks, chunks[1:]):
        assert a.end == b.start
    assert all(0 < c.end - c.start <= 28 * SR for c in chunks)


def test_no_pause_still_cuts_within_limit():
    chunks = audio.split_at_silence(tone(70))
    assert all(c.end - c.start <= 28 * SR for c in chunks)
    assert chunks[-1].end == 70 * SR


def test_wav_bytes_are_16k_mono_pcm16():
    data = audio.to_wav_bytes(tone(1.5))
    with wave.open(io.BytesIO(data)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, SR)
        assert wav.getnframes() == int(1.5 * SR)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_decode_resamples_stereo_44k_to_mono_16k(tmp_path):
    src = tmp_path / "in.wav"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-ac", "2", "-ar", "44100", str(src)],
        check=True,
    )
    samples = audio.decode_to_mono16k(str(src))
    assert samples.dtype == np.float32
    assert abs(len(samples) - 2 * SR) < SR // 100


def test_decode_restricts_ffmpeg_to_local_inputs(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    audio.decode_to_mono16k("in.wav", ffmpeg="ffmpeg")
    cmd = seen["cmd"]
    wl = cmd.index("-protocol_whitelist")
    assert cmd[wl + 1] == "file,pipe"
    assert wl < cmd.index("-i")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_decode_never_fetches_urls_inside_a_playlist(tmp_path):
    import http.server
    import threading

    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        playlist = tmp_path / "clip.m3u8"
        playlist.write_text(
            "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\n"
            f"http://127.0.0.1:{server.server_port}/secret.ts\n#EXT-X-ENDLIST\n",
            encoding="utf-8",
        )
        with pytest.raises(audio.AudioDecodeError):
            audio.decode_to_mono16k(str(playlist))
    finally:
        server.shutdown()
    assert hits == []


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_decode_rejects_non_audio(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(audio.AudioDecodeError):
        audio.decode_to_mono16k(str(bad))
