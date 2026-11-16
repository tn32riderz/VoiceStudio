# Sarvam ASR proxy (Tanglish transcription)

Whisper mishandles Tamil–English code-switching. Sarvam's Saaras v4 in
`codemix` mode writes English words in Latin script and Tamil words in Tamil
script. VoiceStudio already supports any
[OpenAI-compatible ASR server](../../docs/engines/openai-compatible-asr.md),
so this is a small server in front of Sarvam, not a change to VoiceStudio.

```
VoiceStudio backend ──HTTP, loopback──▶ proxy 127.0.0.1:9876 ──HTTPS──▶ api.sarvam.ai
 (OpenAI-compatible ASR engine)          chunks ≤ 28 s at pauses,        saaras:v4, codemix,
                                         offsets timestamps back         with_timestamps
```

## What it does

- `GET /v1/models` → `saaras-v4-codemix`
- `POST /v1/audio/transcriptions` (OpenAI form fields `file`, `model`,
  `language`, `prompt`, `response_format`):
  1. decodes the upload to 16 kHz mono with ffmpeg;
  2. splits it into chunks of at most 28 s (Sarvam's REST limit is 30 s),
     cutting at the quietest 20 ms in the last 8 s before each limit, so a cut
     falls in a pause, not inside a word;
  3. sends each chunk to Sarvam (`model=saaras:v4`, `mode=codemix`,
     `with_timestamps=true`, `language_code` from `language`: `ta` → `ta-IN`,
     other Indic codes likewise, missing or unsupported → `unknown`), with up
     to 50 keyterms;
  4. adds each chunk's start time to its phrase timestamps. A chunk with no
     timestamps becomes one segment covering the chunk;
  5. returns `verbose_json` (`{text, language, duration, segments:[{id, start, end, text}]}`),
     `json` (`{text}`) or plain `text`.
- Retries 429, 5xx and network errors with exponential backoff (honouring
  `Retry-After`), up to 5 attempts. At most 3 Sarvam calls run at once.
- Never logs audio, transcripts or the API key. Binds to loopback only, because
  it has no authentication and spends your Sarvam credit.

## Settings

| Env var | Default | Meaning |
| --- | --- | --- |
| `SARVAM_API_KEY` | none (required) | Without it, transcription requests return 503 |
| `KEYTERMS_FILE` | bundled `keyterms.txt` | One term per line, `#` comments, max 50 × 64 chars. Use `/workspace/keyterms.txt` to edit without rebuilding; empty string disables keyterms |
| `SARVAM_MODEL` | `saaras:v4` | Fallback: `saaras:v3` |
| `SARVAM_MODE` | `codemix` | Sarvam's docs say `mode` applies to `saaras:v3`, but also list every mode for v4. If v4 output is not code-mixed, try `SARVAM_MODEL=saaras:v3` |

On RunPod, `deploy/runpod/start.sh` starts the proxy automatically when
`SARVAM_API_KEY` is set, and restarts it if it exits.

## In VoiceStudio

**Settings → Models → ASR → OpenAI-compatible (remote server)**:

- **Server URL**: `http://127.0.0.1:9876/v1` (plain HTTP is allowed because it
  is loopback on the pod)
- **Model**: `saaras-v4-codemix`
- **API key**: leave empty (the proxy holds the Sarvam key)
- **Test connection**, then **Use** on the engine's row.

Keep WhisperX installed as the fallback for non-Indian source languages:
switch back to it with **Use** on its row.

## Run and test

```bash
python -m tools.sarvam_asr_proxy --host 127.0.0.1 --port 9876
```

```bash
pytest tools/sarvam_asr_proxy
```

The tests use a mocked Sarvam, so they need no key or network.
