"""Composition root and CLI entry point.

Wires config → store → engine → evidence → UI, keeping every layer unaware of the
others' construction. Subcommands:

    habito              launch the timer UI
    habito doctor       check config and the data repo's evidence readiness
    habito init-data    create + ``git init`` the data repo (you still add the remote)

``--test-mode`` runs the UI against a throwaway log with no evidence worker, so the real
data repo is never touched. It paints the whole app red so you can't mistake it for a
real session.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-only, so the CLI paths that never open a window still don't import Qt.
    from habito.ui.app import HabitoApp

from habito.config.loader import load_config
from habito.config.models import Config
from habito.engine.clock import SystemClock
from habito.engine.pomodoro import PomodoroEngine
from habito.evidence.git import GitRepo
from habito.evidence.recorder import EvidenceRecorder
from habito.evidence.worker import EvidenceWorker
from habito.storage.event_store import EventStore


def _log_root(config: Config, test_mode: bool) -> Path:
    """The repo the log lives in — a throwaway directory when running in test mode."""
    if not test_mode:
        return config.data_repo_path()
    return Path(tempfile.gettempdir()) / "habito-test-mode"


def _build_engine_and_store(
    config: Config, test_mode: bool = False
) -> tuple[PomodoroEngine, EventStore]:
    store = EventStore(_log_root(config, test_mode), config.habit, config.time.rollover_hour)
    clock = SystemClock(config.time.zone())
    engine = PomodoroEngine(config.pomodoro, sink=store.append, clock=clock, habit=config.habit)
    return engine, store


def run_gui(config: Config, test_mode: bool = False) -> int:
    from PySide6.QtWidgets import QApplication

    from habito.ui import theme
    from habito.ui.app import HabitoApp

    existing = QApplication.instance()
    qt_app = existing if isinstance(existing, QApplication) else QApplication(sys.argv[:1])
    theme.apply(qt_app, theme.Theme.resolve(config.ui.theme, test_mode))

    if test_mode:
        # Cleared before the store reads it, so "Today" reflects this run rather than
        # last week's fiddling — the app opens on a genuinely empty log. Only ever the
        # scratch dir: test_mode=True is passed literally.
        shutil.rmtree(_log_root(config, test_mode=True), ignore_errors=True)

    engine, store = _build_engine_and_store(config, test_mode)
    app = HabitoApp(config, engine, store, test_mode=test_mode)

    if test_mode:
        # No GitRepo, no worker, no recorder: nothing can reach the data repo from here.
        print(f"TEST MODE — events go to {_log_root(config, test_mode) / config.habit}")
        print("            the data repo is not touched and settings.json is not written")
        app.set_status_mode("status: TEST MODE · not recorded", theme.ACCENT_TEST)
    else:
        _attach_evidence(app, config, store)

    app.show()
    return qt_app.exec()


def _attach_evidence(app: HabitoApp, config: Config, store: EventStore) -> None:
    from habito.ui import theme

    repo = GitRepo(config.data_repo_path())
    if not repo.is_repo():
        app.set_status_mode("status: not set up — run 'habito doctor'", theme.WARN)
        return

    worker = EvidenceWorker(
        repo,
        config.evidence,
        config.habit,  # pathspec for the habit's tree
        on_status=app.on_evidence_status,
    )
    worker.start()
    store.subscribe(EvidenceRecorder(worker))
    app.attach_worker(worker)
    if repo.has_remote(config.evidence.remote):
        app.set_status_mode("status: ready", theme.MUTED)
        worker.flush()  # push any backlog left unpushed from a prior offline run
    else:
        app.set_status_mode("status: local only (no remote)", theme.WARN)


def doctor(config: Config) -> int:
    print("Habito configuration check")
    print(f"  project root : {config.project_root}")
    print(f"  data repo    : {config.data_repo_path()}")
    print(f"  habit        : {config.habit}")
    print(f"  log tree     : {config.habit_dir_path()}")

    repo = GitRepo(config.data_repo_path())
    ok = True
    if not config.data_repo_path().exists():
        ok = False
        print("  [x] data repo directory does not exist")
        print("      fix: habito init-data   (then add a GitHub remote)")
    elif not repo.is_repo():
        ok = False
        print("  [x] data repo directory is not a git repository")
        print("      fix: habito init-data")
    else:
        print("  [ok] data repo is a git repository")
        if repo.has_remote(config.evidence.remote):
            print(f"  [ok] remote '{config.evidence.remote}' is configured")
        else:
            ok = False
            print(f"  [x] remote '{config.evidence.remote}' is missing")
            print(
                f"      fix: cd {config.data_repo_path()} && "
                f"git remote add {config.evidence.remote} <github-url> && "
                f"git push -u {config.evidence.remote} {config.evidence.branch}"
            )
    print("\nEvidence:", "READY" if ok else "NOT READY (events log locally until fixed)")
    return 0 if ok else 1


def init_data(config: Config) -> int:
    path = config.data_repo_path()
    path.mkdir(parents=True, exist_ok=True)
    repo = GitRepo(path)
    if repo.is_repo():
        print(f"Already a git repo: {path}")
        return 0

    subprocess.run(["git", "init", "-b", config.evidence.branch], cwd=path, check=True)
    gitignore = path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("# habito evidence repo — the events log IS tracked.\n")
    habit_dir = config.habit_dir_path()
    habit_dir.mkdir(parents=True, exist_ok=True)
    # Git tracks files, not directories, so the log dir needs a placeholder to survive
    # the initial commit — otherwise there's nothing to commit and `git init` fails.
    keep = habit_dir / ".gitkeep"
    if not keep.exists():
        keep.touch()
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init habito evidence repo"], cwd=path, check=True)
    print(f"Initialised data repo at {path}")
    print("Next: create a GitHub repo, then:")
    print(
        f"  cd {path} && git remote add {config.evidence.remote} <github-url> "
        f"&& git push -u {config.evidence.remote} {config.evidence.branch}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="habito", description="Pomodoro habit tracker")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "doctor", "init-data"],
        help="run the UI (default), check setup, or initialise the data repo",
    )
    parser.add_argument("--config", type=Path, default=None, help="path to settings.json")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="run the UI in red test mode: a throwaway log, nothing written to the data repo",
    )
    args = parser.parse_args(argv)

    config = load_config(config_path=args.config)

    if args.command == "doctor":
        return doctor(config)
    if args.command == "init-data":
        return init_data(config)
    return run_gui(config, test_mode=args.test_mode)


if __name__ == "__main__":
    sys.exit(main())
