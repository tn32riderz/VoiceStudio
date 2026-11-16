"""Recognition-bias terms for Saaras v4 (``keyterms``): at most 50, each at most 64 chars."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_TERMS = 50
MAX_TERM_CHARS = 64
DEFAULT_FILE = Path(__file__).with_name("keyterms.txt")


def load_keyterms(path: Optional[str | Path] = None) -> list[str]:
    """Read one term per line; ``#`` starts a comment; blanks and duplicates are dropped.

    ``path`` defaults to ``$KEYTERMS_FILE``, then the bundled ``keyterms.txt``.
    ``KEYTERMS_FILE=""`` disables keyterms. A missing file is not an error.
    """
    if path is None:
        env = os.environ.get("KEYTERMS_FILE")
        if env is not None and not env.strip():
            return []
        path = env or DEFAULT_FILE
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        logger.warning("Keyterms file %s not found; recognising without keyterms.", path)
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for line in lines:
        term = line.split("#", 1)[0].strip()
        if not term:
            continue
        if len(term) > MAX_TERM_CHARS:
            logger.warning("Keyterm longer than %d characters skipped.", MAX_TERM_CHARS)
            continue
        if term.casefold() in seen:
            continue
        seen.add(term.casefold())
        terms.append(term)
    if len(terms) > MAX_TERMS:
        logger.warning("%d keyterms found; Sarvam accepts %d, the rest are ignored.", len(terms), MAX_TERMS)
        terms = terms[:MAX_TERMS]
    return terms
