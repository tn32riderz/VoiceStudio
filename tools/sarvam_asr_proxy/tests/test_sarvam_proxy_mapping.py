"""Language mapping and keyterms."""
from __future__ import annotations

import pytest

from tools.sarvam_asr_proxy import keyterms, languages


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("ta", "ta-IN"),
        ("TA", "ta-IN"),
        ("ta-IN", "ta-IN"),
        ("ta_IN", "ta-IN"),
        ("hi", "hi-IN"),
        ("te", "te-IN"),
        ("ml", "ml-IN"),
        ("kn", "kn-IN"),
        ("bn", "bn-IN"),
        ("or", "od-IN"),
        ("en", "en-IN"),
        (None, "unknown"),
        ("", "unknown"),
        ("unknown", "unknown"),
        ("fr", "unknown"),
        ("ar", "unknown"),
    ],
)
def test_to_sarvam(given, expected):
    assert languages.to_sarvam(given) == expected


@pytest.mark.parametrize(("given", "expected"), [("ta-IN", "ta"), ("od-IN", "or"), ("en-IN", "en"), (None, None), ("xx-IN", None)])
def test_to_iso(given, expected):
    assert languages.to_iso(given) == expected


def test_keyterms_parsing(tmp_path):
    f = tmp_path / "k.txt"
    f.write_text("# comment\nFigma\n\nReact  # inline comment\nfigma\n" + "x" * 65 + "\nClaude Code\n", encoding="utf-8")
    assert keyterms.load_keyterms(f) == ["Figma", "React", "Claude Code"]


def test_keyterms_capped_at_50(tmp_path):
    f = tmp_path / "k.txt"
    f.write_text("\n".join(f"term{i}" for i in range(60)), encoding="utf-8")
    assert len(keyterms.load_keyterms(f)) == 50


def test_keyterms_env_and_defaults(tmp_path, monkeypatch):
    f = tmp_path / "k.txt"
    f.write_text("Vistaar\n", encoding="utf-8")
    monkeypatch.setenv("KEYTERMS_FILE", str(f))
    assert keyterms.load_keyterms() == ["Vistaar"]
    monkeypatch.setenv("KEYTERMS_FILE", "")
    assert keyterms.load_keyterms() == []
    monkeypatch.setenv("KEYTERMS_FILE", str(tmp_path / "missing.txt"))
    assert keyterms.load_keyterms() == []
    monkeypatch.delenv("KEYTERMS_FILE")
    bundled = keyterms.load_keyterms()
    assert "Figma" in bundled and "Claude" in bundled and len(bundled) <= 50
