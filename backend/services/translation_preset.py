"""Default dub-translation style prompt + glossary (personal v1, change 3).

A preset is a directory under ``presets/`` holding ``style-prompt.md`` (with an
optional ``{target}`` placeholder) and ``glossary.csv`` (``term,translation``;
``keep`` means the term stays as written). When a ``/dub/translate`` request
carries no style brief of its own and the preset is switched on, the preset
fills it in; the request's own glossary entries always win over the preset's.

On: ``OMNIVOICE_TRANSLATE_PRESET=<name>`` (``off`` disables it), or, with the
variable unset, the active LLM provider being ``anthropic`` and the source
being Tamil. Nothing here touches the network or user data.
"""
from __future__ import annotations

import csv
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger("omnivoice.translation_preset")

ENV_PRESET = "OMNIVOICE_TRANSLATE_PRESET"
ENV_DIR = "OMNIVOICE_PRESETS_DIR"
DEFAULT_PRESET = "tanglish-dub"
_SOURCE_LANGS = {"ta"}


def _presets_dir() -> Path:
    override = os.environ.get(ENV_DIR)
    if override:
        return Path(override)
    # backend/services/translation_preset.py -> repo root (or /app in Docker)
    return Path(__file__).resolve().parents[2] / "presets"


@lru_cache(maxsize=8)
def _load(directory: str, name: str) -> Optional[tuple[str, tuple[tuple[str, str], ...]]]:
    base = Path(directory) / name
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    try:
        prompt = (base / "style-prompt.md").read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("translation preset %r not found under %s", name, directory)
        return None
    terms: list[tuple[str, str]] = []
    try:
        with (base / "glossary.csv").open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                term = (row.get("term") or "").strip()
                tr = (row.get("translation") or "").strip()
                if term and tr:
                    terms.append((term, term if tr.lower() == "keep" else tr))
    except OSError:
        pass
    return prompt, tuple(terms)


def load_preset(name: str) -> Optional[dict]:
    """``{"prompt": str, "glossary": [{"source","target","note"}]}`` or None."""
    loaded = _load(str(_presets_dir()), name)
    if loaded is None:
        return None
    prompt, terms = loaded
    return {
        "prompt": prompt,
        "glossary": [{"source": s, "target": t, "note": "keep as written" if s == t else ""}
                     for s, t in terms],
    }


def _selected_name(src_lang: Optional[str]) -> Optional[str]:
    env = (os.environ.get(ENV_PRESET) or "").strip()
    if env:
        return None if env.lower() in {"off", "0", "false", "none"} else env
    if (src_lang or "").lower()[:2] not in _SOURCE_LANGS:
        return None
    try:
        from services import llm_providers
        return DEFAULT_PRESET if llm_providers.active_provider_id() == "anthropic" else None
    except Exception:
        logger.debug("preset provider check failed", exc_info=True)
        return None


def apply_defaults(req, src_lang: Optional[str], target_name: str) -> Optional[str]:
    """Fill ``req.translation_instructions`` / ``req.glossary`` from the preset.

    Returns the preset name applied, or None. A request that already has a
    style brief keeps it untouched; glossary entries it carries win.
    """
    name = _selected_name(src_lang)
    preset = load_preset(name) if name else None
    if preset is None:
        return None
    if not (getattr(req, "translation_instructions", None) or "").strip():
        req.translation_instructions = preset["prompt"].replace("{target}", target_name)
    own = list(getattr(req, "glossary", None) or [])
    seen = {(e.get("source") or "").strip().lower() for e in own}
    req.glossary = own + [e for e in preset["glossary"] if e["source"].lower() not in seen]
    return name
