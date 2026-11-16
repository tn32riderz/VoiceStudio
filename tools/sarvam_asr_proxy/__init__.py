"""OpenAI-compatible ASR proxy in front of Sarvam Saaras (personal fork).

VoiceStudio's "OpenAI-compatible (remote server)" ASR engine calls this on
loopback; it chunks the audio, calls Sarvam's REST speech-to-text API and
returns OpenAI ``verbose_json``. See README.md in this folder.

Layout, so another recogniser (Whisper) can sit beside Sarvam later:

- ``audio``      decode to 16 kHz mono, split at the quietest point, encode WAV
- ``languages``  OpenAI/ISO codes <-> Sarvam BCP-47 codes
- ``keyterms``   recognition-bias terms from ``KEYTERMS_FILE``
- ``sarvam``     the Sarvam HTTP client (retries, concurrency limit)
- ``pipeline``   chunk -> recognise -> offset timestamps -> segments
- ``app``        the FastAPI surface (``/v1/models``, ``/v1/audio/transcriptions``)
"""
