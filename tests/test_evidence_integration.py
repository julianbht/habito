"""End-to-end evidence test: real git, a local bare 'remote', a real worker.

Proves the crux of the app — that each event is committed AND pushed to the remote,
in order, off the main thread — without needing network or GitHub. Fully hermetic
(everything lives under pytest's tmp_path and is cleaned up).
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from conftest import make_config
from habito.config.models import EvidenceConfig
from habito.engine.clock import FakeClock
from habito.engine.pomodoro import PomodoroEngine
from habito.evidence.git import GitRepo
from habito.evidence.recorder import EvidenceRecorder
from habito.evidence.worker import EvidenceWorker
from habito.storage.event_store import EventStore

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def _make_repos(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-b", "main")

    data = tmp_path / "habito-data"
    data.mkdir()
    _git(data, "init", "-b", "main")
    _git(data, "config", "user.email", "test@habito.local")
    _git(data, "config", "user.name", "Habito Test")
    (data / "events.jsonl").touch()
    _git(data, "add", ".")
    _git(data, "commit", "-m", "init")
    _git(data, "remote", "add", "origin", str(remote))
    _git(data, "push", "-u", "origin", "main")
    return remote, data


def test_each_event_is_committed_and_pushed(tmp_path):
    remote, data = _make_repos(tmp_path)

    store = EventStore(data / "events.jsonl")
    repo = GitRepo(data)
    worker = EvidenceWorker(repo, EvidenceConfig(), "events.jsonl")
    worker.start()
    store.subscribe(EvidenceRecorder(worker))

    # Generate a real 1-round session through the engine (4 events total).
    engine = PomodoroEngine(make_config(rounds=1), sink=store.append, clock=FakeClock())
    engine.start()          # SessionStarted, RoundStarted
    worker.wait_idle()      # let those two commit+push before the next pair
    engine.stop()           # RoundEnded, SessionEnded
    worker.wait_idle()
    worker.stop()

    # Everything was pushed: local HEAD == remote-tracking ref, nothing outstanding.
    assert _git(data, "rev-parse", "HEAD").strip() == _git(data, "rev-parse", "origin/main").strip()
    assert repo.unpushed_count("origin", "main") == 0

    # The remote actually received the commits (more than just the initial one).
    remote_log = _git(remote, "log", "--oneline").strip().splitlines()
    assert len(remote_log) > 1

    # Every non-initial commit is an event commit (bundling may merge back-to-back
    # events into one commit labeled by the first of the bundle).
    msgs = _git(data, "log", "--pretty=%s").strip().splitlines()
    event_msgs = [m for m in msgs if m.startswith("event: ")]
    assert event_msgs, "expected at least one event commit"
    assert all(" [live] @" in m for m in event_msgs)

    # The committed file (as pushed) holds all 4 appended events, session_ended included.
    committed = _git(data, "show", "HEAD:events.jsonl")
    assert len([ln for ln in committed.splitlines() if ln.strip()]) == 4
    assert "session_ended" in committed
    assert len(store.read_all()) == 4


def test_push_deferred_when_remote_unreachable(tmp_path):
    _remote, data = _make_repos(tmp_path)
    # Break the remote so pushes fail; commits must still succeed locally.
    _git(data, "remote", "set-url", "origin", str(tmp_path / "does-not-exist.git"))

    statuses = []
    store = EventStore(data / "events.jsonl")
    repo = GitRepo(data)
    worker = EvidenceWorker(repo, EvidenceConfig(), "events.jsonl", on_status=statuses.append)
    worker.start()
    store.subscribe(EvidenceRecorder(worker))

    engine = PomodoroEngine(make_config(rounds=1), sink=store.append, clock=FakeClock())
    engine.start()
    worker.wait_idle()
    worker.stop()

    # Commit happened locally even though every push failed.
    assert repo.unpushed_count("origin", "main") >= 1
    assert any(s.committed for s in statuses), "expected at least one local commit"
    assert all(not s.pushed for s in statuses), "no push should have succeeded"
