"""Map OpenAI ``language`` values (ISO 639-1/-3) to Sarvam BCP-47 codes and back."""
from __future__ import annotations

from typing import Optional

UNKNOWN = "unknown"

# Sarvam's language_code values (STT API reference), keyed by the ISO code an
# OpenAI client sends. Odia is ISO "or" but Sarvam's code is "od-IN".
_ISO_TO_SARVAM = {
    "as": "as-IN",
    "bn": "bn-IN",
    "brx": "brx-IN",
    "doi": "doi-IN",
    "en": "en-IN",
    "gu": "gu-IN",
    "hi": "hi-IN",
    "kn": "kn-IN",
    "kok": "kok-IN",
    "ks": "ks-IN",
    "mai": "mai-IN",
    "ml": "ml-IN",
    "mni": "mni-IN",
    "mr": "mr-IN",
    "ne": "ne-IN",
    "or": "od-IN",
    "od": "od-IN",
    "pa": "pa-IN",
    "sa": "sa-IN",
    "sat": "sat-IN",
    "sd": "sd-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "ur": "ur-IN",
}
_SARVAM_TO_ISO = {v: k for k, v in _ISO_TO_SARVAM.items() if k != "od"}


def to_sarvam(language: Optional[str]) -> str:
    """OpenAI ``language`` -> Sarvam ``language_code``; unknown or missing -> ``unknown``.

    Accepts ``ta``, ``TA``, ``ta-IN`` and ``ta_IN``. A language Sarvam does not
    support also maps to ``unknown`` so Sarvam auto-detects instead of failing.
    """
    if not language or not language.strip():
        return UNKNOWN
    code = language.strip().replace("_", "-")
    if code.lower() == UNKNOWN:
        return UNKNOWN
    base = code.split("-", 1)[0].lower()
    return _ISO_TO_SARVAM.get(base, UNKNOWN)


def to_iso(sarvam_code: Optional[str]) -> Optional[str]:
    """Sarvam ``language_code`` -> ISO code VoiceStudio understands (``ta-IN`` -> ``ta``)."""
    if not sarvam_code:
        return None
    return _SARVAM_TO_ISO.get(sarvam_code.strip())
