"""Optional copy of every exported project bundle (personal v1, change 5).

With ``OMNIVOICE_PROJECT_BUNDLE_DIR`` set (RunPod: ``/workspace/projects``), a
project bundle that is exported is also kept there, so a video can be reopened
after the pod's temporary export files are gone. Failures are logged and never
affect the export itself.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("omnivoice.bundle_archive")

ENV_DIR = "OMNIVOICE_PROJECT_BUNDLE_DIR"
_UNSAFE = re.compile(r"[^\w.\- ]+", re.UNICODE)


def _stem(title: str) -> str:
    cleaned = _UNSAFE.sub("_", (title or "").strip()).strip(" ._")
    return (cleaned or "project")[:80]


def archive_copy(source: Path, title: str, *, now: Optional[float] = None) -> Optional[Path]:
    """Copy ``source`` into the archive folder; returns the copy, or None when off/failed."""
    directory = (os.environ.get(ENV_DIR) or "").strip()
    if not directory:
        return None
    try:
        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now if now is not None else time.time()))
        target = target_dir / f"{_stem(title)}-{stamp}.vsproject"
        n = 1
        while target.exists():
            n += 1
            target = target_dir / f"{_stem(title)}-{stamp}-{n}.vsproject"
        shutil.copyfile(source, target)
        return target
    except Exception:
        logger.warning("could not archive the project bundle", exc_info=True)
        return None
