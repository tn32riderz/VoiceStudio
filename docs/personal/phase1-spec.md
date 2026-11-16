# VoiceStudio Fork — Phase 1 Change Spec (for Claude Code)

Nov 16, 2026 · @Vignesh

## 1. Goal and scope

Phase 1 makes a personal fork of [VoiceStudio](https://github.com/debpalash/VoiceStudio) dub my Tanglish (Tamil + English) videos into other languages in my own cloned voice, with each dubbed line locked to the original line's time slot. Volume: up to 20 videos a month, one user, personal use only. Every change below uses a feature or API that is documented today; nothing depends on an untested model.

**In scope (Phase 1):**

1. Run the fork on a RunPod GPU, driven from the VoiceStudio desktop app on my Intel Mac.
2. Transcribe Tanglish speech with Sarvam Saaras v4 through VoiceStudio's existing OpenAI-compatible ASR slot.
3. Translate with Claude through VoiceStudio's existing "Translate with Agent" (Claude Code CLI on the Mac).
4. Lock timing: every dubbed line fills exactly its original slot, with background audio kept.
5. A repeatable per-video workflow that fits 20 videos a month.

**Out of scope (later phases):** new TTS engines (Maya 2 Native, ZONOS3-Mini), per-language engine routing, Seed-VC, OmniVoice fine-tuning, ElevenLabs integration, lip-sync.

**Rules for Claude Code:** follow the repo's `CLAUDE.md`; keep every change small and isolated so upstream updates still merge; add tests for new code; do not change the default OmniVoice engine.

## 2. What the repo already has (reuse, do not rebuild)

Checked against upstream `main` at commit `b6f05ec` (16 Nov 2026). Most of Phase 1 is configuration plus one small new service.

| Need | Existing piece | Where |
| --- | --- | --- |
| Remote GPU backend + thin client | Backend with `OMNIVOICE_API_KEY` + `OMNIVOICE_SERVER_MODE=1`; desktop app enters Backend URL + key | `docs/remote-gpu.md` |
| GPU Docker image | CUDA Dockerfile; data in `OMNIVOICE_DATA_DIR` volume | `deploy/Dockerfile`, `docs/install/docker.md` |
| Plug-in ASR | "OpenAI-compatible (remote server)" ASR engine; uses `verbose_json` segments; plain HTTP allowed only on loopback | `docs/engines/openai-compatible-asr.md` |
| Claude translation | "Translate with Agent" detects Claude Code CLI; sends dialogue, glossary, per-line time budgets | `docs/dubbing/translation-engines.md` |
| Exact slot timing | `strict_slot` timing strategy (UI default): passes each segment's `end - start` as `duration` to the TTS engine | `backend/api/routers/dub_generate.py` |
| Pre-synthesis fit check | Duration planner badges each line fits / tight / impossible; optional LLM condensation | `backend/services/duration_planner.py` |
| Emotion carry-over | Voice match "Per line": each line cloned from its own source audio; "Mirror source delivery" | `electron/src/shared/store/prefsSlice.ts`, `docs/expressive-speech.md` |
| Background kept | Dialogue-free regions keep original music/ambience | `backend/services/dub_background.py` |
| Many videos | Batch dubbing queue (in-memory; lost on backend restart) | `docs/electron-batch.md` |
| Voice model | OmniVoice, 646 languages, `duration` control | `docs/engines/omnivoice.md` |

## 3. Phase 1 architecture

&#91;embedded content: Phase 1 architecture · Mac thin client + RunPod backend + Sarvam ASR\]

The two main pieces of new code are the Sarvam ASR proxy (step 1) and the timing guard rails (step 4); the rest is deployment scripts, presets and existing VoiceStudio features set up for this workflow.

## 4. Change 1 — RunPod deployment + Mac remote UI

The Intel Mac cannot run the backend (upstream issue #889), so the backend runs on RunPod and the Mac app is the thin client.

**Tasks for Claude Code:**

1. Fork `debpalash/VoiceStudio` to my GitHub account; work on branch `personal/phase1`.
2. Add `deploy/runpod/README.md` with exact steps and a `deploy/runpod/start.sh` that:
   - sets `OMNIVOICE_DATA_DIR=/workspace/omnivoice_data` (RunPod network volume, so models download once);
   - sets `HF_HOME=/workspace/hf_cache`;
   - requires `OMNIVOICE_API_KEY` and sets `OMNIVOICE_SERVER_MODE=1`;
   - starts the Sarvam ASR proxy from Change 2 on `127.0.0.1:9876` when `SARVAM_API_KEY` is set;
   - starts the backend on `0.0.0.0:3900`.
3. Add a GitHub Actions workflow that builds the CUDA image from `deploy/Dockerfile` (plus the proxy) and pushes `ghcr.io/<me>/voicestudio:phase1`.
4. Document the RunPod template: image `ghcr.io/<me>/voicestudio:phase1`, GPU RTX 4090 24 GB, HTTP port 3900, 50 GB network volume at `/workspace`, env `OMNIVOICE_API_KEY`, `SARVAM_API_KEY`.
5. Document the Mac side: install `VoiceStudio-<version>-mac-x64.dmg` (UI only), Settings → Backend URL = `https://<pod-id>-3900.proxy.runpod.net`, API key = `OMNIVOICE_API_KEY`; install and log in to Claude Code on the Mac.

**Done when:** the Mac app connects, the setup wizard completes on the pod, and a 30-second test clip dubs end to end. Stopping and restarting the pod keeps models (no re-download).

## 5. Change 2 — Sarvam Saaras v4 ASR for Tanglish

Whisper mishandles Tamil-English switching; Sarvam's Saaras model is built for it and its `codemix` mode writes English words in Latin script and Tamil words in Tamil script. VoiceStudio can already call any OpenAI-compatible ASR, so this is one small proxy service, not a core change.

**Facts from Sarvam's API docs** ([STT API](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe), [Saaras](https://docs.sarvam.ai/api-reference-docs/getting-started/models/saaras)):

- `POST https://api.sarvam.ai/speech-to-text`, header `api-subscription-key`, multipart `file`.
- `model=saaras:v4` (default); `mode` = `transcribe` | `translate` | `verbatim` | `translit` | `codemix`.
- `language_code` e.g. `ta-IN`, or `unknown` to auto-detect.
- `with_timestamps=true` returns phrase-level `timestamps.words` / `start_time_seconds` / `end_time_seconds` (no word-level).
- REST limit: 30 seconds per request; longer files need the Batch API (up to 2 hours).
- `keyterms` (v4): up to 50 terms to bias recognition.

**Tasks for Claude Code — new folder `tools/sarvam_asr_proxy/`:**

1. A FastAPI app on `127.0.0.1:9876` exposing `GET /v1/models` (returns `saaras-v4-codemix`) and `POST /v1/audio/transcriptions` (OpenAI form fields: `file`, `model`, `language`, `prompt`, `response_format`).
2. Decode input to 16 kHz mono WAV; split into chunks of at most 28 s, cutting at the quietest point (silence detection) so no word is split.
3. For each chunk call Sarvam with `model=saaras:v4`, `mode=codemix`, `with_timestamps=true`, `language_code` mapped from the OpenAI `language` (`ta` → `ta-IN`, other Indic codes likewise, missing → `unknown`). Read optional keyterms from `KEYTERMS_FILE` (my tech words: Figma, React, Claude, API…).
4. Offset each phrase timestamp by its chunk start; if a chunk returns no timestamps, emit the chunk as one segment.
5. Return OpenAI `verbose_json`: `{text, language, duration, segments:[{id, start, end, text}]}`; return plain `text` when `response_format=text`.
6. Retry 429/5xx with exponential backoff; limit to 3 concurrent Sarvam calls; never log audio or the API key.
7. Unit tests with a mocked Sarvam client: chunk boundaries, timestamp offsets, language mapping, both response formats.
8. In VoiceStudio: Settings → Models → ASR → OpenAI-compatible: URL `http://127.0.0.1:9876/v1`, model `saaras-v4-codemix`, then **Use**. Keep WhisperX installed as the fallback for non-Indian source languages.

**Done when:** a 2-minute Tanglish clip transcribes with English words kept in English, segment times within ±0.3 s of the speech, and the dub editor shows the segments.

## 6. Change 3 — Tanglish translation preset

Translation itself already works well: Claude reads Tanglish naturally and Tanglish → English comes out right today. This change only makes the good settings the default, so every video gets the same quality without retyping prompts.

**Tasks for Claude Code:**

1. Add `presets/tanglish-dub/style-prompt.md` with this text, and make it the default "Translation style prompt" in the dub settings (prefs default, user can still edit):

   > Source is spoken Tanglish: Tamil with English words mixed in. Translate the meaning into natural, casual spoken {target}, as a YouTube creator talks. Keep the energy, jokes and emphasis of each line. Keep product and tech names (Figma, React, API, Claude) as they are. For non-Latin target scripts, write those names in the target script as they are pronounced. Respect each line's time budget: never add words that make a line longer to say than the original.
2. Add `presets/tanglish-dub/glossary.csv` (term, translation-or-keep) seeded with my common tech words; load it into the existing dub glossary.
3. Make "Translate with Agent → Claude Code" the default translator when the Claude Code CLI is detected.

**Done when:** the same 2-minute clip translated to English, Hindi, Telugu, Malayalam and Arabic keeps tech names correct, and the duration planner shows no "impossible" lines caused by over-long translations.

## 7. Change 4 — Timing lock (exact sync, no glitches)

The repo already has the right mechanism: with the `strict_slot` timing strategy, `dub_generate.py` passes each segment's exact length (`end - start`) as `duration` to OmniVoice, so the voice is generated to fill the slot instead of being stretched afterwards. What is missing is guard rails, so a too-long translation never ships as rushed speech.

**Tasks for Claude Code:**

1. **Lock the defaults** for new dub sessions: timing = `strict_slot`, voice match = Per line, Mirror source delivery = on, preserve background = on.
2. **Rushed-line check after generation:** for each segment, compare characters per second of the translated text with the language's normal rate (`backend/services/speech_rate.py`). Flag lines above 1.25× as "rushed" in the dub editor, with a one-click "shorten and regenerate" that reuses the existing duration-planner condensation.
3. **Export gate:** before export, list every "impossible" (duration planner) or "rushed" line and require an explicit "export anyway".
4. **Clean joins:** verify `dub_mix.py` applies a short fade (about 10 ms) at every segment edge and keeps dub-free regions at the original background level; add it if missing, with a test.
5. **Loudness:** confirm export loudness normalisation is on so every language track matches the original's level.

**Done when:** on a real 10-minute video, every dubbed line starts within ±50 ms of the original line, no line is flagged "rushed" after one shorten pass, and listening end to end finds no clicks, gaps or level jumps.

## 8. Change 5 — Workflow for 20 videos a month

Use the interactive Dub page per video, not the batch queue: the batch queue's translation runs on the backend, so it cannot use the Claude Code agent on the Mac, and it skips the line review that keeps sync and emotion right.

**Per-video routine (target: about 1 to 1.5 GPU-hours per 10-minute video, 4 languages):**

1. Start the RunPod pod; open the Mac app.
2. Dub page → upload video → source language Tamil → Transcribe (Sarvam). Fix any wrong words in the Tamil text.
3. Pick target languages → Translate with Agent (Claude Code) using the Tanglish preset.
4. Generate. Fix flagged lines (impossible, rushed) with "shorten and regenerate". Listen once per language.
5. Export one WAV per language → upload as YouTube audio tracks.
6. Stop the pod.

**Tasks for Claude Code:**

1. Write `deploy/runpod/WORKFLOW.md` with the routine above and the exact name and value of each setting.
2. Add an idle auto-stop: a small script on the pod that calls the RunPod API to stop the pod after 30 minutes with no backend requests (`RUNPOD_API_KEY` env, off by default).
3. Save each dub project bundle to `/workspace/projects/` so a video can be reopened and re-exported after a restart.

## 9. Acceptance tests (run in this order)

Phase 1 is done only when every test passes on the real RunPod setup.

| # | Test | Pass when |
| --- | --- | --- |
| 1 | Mac app → RunPod backend over HTTPS, including WebSocket progress | Connects; progress bars update live |
| 2 | Pod stop → start | Models load from `/workspace`; no re-download |
| 3 | Sarvam proxy unit tests | All pass (`pytest tools/sarvam_asr_proxy`) |
| 4 | 2-minute Tanglish clip → transcript | English words in Latin script; segment times within ±0.3 s |
| 5 | Same clip → Claude translation (En, Hi, Te, Ml, Ar) | Tech names correct; no "impossible" lines |
| 6 | Generate in `strict_slot` + Per line | Each line starts within ±50 ms of the original; voice recognisably mine |
| 7 | Rushed-line flag + shorten | A deliberately long line gets flagged, shortened and fits |
| 8 | Export gate | Export lists flagged lines and asks before continuing |
| 9 | Full 10-minute video, 4 languages | End-to-end listen: no clicks, gaps or level jumps; total pod time ≤ 1.5 h |
| 10 | Upstream merge | `git merge upstream/main` succeeds with only expected conflicts |

Record the real GPU minutes from test 9; they replace the estimates in the cost table.

## 10. Monthly cost for 20 videos

About **₹2,400 (AED 93) a month** on RunPod Secure for 20 ten-minute videos in 4 languages, against about ₹1,71,000 (AED 6,610) at the ElevenLabs Pro-plan dubbing rate. Assumes 1.5 GPU-hours per video (estimate; test 9 replaces it).

Rates: RunPod RTX 4090 Secure $0.69/h, Community $0.34/h, storage \~$0.07/GB/month; [Sarvam STT](https://docs.sarvam.ai/api/pricing) ₹0.49/min (₹1,000 free credits to start); Claude Code covered by the Pro plan. 1 USD ≈ ₹95 (Wise mid-market ₹94.85), 1 USD = AED 3.6725.

| Item | Quantity | USD | INR | AED |
| --- | --- | --- | --- | --- |
| RunPod RTX 4090 Secure | 30 GPU-hours | $20.70 | ₹1,966 | 76.02 |
| Network volume | 50 GB | $3.50 | ₹332 | 12.85 |
| Sarvam STT | 200 min of source audio | $1.03 | ₹98 | 3.79 |
| Claude Code translation | — | $0 extra | ₹0 | 0 |
| **Total (Secure)** |  | **$25.23** | **₹2,397** | **92.66** |
| Total with Community GPU instead |  | $14.73 | ₹1,400 | 54.10 |
| For comparison: Sarvam Dubbing API | 800 dubbed min × ₹40 | $336.84 | ₹32,000 | 1,237.05 |
| For comparison: ElevenLabs dubbing at Pro-plan rate | 800 dubbed min × \~$2.25 | $1,800 | ₹1,71,000 | 6,610.50 |

One-time: about 20 GPU-hours of build and testing (\~$14, ₹1,311, AED 51). Card payments add your bank's forex markup.

## 11. Later phases (do not build now)

Each starts only after Phase 1 passes and a side-by-side listening test on my own clip shows it beats OmniVoice for that language.

| Phase | Change | Starts when |
| --- | --- | --- |
| 2 | Maya 2 Native engine (Indian languages) as a sidecar adapter | Te/Ml/Hi output from OmniVoice is not good enough |
| 2 | ZONOS3-Mini engine (Arabic, English, 40+ languages, emotion steering) | Arabic/English emotion is not good enough |
| 3 | Per-language engine routing (`engine_by_language`) | Two or more engines are worth keeping |
| 3 | Seed-VC timbre fix through the existing RVC hook | A good engine drifts from my voice |
| 4 | ElevenLabs TTS engine for single hard languages | Open models fail a language I need |
| 4 | OmniVoice fine-tune on my own recordings | Voice similarity is the only remaining gap |

## 12. Sources

- [VoiceStudio repo](https://github.com/debpalash/VoiceStudio) (commit `b6f05ec`, 16 Nov 2026): `docs/remote-gpu.md`, `docs/install/docker.md`, `docs/engines/openai-compatible-asr.md`, `docs/electron-batch.md`, `backend/api/routers/dub_generate.py`, `backend/services/fit_planner.py`, `backend/services/duration_planner.py`
- [Sarvam Speech-to-Text API](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe)
- [Sarvam Saaras models](https://docs.sarvam.ai/api-reference-docs/getting-started/models/saaras)
- [Sarvam API pricing](https://docs.sarvam.ai/api/pricing) · [free credits](https://sarvam.ai/api-pricing)
- [Sarvam Tamil STT (Tanglish)](https://www.sarvam.ai/apis/speech-to-text/tamil)
- [RunPod pricing (Hackceleration, Jun 2026)](https://www.hackceleration.com/labs/runpod-pricing) · [RunPod storage (Layer3, Jul 2026)](https://www.layer3labs.io/guides/is-runpod-worth-it)
- [ElevenLabs Dubbing credits (Stork)](https://www.stork.ai/blog/elevenlabs-dubbing-2026)
- [USD/INR (Wise)](https://wise.com/in/currency-converter/usd-to-inr-rate) · [AED peg (The National)](https://www.thenationalnews.com/lifestyle/2024/11/22/uae-dirham-dollar-peg/)
