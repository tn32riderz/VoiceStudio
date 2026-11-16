# Personal v1 RunPod image: the upstream CUDA image (built from
# deploy/Dockerfile by .github/workflows/personal-runpod-image.yml) plus the
# RunPod entrypoint. Kept as a thin layer so deploy/Dockerfile stays untouched
# and upstream merges stay clean.
ARG BASE_IMAGE=ghcr.io/tn32riderz/voicestudio:v1-base
FROM ${BASE_IMAGE}

COPY deploy/runpod/start.sh /app/deploy/runpod/start.sh
RUN chmod 0755 /app/deploy/runpod/start.sh
# Sarvam ASR proxy (Change 2). Its dependencies (FastAPI, uvicorn, httpx,
# numpy, python-multipart) and ffmpeg are already in the base image.
COPY tools/sarvam_asr_proxy/ /app/tools/sarvam_asr_proxy/
RUN python3 -c "import tools.sarvam_asr_proxy.app"

# Tanglish translation preset (Change 3): style prompt + glossary, applied by
# backend/services/translation_preset.py when the anthropic provider is active.
COPY presets/ /app/presets/

EXPOSE 3900
ENTRYPOINT ["/app/deploy/runpod/start.sh"]
