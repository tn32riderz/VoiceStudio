# Phase 1 — decisions that change the spec

`phase1-spec.md` is kept verbatim. These owner decisions (16 Nov 2026) replace
the parts of it that did not match upstream `b6f05ec`.

| Spec says | Code at `b6f05ec` | Decision |
| --- | --- | --- |
| Translate with **Claude Code CLI on the Mac** (Change 3 task 3, Change 5 step 3) | The CLI bridge lives in Electron main on `127.0.0.1` and is handed only to a backend Electron starts itself; `backend/services/llm_cli.py` rejects any other address. A RunPod backend cannot reach it. | Use the existing **Anthropic (Claude)** LLM provider on the pod with `ANTHROPIC_API_KEY` (env var, never committed). Claude API usage is billed per token, so the cost table's "Claude Code translation — $0" line no longer holds. |
| "Mirror source delivery = on" as a session default (Change 4 task 1) | It is a one-shot menu action, **Match original delivery**, not a setting. | No code. `deploy/runpod/WORKFLOW.md` lists it as a manual step after transcription. |
| Style prompt as a "prefs default" (Change 3 task 1) | The prompt is per-project (`translationInstructions`); no app-wide default exists. | Add a small preference that pre-fills new projects; still editable per project. |

Other notes:

- `CLAUDE.md` forbids agent attribution in commits, so commits carry only the
  owner's git identity.
- No `changelog.d/` fragments: this is a personal fork with no upstream PR, and
  skipping them avoids merge conflicts with upstream.
