"""Checks for deploy/colab/VoiceStudio_v1_trial_Colab.ipynb.

Run explicitly: ``pytest deploy/colab/tests`` (``deploy`` is outside the
default ``testpaths``).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRIAL = ROOT / "deploy" / "colab" / "VoiceStudio_v1_trial_Colab.ipynb"
UPSTREAM = ROOT / "notebooks" / "OmniVoice_Studio_Colab.ipynb"


def code_cells(path: Path) -> list[str]:
    nb = json.loads(path.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def trial_source() -> str:
    return "\n".join(code_cells(TRIAL))


def test_notebook_is_valid_nbformat_4_on_a_gpu_runtime():
    nb = json.loads(TRIAL.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    assert nb["metadata"]["accelerator"] == "GPU"
    for cell in nb["cells"]:
        assert cell["cell_type"] in {"markdown", "code"}
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None


def test_code_cells_are_valid_python():
    for source in code_cells(TRIAL):
        ast.parse(source)


def test_every_reused_upstream_cell_still_exists():
    """Fails when upstream renames or removes a cell the trial runs."""
    tree = ast.parse(trial_source())
    headings = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "UPSTREAM_CELLS" for t in node.targets):
            headings = ast.literal_eval(node.value)
    assert headings, "UPSTREAM_CELLS not found"
    upstream_starts = [s for s in code_cells(UPSTREAM)]
    for key, heading in headings.items():
        matches = [s for s in upstream_starts if s.startswith(heading)]
        assert len(matches) == 1, f"{key}: {heading!r} matches {len(matches)} upstream cells"


def test_upstream_cells_use_the_repo_dir_the_trial_clones_to():
    upstream = "\n".join(code_cells(UPSTREAM))
    assert 'REPO_DIR = "/content/VoiceStudio"' in upstream
    assert 'REPO_DIR = "/content/VoiceStudio"' in trial_source()


def test_clones_the_fork_branch():
    source = trial_source()
    assert 'FORK_URL = "https://github.com/tn32riderz/VoiceStudio"' in source
    assert 'BRANCH = "personal/v1"' in source
    assert '"--branch", BRANCH, FORK_URL' in source


def test_proxy_is_loopback_only_and_matches_start_sh():
    source = trial_source()
    assert '"-m", "tools.sarvam_asr_proxy", "--host", "127.0.0.1", "--port", "9876"' in source
    start_sh = (ROOT / "deploy" / "runpod" / "start.sh").read_text(encoding="utf-8")
    assert "ASR_PROXY_PORT=9876" in start_sh


def test_no_secrets_in_the_notebook_and_values_never_printed():
    raw = TRIAL.read_text(encoding="utf-8")
    for pattern in (r"sk-ant-[A-Za-z0-9_-]{8,}", r"sk_[A-Za-z0-9]{16,}", r"hf_[A-Za-z0-9]{20,}"):
        assert not re.search(pattern, raw), pattern
    source = trial_source()
    # Keys are read only from Colab Secrets.
    assert "userdata.get(name)" in source
    for line in source.splitlines():
        if "print(" in line:
            assert "value" not in line.split("print(", 1)[1], line
            assert "os.environ[" not in line.split("print(", 1)[1], line
