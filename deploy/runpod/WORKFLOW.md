# Dubbing workflow on the RunPod pod

One 10-minute Tanglish video into four languages. Target: **1 to 1.5 GPU-hours
and about 30 minutes of your time** per video. Use the interactive **Dub** page
for each video, not the batch queue: batch skips the line review that keeps
sync and emotion right.

Names in **bold** are the app's labels (English UI). If a label differs on your
screen, tell me and I will correct this file.

## Before the first video (once)

| Where | Setting | Value |
| --- | --- | --- |
| RunPod template | `OMNIVOICE_API_KEY` | your 40+ character key |
| RunPod template | `SARVAM_API_KEY` | from the Sarvam dashboard (Tamil transcription) |
| RunPod template | `ANTHROPIC_API_KEY` | from the Anthropic Console, monthly spend limit set |
| RunPod template | `RUNPOD_API_KEY` | optional: lets the pod stop itself when idle |
| Mac app | **Settings → Sharing → Remote backend** | `https://<pod-id>-3900.proxy.runpod.net` + your `OMNIVOICE_API_KEY` |
| Mac app | **Settings → LLM Providers** | **Anthropic (Claude)** active, key comes from the pod's `ANTHROPIC_API_KEY` |
| Dub page | **Engine** (translation) | the LLM engine, not Google/NLLB |
| Dub page | Timing | **Strict slot** (default) |
| Dub page | Voice match | **Per line** (default) |

The Tanglish style prompt and glossary apply by themselves when the active LLM
provider is Anthropic and the source language is Tamil (`presets/tanglish-dub/`).

## Per video

1. **Start the pod** (RunPod → Pods → Start). Wait for the Mac app to connect.
2. **Dub page → upload the video.** Source language **Tamil**. Transcribe
   (Sarvam). Read the Tamil text once and fix wrong words.
3. **Pick the target languages** and translate. Technical names should stay as
   written; glossary terms are in `presets/tanglish-dub/glossary.csv`.
4. **Match original delivery** (the menu action, not a setting): run it once
   after translating when you want the energy of the original voice carried
   over. Skip it for flat, narration-style videos.
5. **Generate.** Then fix flagged lines:
   - **Rushed ×N** on a line: press **Shorten**, then regenerate that line.
   - **Won't fit +Ns**: shorten the text by hand or with **Apply** on the
     suggestion, then regenerate.
6. **Listen once per language**, end to end.
7. **Export** one WAV per language. If the export lists rushed or won't-fit
   lines, go back and fix them; use **Export anyway** only on purpose.
8. Upload each WAV as an extra audio track on YouTube.
9. **Stop the pod** (RunPod → Stop), unless idle auto-stop is on (below).

## Idle auto-stop

Set `RUNPOD_API_KEY` in the template. The pod then stops itself after 30
minutes with no backend activity (running jobs, downloads, open requests).

| Variable | Default | Meaning |
| --- | --- | --- |
| `RUNPOD_API_KEY` | unset (off) | RunPod API key; lets the pod stop itself |
| `RUNPOD_IDLE_MINUTES` | 30 (minimum 5) | idle time before stopping |
| `RUNPOD_IDLE_IGNORE_STREAMS` | unset | `1` = a Mac app left open with nothing running does not keep the pod alive |

The Mac app may keep a connection open while it is running, which counts as
activity. If the pod does not stop after you stopped working, set
`RUNPOD_IDLE_IGNORE_STREAMS=1` (see test notes below). A stopped pod keeps the
network volume; **Start** brings back models and projects without downloads.

## Projects

- Projects, transcripts and generated audio live in `/workspace/omnivoice_data`
  on the volume, so they survive a stop and start. Reopen a video from
  **Projects** in the app.
- Every project bundle you export (**Projects → Export project bundle**) is also
  copied to `/workspace/projects/` as `<name>-<date>.vsproject`.

## Costs to watch

- Pod: billed per hour while running. Stop it when you finish.
- Sarvam: per minute of source audio.
- Anthropic: per token, separate from your Claude plan. Check the Console after
  the first video and write the number down.
