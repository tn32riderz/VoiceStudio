# Free trial on Google Colab (before paying for RunPod)

[Open the trial notebook in Colab](https://colab.research.google.com/github/tn32riderz/VoiceStudio/blob/personal/v1/deploy/colab/VoiceStudio_v1_trial_Colab.ipynb)

`VoiceStudio_v1_trial_Colab.ipynb` runs the `personal/v1` branch on a free
Colab T4 GPU. The app opens in your browser through Colab's own proxy, so you
need neither the Mac app nor a tunnel. It reuses cells 1–6 of the upstream
notebook (`notebooks/OmniVoice_Studio_Colab.ipynb`) from the fork's checkout
and adds the Sarvam ASR proxy. `tests/test_colab_trial_notebook.py` fails if
upstream renames those cells.

| | Colab free (this notebook) | RunPod (`deploy/runpod`) |
| --- | --- | --- |
| Cost | $0 | about $0.34–0.69 an hour for an RTX 4090 |
| GPU | T4, 16 GB, not guaranteed | RTX 4090, 24 GB |
| Speed | Slower; good for checking quality | Full speed |
| Session | At most ~12 h; stops when idle or when the tab closes | Runs until you stop it |
| Models | Downloaded again each session | Kept on the network volume |
| Your data | Lost at session end, unless `USE_DRIVE = True` | Kept on the network volume |
| App | Browser tab | Mac app or browser |
| Translation | Argos or NLLB-200 (free, offline), or Claude with `ANTHROPIC_API_KEY` | Claude with `ANTHROPIC_API_KEY` |

Keys go in **Colab Secrets** (the key icon in the left sidebar), never in a
cell: `SARVAM_API_KEY` (optional, for Tanglish ASR) and `ANTHROPIC_API_KEY`
(optional, paid). No `OMNIVOICE_API_KEY` is needed: only your signed-in Google
browser session can reach the app.

Not covered here: Kaggle's free T4 ×2 (about 30 hours a week) has no built-in
port proxy, so it would need a public tunnel and the API key. Colab is the
simpler free route.

Tests: `pytest deploy/colab/tests`.
