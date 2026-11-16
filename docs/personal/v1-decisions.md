# v1 — decisions that change the spec

`v1-spec.md` is kept word for word. These owner decisions (16 Nov 2026) replace
the parts of it that did not match upstream `b6f05ec`.

| # | Spec says | Code at `b6f05ec` | Decision |
| --- | --- | --- | --- |
| 1 | Translate with **Claude Code CLI on the Mac** | The CLI bridge lives in Electron main on `127.0.0.1` and is handed only to a backend Electron starts itself; `backend/services/llm_cli.py` rejects any other address. A RunPod backend cannot reach it. | Use the backend's existing **`anthropic`** LLM provider (`backend/services/llm_providers.py`) on the pod with `ANTHROPIC_API_KEY` (env var, never committed). |
| 2 | "Mirror source delivery = on" as a session default | It is a one-shot menu action, **Match original delivery**, not a setting. | No code. `deploy/runpod/WORKFLOW.md` tells you when to run it. |
| 3 | Style prompt as a "prefs default" | The prompt is per-project (`translationInstructions`); no app-wide default exists. | Add a small preference that pre-fills new projects; still editable per project. |

## How the decisions affect later changes

- **Change 3 (translation preset):** the Tanglish style prompt and glossary
  become the default prompt of the `anthropic` provider instead of the
  agent's. Translation runs on the pod and is billed per token by Anthropic,
  separately from the Pro plan, so the cost table's "$0" translation line no
  longer holds. Set a monthly spend limit in the Anthropic Console.
- **Change 4 (timing lock):** does not force "Mirror source delivery" on. The
  other locked defaults (`strict_slot`, Per line, preserve background) are
  unchanged.
- **Change 11 (emotion layer):** measures delivery itself, so emotion still
  carries over without the manual action.

## Other notes

- The backend URL is set under **Settings → Sharing → Remote backend**.
- `CLAUDE.md` forbids agent attribution in commits, so commits carry only the
  owner's git identity (`Vignesh <tn32riderz@users.noreply.github.com>`).
- No `changelog.d/` fragments: this is a personal fork with no upstream PR, and
  skipping them avoids merge conflicts with upstream.
