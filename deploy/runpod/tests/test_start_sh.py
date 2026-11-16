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


def test_never_prints_secrets(tmp_path):
    secret, sarvam = "x" * 40, "sarvam-secret-value"
    result = run(tmp_path, with_proxy=True, OMNIVOICE_API_KEY=secret, SARVAM_API_KEY=sarvam)
    for text in (result.stdout, result.stderr):
        assert secret not in text
        assert sarvam not in text
