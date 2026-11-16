"""Auto-stop logic with a mocked RunPod API and a fake clock (no network)."""
from __future__ import annotations

import io
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import idle_stop  # noqa: E402

def quiet(since):
    """Backend snapshot when nothing has happened since time ``since``."""
    return lambda now: {"inflight": 0, "busy": [], "idle_seconds": max(0.0, now - since)}



def test_off_unless_explicitly_enabled():
    # RunPod puts RUNPOD_API_KEY and RUNPOD_POD_ID in every pod; that is not an opt-in.
    assert idle_stop.load_config({}) is None
    assert idle_stop.load_config({"RUNPOD_API_KEY": "k", "RUNPOD_POD_ID": "p"}) is None
    assert idle_stop.load_config({"RUNPOD_AUTO_STOP": "yes", "RUNPOD_API_KEY": "k"}) is None


def test_key_prefers_the_user_created_one():
    on = {"RUNPOD_AUTO_STOP": "1"}
    assert idle_stop.load_config({**on, "RUNPOD_API_KEY": "pod"}).api_key == "pod"
    both = {**on, "RUNPOD_API_KEY": "pod", "RUNPOD_STOP_API_KEY": "mine"}
    assert idle_stop.load_config(both).api_key == "mine"
    assert idle_stop.load_config(on).api_key == ""


def test_config_defaults_clamps_and_bad_values():
    cfg = idle_stop.load_config({"RUNPOD_AUTO_STOP": "1", "RUNPOD_API_KEY": "k", "RUNPOD_POD_ID": "abc"})
    assert cfg.idle_seconds == 30 * 60 and cfg.pod_id == "abc" and cfg.port == 3900
    low = idle_stop.load_config({"RUNPOD_AUTO_STOP": "1", "RUNPOD_API_KEY": "k", "RUNPOD_IDLE_MINUTES": "1"})
    assert low.idle_seconds == 5 * 60 and low.problems
    junk = idle_stop.load_config({"RUNPOD_AUTO_STOP": "1", "RUNPOD_API_KEY": "k", "RUNPOD_IDLE_MINUTES": "soon"})
    assert junk.idle_seconds == 30 * 60 and junk.problems


def test_tracker_counts_busy_streams_and_unreadable_as_activity():
    t = idle_stop.IdleTracker()
    assert t.update({"inflight": 0, "busy": ["dub"], "idle_seconds": 900}, 1000) == 0
    assert t.update({"inflight": 2, "busy": [], "idle_seconds": 0}, 1100) == 0
    assert t.update(None, 1200) == 0
    assert t.update({"inflight": "x", "busy": [], "idle_seconds": 0}, 1300) == 0
    assert t.update({"inflight": 0, "busy": [], "idle_seconds": 100}, 1400) == 100


def test_tracker_can_ignore_open_streams_but_not_jobs():
    t = idle_stop.IdleTracker(ignore_streams=True)
    t.update({"inflight": 0, "busy": [], "idle_seconds": 0}, 0)
    assert t.update({"inflight": 3, "busy": [], "idle_seconds": 0}, 600) == 600
    assert t.update({"inflight": 3, "busy": ["dub"], "idle_seconds": 0}, 700) == 0


def test_tracker_uses_the_backends_own_idle_clock():
    t = idle_stop.IdleTracker()
    assert t.update({"inflight": 0, "busy": [], "idle_seconds": 500}, 100) == 0
    assert t.update({"inflight": 0, "busy": [], "idle_seconds": 560}, 160) == 60


def _loop(feed, cfg, stop_ok=True):
    """``feed(now)`` returns the backend snapshot at that moment."""
    clock = {"now": 0.0}
    stops = []

    def stop(pod, key):
        stops.append((pod, key))
        return stop_ok

    def sleep(seconds):
        clock["now"] += seconds

    done = idle_stop.run(cfg, read=lambda port, key: feed(clock["now"]), stop=stop,
                         clock=lambda: clock["now"], sleep=sleep, max_polls=200)
    return done, stops, clock["now"]


def _cfg(**kw):
    base = {"RUNPOD_AUTO_STOP": "1", "RUNPOD_API_KEY": "key", "RUNPOD_POD_ID": "pod1", "RUNPOD_IDLE_MINUTES": "30"}
    return idle_stop.load_config({**base, **kw})


def test_stops_once_after_the_idle_window():
    done, stops, at = _loop(quiet(0), _cfg())
    assert done and stops == [("pod1", "key")]
    assert 30 * 60 <= at <= 31 * 60


def test_activity_delays_the_stop():
    # a job runs for the first 20 minutes, then the backend goes quiet
    def feed(now):
        if now < 20 * 60:
            return {"inflight": 0, "busy": ["dub"], "idle_seconds": 0}
        return quiet(20 * 60)(now)

    done, stops, at = _loop(feed, _cfg())
    assert done and 50 * 60 <= at <= 51 * 60


def test_open_streams_keep_the_pod_unless_ignored():
    streams = lambda now: {"inflight": 1, "busy": [], "idle_seconds": 0}  # noqa: E731
    done, stops, _ = _loop(streams, _cfg())
    assert not done and stops == []
    done, stops, at = _loop(streams, _cfg(RUNPOD_IDLE_IGNORE_STREAMS="1"))
    assert done and 30 * 60 <= at <= 31 * 60


def test_unreadable_backend_never_stops_the_pod():
    done, stops, _ = _loop(lambda now: None, _cfg())
    assert not done and stops == []


def test_failed_stop_retries_next_poll():
    done, stops, _ = _loop(quiet(0), _cfg(), stop_ok=False)
    assert not done and len(stops) > 1


def test_stop_pod_posts_to_runpod_with_bearer_and_no_key_in_logs(capsys):
    seen = {}

    class Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(request, timeout):
        seen.update(url=request.full_url, method=request.get_method(),
                    auth=request.get_header("Authorization"), body=request.data)
        return Resp(b"{}")

    assert idle_stop.stop_pod("pod/1", "secret-key", opener)
    assert seen == {"url": "https://api.runpod.io/v2/pods/pod%2F1/action", "method": "POST",
                    "auth": "Bearer secret-key", "body": b'{"action": "stop"}'}

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)

    assert not idle_stop.stop_pod("pod1", "secret-key", refuse)
    assert "secret-key" not in capsys.readouterr().err


def test_read_activity_sends_bearer_and_tolerates_failures():
    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = {}

    def opener(request, timeout):
        seen["auth"] = request.get_header("Authorization")
        seen["url"] = request.full_url
        return Resp(b'{"inflight": 0, "busy": [], "idle_seconds": 1.5}')

    assert idle_stop.read_activity(3900, "abc", opener)["idle_seconds"] == 1.5
    assert seen == {"auth": "Bearer abc", "url": "http://127.0.0.1:3900/system/activity"}
    assert idle_stop.read_activity(3900, "abc", lambda r, timeout: Resp(b"not json")) is None

    def down(request, timeout):
        raise OSError("refused")

    assert idle_stop.read_activity(3900, "abc", down) is None
