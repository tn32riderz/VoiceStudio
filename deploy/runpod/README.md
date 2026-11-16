# RunPod backend for the Intel Mac (personal v1)

The Intel Mac can't run the VoiceStudio backend
([#889](https://github.com/debpalash/VoiceStudio/issues/889)), so the backend
runs on a RunPod GPU and the Mac app is only the interface. This is the
[remote GPU backend](../../docs/remote-gpu.md) mode, with RunPod's HTTPS proxy
in place of Tailscale.

| File | Purpose |
| --- | --- |
| `start.sh` | Image entrypoint: checks the API key, stores everything on `/workspace`, starts the Sarvam ASR proxy (if configured) and the backend |
| `Dockerfile` | Thin layer on top of the unchanged upstream CUDA image (`deploy/Dockerfile`) |
| `../../.github/workflows/personal-runpod-image.yml` | Builds and pushes both images to GHCR |
| `tests/test_start_sh.py` | `pytest deploy/runpod/tests` |

## 1. Build the image (once, then on every push)

1. On the fork, open **Actions** and enable workflows if GitHub asks.
2. Push to `personal/v1`, or run **Personal RunPod image →
   Run workflow**. The first build takes about 30–60 minutes; later ones reuse
   the layer cache.
3. Result: `ghcr.io/tn32riderz/voicestudio:v1` (also
   `:v1-<commit>` for rolling back).
4. GHCR creates new packages as **private**. Either:
   - make it public: GitHub → your profile → **Packages → voicestudio →
     Package settings → Change visibility → Public** (the image contains no
     keys), or
   - keep it private and add a RunPod **Container Registry Credential** for
     `ghcr.io` (username `tn32riderz`, password a GitHub token with only
     `read:packages`).

## 2. Generate the API key

On any machine:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Save it in your password manager. `start.sh` refuses keys shorter than 24
characters. Never put it in the repo.

## 3. RunPod network volume and template

**Storage → New Network Volume**: 100 GB, in a data centre that has RTX 4090s.
Models, projects and the Hugging Face cache all live here, so they survive a
pod stop.

**Templates → New Template**:

| Field | Value |
| --- | --- |
| Container image | `ghcr.io/tn32riderz/voicestudio:v1` |
| Container disk | 20 GB |
| Volume mount path | `/workspace` |
| Expose HTTP ports | `3900` |
| Expose TCP ports | none |
| Start command | leave empty (the image runs `start.sh`) |

Environment variables. Use RunPod **Secrets** (`{{ RUNPOD_SECRET_<name> }}`)
for the keys, not plain values:

| Name | Required | Value |
| --- | --- | --- |
| `OMNIVOICE_API_KEY` | yes | the key from step 2 (40+ characters recommended; under 24 is refused) |
| `SARVAM_API_KEY` | for Tanglish ASR (Change 2) | from the Sarvam dashboard |
| `KEYTERMS_FILE` | optional | e.g. `/workspace/keyterms.txt` to edit Sarvam keyterms without rebuilding |
| `ANTHROPIC_API_KEY` | for Claude translation (Change 3) | from the Anthropic Console; set a monthly spend limit there first. A truncated key is refused at start |
| `RUNPOD_API_KEY` | only for idle auto-stop (Change 5) | RunPod → Settings → API Keys; auto-stop stays off without it |
| `ELEVENLABS_API_KEY` | optional (Change 9) | only if you add the ElevenLabs engine |
| `ELEVENLABS_VOICE_ID` | optional (Change 9) | your cloned voice ID, with the key above |

Claude translation runs on the pod through the backend's `anthropic` LLM
provider and is billed per token by Anthropic, separately from a Claude Pro
plan. See [v1 decisions](../../docs/personal/v1-decisions.md).

`start.sh` sets the rest itself: `OMNIVOICE_DATA_DIR=/workspace/omnivoice_data`,
`HF_HOME=/workspace/hf_cache`, `OMNIVOICE_SERVER_MODE=1`, backend on
`0.0.0.0:3900`, ASR proxy on `127.0.0.1:9876`.

**Deploy**: Pods → Deploy → **RTX 4090 (24 GB)**, Secure Cloud (or Community
for about half the price) → select the template and the network volume.

Once it is running, the backend is at:

```
https://<pod-id>-3900.proxy.runpod.net
```

`https://<pod-id>-3900.proxy.runpod.net/health` should answer without a key.

## 4. The Mac app

1. Install `VoiceStudio-<version>-mac-x64.dmg` from the
   [releases page](https://github.com/debpalash/VoiceStudio/releases/latest)
   (UI only on Intel; see [macOS install](../../docs/install/macos.md)).
2. **Settings → Sharing → Remote backend**:
   - **Backend URL**: `https://<pod-id>-3900.proxy.runpod.net`
   - **API key**: the `OMNIVOICE_API_KEY` value
   - **Test connection**, then **Save & reload**.
3. Finish the setup wizard. It runs against the pod and downloads the models
   to `/workspace`.
4. For Tanglish transcription (needs `SARVAM_API_KEY` on the pod):
   **Settings → Models → ASR → OpenAI-compatible (remote server)**, Server URL
   `http://127.0.0.1:9876/v1`, Model `saaras-v4-codemix`, API key empty,
   **Test connection**, then **Use**. The URL is loopback *on the pod*: the
   backend calls the proxy, not the Mac. Details in
   [the proxy README](../../tools/sarvam_asr_proxy/README.md).

The pod ID changes when you deploy a new pod, though not when you stop and
start the same one. After a new deploy, update the Backend URL.

## 5. Check it works (Change 1 done-when)

1. The Mac app connects, and progress bars update live (WebSocket through the
   RunPod proxy).
2. The setup wizard completes.
3. A 30-second test clip dubs end to end.
4. Stop the pod, start it again: the app reconnects and the models load from
   `/workspace` with no new download (the pod log shows no download progress,
   and `du -sh /workspace/hf_cache` stays the same).

## Security

- The RunPod proxy URL is **public internet**. Upstream recommends against
  exposing a backend publicly ([remote GPU security notes](../../docs/remote-gpu.md#security-notes));
  here the API key is the only thing guarding it. Use a long random key,
  never share the URL together with the key, and stop the pod when you're
  not using it.
- To rotate the key: change the RunPod secret, restart the pod, and enter the
  new key in the Mac app.
- A stronger alternative is Tailscale inside the pod with no public HTTP port.
  That is not set up here.
- If the log warns `/workspace is not a mounted volume`, the network volume
  isn't attached and everything will be downloaded again on the next start.
