"""Tanglish dub preset (personal v1, change 3): loads, applies only when it
should, never overrides the user's own brief or glossary, and reaches the
prompt sent to the LLM. No network."""
import types

import pytest

from test_dub_translation_quality import (  # noqa: E402
    _ScriptedLLMClient, _segs, _wire_skill_client,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("OMNIVOICE_TRANSLATE_PRESET", raising=False)
    monkeypatch.delenv("OMNIVOICE_PRESETS_DIR", raising=False)


def _req(**kw):
    from schemas.requests import TranslateRequest
    return TranslateRequest(
        segments=_segs("Intha Figma plugin romba nalla irukku."),
        target_lang="es", provider="openai", source_lang="ta", **kw)


def _anthropic_active(monkeypatch, pid="anthropic"):
    from services import llm_providers
    monkeypatch.setattr(llm_providers, "active_provider_id", lambda: pid)


def test_preset_files_load():
    from services.translation_preset import load_preset
    p = load_preset("tanglish-dub")
    assert p and "{target}" in p["prompt"] and "Tanglish" in p["prompt"]
    by_src = {e["source"]: e["target"] for e in p["glossary"]}
    assert by_src["Figma"] == "Figma" and by_src["API"] == "API"


def test_unknown_or_unsafe_preset_name_is_none():
    from services.translation_preset import load_preset
    assert load_preset("nope") is None
    assert load_preset("../tanglish-dub") is None


def test_applies_for_anthropic_and_tamil_source(monkeypatch):
    from services.translation_preset import apply_defaults
    _anthropic_active(monkeypatch)
    req = _req()
    assert apply_defaults(req, "ta", "Spanish") == "tanglish-dub"
    assert "natural, casual spoken Spanish" in req.translation_instructions
    assert "{target}" not in req.translation_instructions
    assert {"Figma", "API"} <= {e["source"] for e in req.glossary}


@pytest.mark.parametrize("pid,src", [("openai", "ta"), ("anthropic", "en"), (None, "ta")])
def test_not_applied_otherwise(monkeypatch, pid, src):
    from services.translation_preset import apply_defaults
    _anthropic_active(monkeypatch, pid)
    req = _req()
    assert apply_defaults(req, src, "Spanish") is None
    assert req.translation_instructions is None and not req.glossary


def test_env_forces_on_and_off(monkeypatch):
    from services.translation_preset import apply_defaults
    _anthropic_active(monkeypatch, "openai")
    monkeypatch.setenv("OMNIVOICE_TRANSLATE_PRESET", "tanglish-dub")
    assert apply_defaults(_req(), "en", "Spanish") == "tanglish-dub"
    _anthropic_active(monkeypatch)
    monkeypatch.setenv("OMNIVOICE_TRANSLATE_PRESET", "off")
    assert apply_defaults(_req(), "ta", "Spanish") is None


def test_user_brief_and_glossary_win(monkeypatch):
    from services.translation_preset import apply_defaults
    _anthropic_active(monkeypatch)
    req = _req(translation_instructions="Formal register.",
               glossary=[{"source": "figma", "target": "Figma-es", "note": ""}])
    apply_defaults(req, "ta", "Spanish")
    assert req.translation_instructions == "Formal register."
    figma = [e for e in req.glossary if e["source"].lower() == "figma"]
    assert figma == [{"source": "figma", "target": "Figma-es", "note": ""}]


@pytest.mark.asyncio
async def test_preset_reaches_llm_prompt(monkeypatch):
    from api.routers import dub_translate
    _anthropic_active(monkeypatch)
    client = _ScriptedLLMClient(
        lambda kw: "THEME: tech review\n" if "translation brief" in kw["messages"][0]["content"] else "hola")
    _wire_skill_client(monkeypatch, client)
    resp = await dub_translate.dub_translate(_req(reflect=False))
    assert resp["translated"][0]["text"] == "hola"
    direct = [c for c in client.calls if "professional dubbing translator" in client.system_of(c)]
    assert direct
    sys_msg = client.system_of(direct[0])
    assert "natural, casual spoken Spanish" in sys_msg     # style prompt
    assert "Figma → Figma" in sys_msg                      # glossary term
