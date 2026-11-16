"""FastAPI surface: the subset of the OpenAI audio API VoiceStudio's ASR engine calls."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from typing import Callable, Optional

import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from . import audio, pipeline
from .keyterms import load_keyterms
from .sarvam import SarvamClient, SarvamError

logger = logging.getLogger(__name__)

MODEL_ID = "saaras-v4-codemix"
SUPPORTED_FORMATS = ("json", "text", "verbose_json")
# Uploads are spooled to disk; this only stops a runaway client.
MAX_UPLOAD_BYTES = 2 * 1024**3
MAX_DURATION_S = 3 * 3600


def _error(status: int, message: str, kind: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": kind}})


def create_app(
    recognizer_factory: Optional[Callable[[], pipeline.Recognizer]] = None,
    decoder: Callable[[str], np.ndarray] = audio.decode_to_mono16k,
    keyterms_loader: Callable[[], list[str]] = load_keyterms,
) -> FastAPI:
    """Build the app. Tests inject a fake recognizer and decoder."""
    app = FastAPI(title="Sarvam ASR proxy", docs_url=None, redoc_url=None, openapi_url=None)
    state: dict = {}

    def recognizer() -> Optional[pipeline.Recognizer]:
        if "recognizer" not in state:
            if recognizer_factory is not None:
                state["recognizer"] = recognizer_factory()
            else:
                key = os.environ.get("SARVAM_API_KEY", "")
                state["recognizer"] = SarvamClient(key) if key else None
        return state["recognizer"]

    @app.get("/health")
    async def health():
        return {"ok": True, "configured": recognizer() is not None}

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "sarvam"}]}

    @app.post("/v1/audio/transcriptions")
    async def transcriptions(
        file: UploadFile = File(...),
        model: str = Form(MODEL_ID),
        language: Optional[str] = Form(None),
        prompt: Optional[str] = Form(None),  # accepted for compatibility; Sarvam has no prompt field
        response_format: str = Form("json"),
        temperature: Optional[float] = Form(None),  # accepted for compatibility; ignored
    ):
        if response_format not in SUPPORTED_FORMATS:
            return _error(400, f"response_format must be one of {', '.join(SUPPORTED_FORMATS)}")
        rec = recognizer()
        if rec is None:
            return _error(503, "SARVAM_API_KEY is not set on the server", "server_error")

        started = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".upload") as tmp:
            size = 0
            while block := await file.read(1024 * 1024):
                size += len(block)
                if size > MAX_UPLOAD_BYTES:
                    return _error(413, "audio file is too large")
                tmp.write(block)
            tmp.flush()
            try:
                samples = await asyncio.to_thread(decoder, tmp.name)
            except audio.AudioDecodeError as exc:
                return _error(400, str(exc))
        duration = len(samples) / audio.SAMPLE_RATE
        if duration > MAX_DURATION_S:
            return _error(400, f"audio is longer than {MAX_DURATION_S // 3600} hours")

        try:
            result = await pipeline.transcribe_samples(
                samples, rec, language=language, keyterms=keyterms_loader() or None
            )
        except SarvamError as exc:
            status = 429 if exc.status == 429 else 502
            logger.warning("Transcription failed: %s", exc)
            return _error(status, str(exc), "upstream_error")

        logger.info(
            "Transcribed %.1f s of audio into %d segments in %.1f s",
            duration, len(result["segments"]), time.perf_counter() - started,
        )
        if response_format == "text":
            return PlainTextResponse(result["text"])
        if response_format == "json":
            return {"text": result["text"]}
        return result

    return app
