#!/usr/bin/env bash
# RunPod entrypoint for the personal Phase 1 image (see deploy/runpod/README.md).
#
# - Keeps models, projects and the Hugging Face cache on the RunPod network
#   volume at /workspace so a stopped pod restarts without re-downloading.
# - Refuses to start without OMNIVOICE_API_KEY: the RunPod HTTP proxy is
#   public, so the key is the only thing guarding the backend.
# - Starts the Sarvam ASR proxy on loopback when SARVAM_API_KEY is set.
#
# START_SH_DRY_RUN=1 prints what would run instead of running it (tests).
# RUNPOD_WORKSPACE and APP_DIR override /workspace and /app (tests only).
set -euo pipefail

APP_DIR="${APP_DIR:-/app}"
WORKSPACE="${RUNPOD_WORKSPACE:-/workspace}"
BACKEND_HOST=0.0.0.0
BACKEND_PORT=3900
ASR_PROXY_HOST=127.0.0.1
ASR_PROXY_PORT=9876
MIN_KEY_LENGTH=24

die() { echo "start.sh: $*" >&2; exit 1; }
warn() { echo "start.sh: warning: $*" >&2; }
dry_run() { [[ "${START_SH_DRY_RUN:-0}" == "1" ]]; }

if [[ -z "${OMNIVOICE_API_KEY:-}" ]]; then
  die "OMNIVOICE_API_KEY is not set. Add it to the RunPod template's environment variables."
fi
if (( ${#OMNIVOICE_API_KEY} < MIN_KEY_LENGTH )); then
  die "OMNIVOICE_API_KEY is shorter than ${MIN_KEY_LENGTH} characters. Generate one with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
fi

export OMNIVOICE_DATA_DIR="${WORKSPACE}/omnivoice_data"
export HF_HOME="${WORKSPACE}/hf_cache"
export OMNIVOICE_SERVER_MODE=1

if [[ ! -d "$WORKSPACE" ]]; then
  die "${WORKSPACE} does not exist. Attach the RunPod network volume at ${WORKSPACE}."
fi
# A volume is a different filesystem from its parent directory. Without one,
# everything below is lost when the pod stops.
if [[ "$(stat -c %d "$WORKSPACE")" == "$(stat -c %d "$(dirname "$WORKSPACE")")" ]]; then
  warn "${WORKSPACE} is not a mounted volume; models will be downloaded again after every pod restart."
fi
mkdir -p "$OMNIVOICE_DATA_DIR" "$HF_HOME"

if dry_run; then
  echo "ENV OMNIVOICE_DATA_DIR=${OMNIVOICE_DATA_DIR}"
  echo "ENV HF_HOME=${HF_HOME}"
  echo "ENV OMNIVOICE_SERVER_MODE=${OMNIVOICE_SERVER_MODE}"
fi

cd "$APP_DIR"

if [[ -n "${SARVAM_API_KEY:-}" ]]; then
  if [[ -d "${APP_DIR}/tools/sarvam_asr_proxy" ]]; then
    proxy_cmd=(python3 -m tools.sarvam_asr_proxy --host "$ASR_PROXY_HOST" --port "$ASR_PROXY_PORT")
    if dry_run; then
      echo "PROXY ${proxy_cmd[*]}"
    else
      # Restart the proxy if it exits; the backend keeps serving either way.
      (
        while true; do
          "${proxy_cmd[@]}" || true
          warn "Sarvam ASR proxy exited; restarting in 3 s."
          sleep 3
        done
      ) &
    fi
  else
    warn "SARVAM_API_KEY is set but tools/sarvam_asr_proxy is not in this image; ASR proxy not started."
  fi
fi

backend_cmd=(python3 backend/docker_entrypoint.py --host "$BACKEND_HOST" --port "$BACKEND_PORT")
if dry_run; then
  echo "BACKEND ${backend_cmd[*]}"
  exit 0
fi
exec "${backend_cmd[@]}"
