"""End-to-end evidence test: real git, a local bare 'remote', a real worker.

Proves the crux of the app — that each event is committed AND pushed to the remote,
in order, off the main thread — without needing network or GitHub. Fully hermetic
(everything lives under pytest's tmp_path and is cleaned up).
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime

import pytest

from conftest import make_config
from habito import app as app_module
from habito.actions.wakeup import build_wakeup_event
from habito.config.models import Config, EvidenceConfig, PathsConfig
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


@pytest.fixture(scope="session")
def _repo_template(tmp_path_factory):
    """A pristine data repo and its bare 'remote', built once for the whole session.

    Standing this pair up costs eight git subprocesses (~400ms on Windows, where spawning
    dominates), and it is scaffolding rather than anything under test — every assertion in
    this module is about what the *worker* does afterwards. So it is built once and each
    test gets a copy, which is the same repo without paying for `git init` four times.
    """
    root = tmp_path_factory.mktemp("evidence-template")
    remote = root / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-b", "main")

    data = root / "habito-data"
    data.mkdir()
    _git(data, "init", "-b", "main")
    _git(data, "config", "user.email", "test@habito.local")
    _git(data, "config", "user.name", "Habito Test")
    (data / "study").mkdir()
    (data / "study" / ".gitkeep").touch()
    _git(data, "add", ".")
    _git(data, "commit", "-m", "init")
    _git(data, "remote", "add", "origin", str(remote))
    _git(data, "push", "-u", "origin", "main")
    return root


@pytest.fixture
def repos(_repo_template, tmp_path):
    """This test's own copy of that pair, with origin re-pointed at the copied remote.

    The URL is rewritten through git rather than by editing `.git/config`, so nothing here
    depends on how git happens to serialise a Windows path into that file.
    """
    shutil.copytree(_repo_template, tmp_path, dirs_exist_ok=True)
    remote, data = tmp_path / "remote.git", tmp_path / "habito-data"
    _git(data, "remote", "set-url", "origin", str(remote))
    return remote, data


def test_each_event_is_committed_and_pushed(repos):
    remote, data = repos

    store = EventStore(data, "study")
    repo = GitRepo(data)
    worker = EvidenceWorker(repo, EvidenceConfig(), "study")
    worker.start()
    store.subscribe(EvidenceRecorder(worker))

    # Generate a real 1-round session through the engine (4 events total).
    engine = PomodoroEngine(
        make_config(rounds=1), sink=store.append, clock=FakeClock(), habit="study"
    )
    engine.start()  # SessionStarted, RoundStarted
    worker.wait_idle()  # let those two commit+push before the next pair
    engine.stop()  # RoundEnded, SessionEnded
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
    # The path is asked of the store rather than hardcoded — it's the day partition that
    # decides it, and this session is short enough to land in a single day file.
    day_file = store.files()[0].relative_to(data).as_posix()
    committed = _git(data, "show", f"HEAD:{day_file}")
    assert len([ln for ln in committed.splitlines() if ln.strip()]) == 4
    assert "session_ended" in committed
    assert len(store.read_all()) == 4


def test_one_worker_commits_two_habits_stores_together(repos):
    """The "." pathspec (rather than one habit's subtree) is what lets a single worker
    serve every habit's store — e.g. the study habit and the wake-up "sleep" habit sharing
    one data repo — without racing git commands against each other."""
    remote, data = repos

    study = EventStore(data, "study")
    wakeup = EventStore(data, "sleep")
    repo = GitRepo(data)
    worker = EvidenceWorker(repo, EvidenceConfig(), ".")
    worker.start()
    recorder = EvidenceRecorder(worker)
    study.subscribe(recorder)
    wakeup.subscribe(recorder)

    engine = PomodoroEngine(
        make_config(rounds=1), sink=study.append, clock=FakeClock(), habit="study"
    )
    engine.start()
    engine.stop()
    worker.wait_idle()

    wake_event = build_wakeup_event(
        datetime(2026, 8, 17, 7, 0, tzinfo=UTC),
        datetime(2026, 8, 16, 23, 0, tzinfo=UTC),
        habit="sleep",
    )
    wakeup.append(wake_event)
    worker.wait_idle()
    worker.stop()

    assert repo.unpushed_count("origin", "main") == 0
    study_file = study.files()[0].relative_to(data).as_posix()
    wakeup_file = wakeup.files()[0].relative_to(data).as_posix()
    assert "session_ended" in _git(data, "show", f"HEAD:{study_file}")
    assert "wake_up_logged" in _git(data, "show", f"HEAD:{wakeup_file}")


def test_push_deferred_when_remote_unreachable(repos, tmp_path):
    _remote, data = repos
    # Break the remote so pushes fail; commits must still succeed locally.
    _git(data, "remote", "set-url", "origin", str(tmp_path / "does-not-exist.git"))

    statuses = []
    store = EventStore(data, "study")
    repo = GitRepo(data)
    worker = EvidenceWorker(repo, EvidenceConfig(), "study", on_status=statuses.append)
    worker.start()
    store.subscribe(EvidenceRecorder(worker))

    engine = PomodoroEngine(
        make_config(rounds=1), sink=store.append, clock=FakeClock(), habit="study"
    )
    engine.start()
    worker.wait_idle()
    worker.stop()

    # Commit happened locally even though every push failed.
    assert repo.unpushed_count("origin", "main") >= 1
    assert any(s.committed for s in statuses), "expected at least one local commit"
    assert all(not s.pushed for s in statuses), "no push should have succeeded"


def _accumulate_offline_backlog(repos, tmp_path):
    """Study while 'offline', and return (remote, data, store, repo, worker)."""
    remote, data = repos
    store = EventStore(data, "study")
    repo = GitRepo(data)
    worker = EvidenceWorker(repo, EvidenceConfig(), "study")
    worker.start()
    store.subscribe(EvidenceRecorder(worker))

    _git(data, "remote", "set-url", "origin", str(tmp_path / "offline.git"))
    engine = PomodoroEngine(
        make_config(rounds=1), sink=store.append, clock=FakeClock(), habit="study"
    )
    engine.start()
    engine.stop()
    worker.wait_idle()
    assert repo.unpushed_count("origin", "main") >= 1  # backlog accumulated offline
    return remote, data, store, repo, worker


def test_startup_flush_pushes_backlog_after_reconnect(repos, tmp_path):
    remote, data, _store, repo, worker = _accumulate_offline_backlog(repos, tmp_path)

    # Reconnect, then the startup flush() drains the backlog.
    _git(data, "remote", "set-url", "origin", str(remote))
    worker.flush()
    worker.wait_idle()
    worker.stop()

    assert repo.unpushed_count("origin", "main") == 0
    local_head = _git(data, "rev-parse", "HEAD").strip()
    assert local_head == _git(data, "rev-parse", "origin/main").strip()
    assert len(_git(remote, "log", "--oneline").strip().splitlines()) > 1


def test_close_flush_pushes_backlog_after_reconnect(repos, tmp_path):
    remote, data, _store, repo, worker = _accumulate_offline_backlog(repos, tmp_path)

    # Reconnect and close — the shutdown flush should push the backlog.
    _git(data, "remote", "set-url", "origin", str(remote))
    worker.stop()

    assert repo.unpushed_count("origin", "main") == 0


def _second_machine(remote, tmp_path):
    """Another clone of the same remote: the other PC."""
    other = tmp_path / "other-pc"
    _git(tmp_path, "clone", "-q", str(remote), str(other))
    _git(other, "config", "user.email", "test@habito.local")
    _git(other, "config", "user.name", "Habito Test")
    return other


def _log_one_session(data):
    store = EventStore(data, "study")
    engine = PomodoroEngine(
        make_config(rounds=1), sink=store.append, clock=FakeClock(), habit="study"
    )
    engine.start()
    engine.stop()
    return store


def _commit_and_push(data):
    _git(data, "add", ".")
    _git(data, "commit", "-q", "-m", "other pc")
    _git(data, "push", "-q", "origin", "main")


def test_rejected_push_merges_a_day_file_both_machines_wrote(repos, tmp_path):
    """One machine pushes a day, the other then logs the same day without pulling first.
    The union merge keeps both sides' lines, so the worker's rebase-and-retry succeeds."""
    remote, data = repos
    (data / ".gitattributes").write_text("*.jsonl merge=union\n")
    _commit_and_push(data)
    other = _second_machine(remote, tmp_path)
    _log_one_session(other)
    _commit_and_push(other)

    store = _log_one_session(data)
    repo = GitRepo(data)
    worker = EvidenceWorker(repo, EvidenceConfig(), ".")
    worker.start()
    worker.submit(store.read_all()[-1])
    worker.wait_idle()
    worker.stop()

    assert repo.unpushed_count("origin", "main") == 0
    assert len(store.read_all()) == 8
    assert _git(data, "status", "--porcelain") == ""


def test_failed_rebase_is_aborted_and_the_local_commit_kept(repos, tmp_path):
    """Without the union merge the same case conflicts. The repo must not stay stopped
    halfway through the rebase, or every later commit and push would fail too."""
    remote, data = repos
    other = _second_machine(remote, tmp_path)
    _log_one_session(other)
    _commit_and_push(other)

    store = _log_one_session(data)
    repo = GitRepo(data)
    worker = EvidenceWorker(repo, EvidenceConfig(), ".")
    worker.start()
    worker.submit(store.read_all()[-1])
    worker.wait_idle()
    worker.stop()

    assert not (data / ".git" / "rebase-merge").exists()
    assert repo.unpushed_count("origin", "main") == 1
    assert len(store.read_all()) == 4


def test_startup_pull_brings_in_the_other_machines_events(repos, tmp_path):
    remote, data = repos
    other = _second_machine(remote, tmp_path)
    _log_one_session(other)
    _commit_and_push(other)

    config = Config(project_root=tmp_path, paths=PathsConfig(data_repo=str(data)))
    assert app_module._pull_on_startup(config)
    assert len(EventStore(data, "study").read_all()) == 4


def test_startup_pull_reports_an_unreachable_remote(repos, tmp_path):
    _remote, data = repos
    _git(data, "remote", "set-url", "origin", str(tmp_path / "offline.git"))
    config = Config(project_root=tmp_path, paths=PathsConfig(data_repo=str(data)))
    assert not app_module._pull_on_startup(config)


def test_init_data_gives_a_new_repo_the_union_merge(tmp_path, monkeypatch):
    for var in ("GIT_AUTHOR", "GIT_COMMITTER"):
        monkeypatch.setenv(f"{var}_NAME", "Habito Test")
        monkeypatch.setenv(f"{var}_EMAIL", "test@habito.local")
    data = tmp_path / "habito-data"
    config = Config(project_root=tmp_path, paths=PathsConfig(data_repo=str(data)))

    app_module.init_data(config)

    assert GitRepo(data).merge_attribute("x.jsonl") == "union"


def test_init_data_adds_the_union_merge_to_an_existing_repo(repos, tmp_path):
    _remote, data = repos
    config = Config(project_root=tmp_path, paths=PathsConfig(data_repo=str(data)))

    app_module.init_data(config)
    app_module.init_data(config)  # a second run changes nothing

    assert GitRepo(data).merge_attribute("x.jsonl") == "union"
    assert _git(data, "status", "--porcelain") == ""
    assert _git(data, "log", "--oneline").count("merge day files by union") == 1
