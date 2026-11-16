"""Tests for deploy/runpod/start.sh, run in its dry-run mode.

Run explicitly: ``pytest deploy/runpod/tests`` (``deploy`` is outside the
default ``testpaths``).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "start.sh"
GOOD_KEY = "k" * 32

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def run(tmp_path: Path, *, with_proxy: bool = False, **env: str) -> subprocess.CompletedProcess:
    app = tmp_path / "app"
    app.mkdir(exist_ok=True)
    if with_proxy:
        (app / "tools" / "sarvam_asr_proxy").mkdir(parents=True, exist_ok=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    base = {
        "PATH": os.environ["PATH"],
        "START_SH_DRY_RUN": "1",
        "APP_DIR": str(app),
        "RUNPOD_WORKSPACE": str(workspace),
    }
    return subprocess.run(
        ["bash", str(SCRIPT)], env={**base, **env}, capture_output=True, text=True, check=False
    )


def test_requires_api_key(tmp_path):
    result = run(tmp_path)
    assert result.returncode != 0
    assert "OMNIVOICE_API_KEY is not set" in result.stderr


def test_rejects_short_api_key(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY="short")
    assert result.returncode != 0
    assert "shorter than 24" in result.stderr


def test_sets_workspace_paths_and_server_mode(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY)
    assert result.returncode == 0, result.stderr
    workspace = tmp_path / "workspace"
    assert f"ENV OMNIVOICE_DATA_DIR={workspace}/omnivoice_data" in result.stdout
    assert f"ENV HF_HOME={workspace}/hf_cache" in result.stdout
    assert "ENV OMNIVOICE_SERVER_MODE=1" in result.stdout
    assert (workspace / "omnivoice_data").is_dir()
    assert (workspace / "hf_cache").is_dir()


def test_starts_backend_on_all_interfaces_port_3900(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY)
    assert "BACKEND python3 backend/docker_entrypoint.py --host 0.0.0.0 --port 3900" in result.stdout


def test_warns_when_workspace_is_not_a_volume(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY)
    assert "not a mounted volume" in result.stderr


def test_missing_workspace_fails(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY, RUNPOD_WORKSPACE=str(tmp_path / "nope"))
    assert result.returncode != 0
    assert "Attach the RunPod network volume" in result.stderr


def test_no_proxy_without_sarvam_key(tmp_path):
    result = run(tmp_path, with_proxy=True, OMNIVOICE_API_KEY=GOOD_KEY)
    assert "PROXY" not in result.stdout


def test_starts_proxy_on_loopback_with_sarvam_key(tmp_path):
    result = run(tmp_path, with_proxy=True, OMNIVOICE_API_KEY=GOOD_KEY, SARVAM_API_KEY="s" * 10)
    assert "PROXY python3 -m tools.sarvam_asr_proxy --host 127.0.0.1 --port 9876" in result.stdout


def test_warns_when_proxy_missing_from_image(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY, SARVAM_API_KEY="s" * 10)
    assert result.returncode == 0
    assert "PROXY" not in result.stdout
    assert "not in this image" in result.stderr


def test_rejects_truncated_anthropic_key(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY, ANTHROPIC_API_KEY="sk-ant-short")
    assert result.returncode != 0
    assert "ANTHROPIC_API_KEY looks truncated" in result.stderr
    assert "sk-ant-short" not in result.stderr


def test_accepts_full_anthropic_key_and_runs_without_one(tmp_path):
    assert run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY, ANTHROPIC_API_KEY="sk-ant-" + "a" * 90).returncode == 0
    assert run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY).returncode == 0


def test_never_prints_secrets(tmp_path):
    secret, sarvam, anthropic = "x" * 40, "sarvam-secret-value", "sk-ant-" + "b" * 90
    result = run(
        tmp_path, with_proxy=True,
        OMNIVOICE_API_KEY=secret, SARVAM_API_KEY=sarvam, ANTHROPIC_API_KEY=anthropic,
    )
    for text in (result.stdout, result.stderr):
        assert secret not in text
        assert sarvam not in text
        assert anthropic not in text


def test_project_bundles_are_kept_on_the_volume(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY)
    assert f"ENV OMNIVOICE_PROJECT_BUNDLE_DIR={tmp_path}/workspace/projects" in result.stdout
    assert (tmp_path / "workspace" / "projects").is_dir()


def test_idle_stop_is_off_unless_enabled(tmp_path):
    # RunPod sets these two in every pod; they alone must not start auto-stop.
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY, RUNPOD_API_KEY="rp-key", RUNPOD_POD_ID="pod1")
    assert "IDLE_STOP" not in result.stdout


def test_idle_stop_needs_the_pod_id(tmp_path):
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY, RUNPOD_API_KEY="rp-secret-key",
                 RUNPOD_AUTO_STOP="1")
    assert "IDLE_STOP" not in result.stdout
    assert "RUNPOD_POD_ID is not" in result.stderr
    assert "rp-secret-key" not in result.stdout + result.stderr


def test_idle_stop_starts_when_key_and_pod_id_are_set(tmp_path):
    app = tmp_path / "app" / "deploy" / "runpod"
    app.mkdir(parents=True)
    (app / "idle_stop.py").write_text("")
    result = run(tmp_path, OMNIVOICE_API_KEY=GOOD_KEY, RUNPOD_API_KEY="rp-secret-key",
                 RUNPOD_POD_ID="pod1", RUNPOD_AUTO_STOP="1")
    assert f"IDLE_STOP python3 {tmp_path}/app/deploy/runpod/idle_stop.py" in result.stdout
    assert "rp-secret-key" not in result.stdout + result.stderr
