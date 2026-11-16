#!/usr/bin/env python3
"""Stop this RunPod pod after a period with no backend activity (personal v1).

Off unless RUNPOD_AUTO_STOP=1. (RunPod itself sets RUNPOD_POD_ID and
RUNPOD_API_KEY in every pod, so a key being present is not an opt-in.) Polls the backend's own ``/system/activity``
(open requests and streams, running jobs, downloads), and when nothing has
happened for RUNPOD_IDLE_MINUTES (default 30, minimum 5) asks the RunPod API to
stop this pod. The key is RUNPOD_STOP_API_KEY when set (a key you created in the
RunPod console), otherwise the RUNPOD_API_KEY that RunPod provides in the pod. A stopped pod keeps its
network volume and stops billing for the GPU.

Conservative on purpose: an unreachable or unreadable backend counts as busy,
so it never stops a pod that is still starting or working. Keys are read from
the environment and never printed or logged.

RUNPOD_IDLE_IGNORE_STREAMS=1 stops counting open streams (for example an idle
app connection) as activity; running jobs and downloads still count.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

DEFAULT_IDLE_MINUTES = 30.0
MIN_IDLE_MINUTES = 5.0
DEFAULT_POLL_SECONDS = 60.0
RUNPOD_STOP_URL = "https://api.runpod.io/v2/pods/{pod_id}/action"
ACTIVITY_URL = "http://127.0.0.1:{port}/system/activity"


def log(message: str) -> None:
    print(f"idle_stop: {message}", file=sys.stderr, flush=True)


@dataclass
class IdleTracker:
    """Turns backend activity snapshots into 'seconds idle'."""

    ignore_streams: bool = False
    last_active: Optional[float] = None

    def update(self, snapshot: Optional[dict], now: float) -> float:
        if self.last_active is None:
            self.last_active = now
        if snapshot is None or self._busy(snapshot):
            self.last_active = now
        elif snapshot.get("inflight") == 0:
            # idle_seconds is the backend's own clock since its last request.
            # It reads 0 while any stream is open, so it only counts when none is.
            idle = snapshot.get("idle_seconds")
            if isinstance(idle, (int, float)) and idle >= 0:
                self.last_active = max(self.last_active, now - float(idle))
        return now - self.last_active

    def _busy(self, snapshot: dict) -> bool:
        busy = snapshot.get("busy")
        inflight = snapshot.get("inflight")
        if not isinstance(busy, list) or not isinstance(inflight, int):
            return True  # unreadable means keep the pod alive
        if busy:
            return True
        return inflight > 0 and not self.ignore_streams


def read_activity(port: int, api_key: str, opener: Callable = urllib.request.urlopen) -> Optional[dict]:
    request = urllib.request.Request(
        ACTIVITY_URL.format(port=port),
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
    )
    try:
        with opener(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def stop_pod(pod_id: str, api_key: str, opener: Callable = urllib.request.urlopen) -> bool:
    request = urllib.request.Request(
        RUNPOD_STOP_URL.format(pod_id=urllib.request.quote(pod_id, safe="")),
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=b'{"action": "stop"}',
    )
    try:
        with opener(request, timeout=30) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as error:
        log(f"RunPod refused the stop request (HTTP {error.code}).")
    except (OSError, urllib.error.URLError):
        log("could not reach the RunPod API.")
    return False


@dataclass
class Config:
    api_key: str
    pod_id: str
    idle_seconds: float
    poll_seconds: float
    port: int
    backend_key: str = ""
    ignore_streams: bool = False
    problems: list = field(default_factory=list)


def load_config(env: dict) -> Optional[Config]:
    """None when auto-stop is off (RUNPOD_AUTO_STOP is not 1). Bad values fall back."""
    if (env.get("RUNPOD_AUTO_STOP") or "").strip() != "1":
        return None
    api_key = (env.get("RUNPOD_STOP_API_KEY") or env.get("RUNPOD_API_KEY") or "").strip()
    problems = []
    try:
        minutes = float(env.get("RUNPOD_IDLE_MINUTES") or DEFAULT_IDLE_MINUTES)
    except ValueError:
        minutes = DEFAULT_IDLE_MINUTES
        problems.append("RUNPOD_IDLE_MINUTES is not a number; using 30.")
    if minutes < MIN_IDLE_MINUTES:
        problems.append(f"RUNPOD_IDLE_MINUTES below {MIN_IDLE_MINUTES:g}; using {MIN_IDLE_MINUTES:g}.")
        minutes = MIN_IDLE_MINUTES
    try:
        poll = float(env.get("RUNPOD_IDLE_POLL_SECONDS") or DEFAULT_POLL_SECONDS)
    except ValueError:
        poll = DEFAULT_POLL_SECONDS
    return Config(
        api_key=api_key,
        pod_id=(env.get("RUNPOD_POD_ID") or "").strip(),
        idle_seconds=minutes * 60,
        poll_seconds=max(5.0, poll),
        port=int(env.get("BACKEND_PORT") or 3900),
        backend_key=(env.get("OMNIVOICE_API_KEY") or "").strip(),
        ignore_streams=(env.get("RUNPOD_IDLE_IGNORE_STREAMS") or "") == "1",
        problems=problems,
    )


def run(config: Config, *, read=read_activity, stop=stop_pod,
        clock=time.monotonic, sleep=time.sleep, max_polls: Optional[int] = None) -> bool:
    """Poll until the pod is stopped. Returns True once a stop was accepted."""
    tracker = IdleTracker(ignore_streams=config.ignore_streams)
    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1
        idle = tracker.update(read(config.port, config.backend_key), clock())
        if idle >= config.idle_seconds:
            log(f"idle for {int(idle // 60)} min; stopping the pod.")
            if stop(config.pod_id, config.api_key):
                return True
            log("stop failed; will retry.")
        sleep(config.poll_seconds)
    return False


def main() -> int:
    config = load_config(dict(os.environ))
    if config is None:
        log("RUNPOD_AUTO_STOP is not 1; auto-stop is off.")
        return 0
    for problem in config.problems:
        log(problem)
    if not config.api_key:
        log("no RUNPOD_STOP_API_KEY or RUNPOD_API_KEY available; auto-stop is off.")
        return 1
    if not config.pod_id:
        log("RUNPOD_POD_ID is not set (RunPod sets it inside a pod); auto-stop is off.")
        return 1
    log(f"auto-stop on: {int(config.idle_seconds // 60)} min without activity.")
    run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
