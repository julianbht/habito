"""Composition root and CLI entry point.

Wires config → store → engine → evidence → UI, keeping every layer unaware of the
others' construction. Subcommands:

    habito              launch the timer UI
    habito doctor       check config and the data repo's evidence readiness
    habito init-data    create + ``git init`` the data repo (you still add the remote)

``--test-mode`` runs the UI against a throwaway log with no evidence worker, so the real
data repo is never touched. It paints the whole app red so you can't mistake it for a
real session, and — unless ``--config`` says otherwise — loads settings from a gitignored
``config/test-settings.json`` instead of ``config/settings.json``, so poking at the UI
(e.g. a 1-minute, 1-round Pomodoro) never needs the real settings touched or reverted.
Pass ``--config config/settings.json`` explicitly to use the real settings while in test
mode anyway.
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-only, so the CLI paths that never open a window still don't import Qt.
    from habito.ui.app import HabitoApp

from habito.config.loader import find_project_root, load_config
from habito.config.models import Config
from habito.engine.clock import SystemClock
from habito.engine.pomodoro import PomodoroEngine
from habito.evidence.git import GitRepo
from habito.evidence.recorder import EvidenceRecorder
from habito.evidence.worker import EvidenceWorker
from habito.storage.event_store import EventStore

# habito is a gui-script (no attached console), so a console child like git.exe would
# otherwise flash its own new console window on every invocation.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _configure_logging(project_root: Path) -> None:
    """Log to a file always, plus the console when one exists.

    ``habito`` is a gui-script (see pyproject.toml) so it launches with no console
    attached and outlives the terminal it was started from — but that also means
    ``sys.stderr`` may be ``None``, and even when it isn't, there's nowhere for anyone to
    read it. The file is what makes evidence-worker failures (push rejected, offline,
    etc.) diagnosable after the fact.
    """
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            log_dir / "habito.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


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


def _build_wakeup_store(config: Config, test_mode: bool = False) -> EventStore | None:
    """A second, unrelated habit's store — only when `extras.enabled` (see CLAUDE.md §
    Extras). Reuses the same habit-agnostic `EventStore`, just pointed at a different habit
    name under the same root."""
    if not config.extras.enabled:
        return None
    root = _log_root(config, test_mode)
    return EventStore(root, config.extras.wakeup.habit, config.time.rollover_hour)


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
    wakeup_store = _build_wakeup_store(config, test_mode)
    app = HabitoApp(config, engine, store, wakeup_store, test_mode=test_mode)

    if test_mode:
        # No GitRepo, no worker, no recorder: nothing can reach the data repo from here.
        print(f"TEST MODE — events go to {_log_root(config, test_mode) / config.habit}")
        print("            the data repo is not touched and settings.json is not written")
        app.set_status_mode("status: TEST MODE · not recorded", theme.ACCENT_TEST)
    else:
        _attach_evidence(app, config, store, wakeup_store)

    app.show()
    app.offer_resume()
    return qt_app.exec()


def _attach_evidence(
    app: HabitoApp, config: Config, store: EventStore, wakeup_store: EventStore | None = None
) -> None:
    from habito.ui import theme

    repo = GitRepo(config.data_repo_path())
    if not repo.is_repo():
        app.set_status_mode("status: not set up — run 'habito doctor'", theme.WARN)
        return

    # "." rather than one habit's directory: the data repo holds nothing but habit
    # trees and a .gitignore, so staging/committing the whole thing is safe and is what
    # lets one worker (one thread, one git-command queue against this repo) serve every
    # habit's store rather than needing one worker per habit.
    worker = EvidenceWorker(repo, config.evidence, ".", on_status=app.on_evidence_status)
    worker.start()
    recorder = EvidenceRecorder(worker)
    store.subscribe(recorder)
    if wakeup_store is not None:
        wakeup_store.subscribe(recorder)
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

    subprocess.run(
        ["git", "init", "-b", config.evidence.branch],
        cwd=path,
        check=True,
        creationflags=_NO_WINDOW,
    )
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
    subprocess.run(["git", "add", "."], cwd=path, check=True, creationflags=_NO_WINDOW)
    subprocess.run(
        ["git", "commit", "-m", "init habito evidence repo"],
        cwd=path,
        check=True,
        creationflags=_NO_WINDOW,
    )
    print(f"Initialised data repo at {path}")
    print("Next: create a GitHub repo, then:")
    print(
        f"  cd {path} && git remote add {config.evidence.remote} <github-url> "
        f"&& git push -u {config.evidence.remote} {config.evidence.branch}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="habito", description="Pomodoro habit tracker")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "doctor", "init-data"],
        help="run the UI (default), check setup, or initialise the data repo",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="path to settings.json (default: config/test-settings.json in --test-mode, "
        "else config/settings.json)",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="run the UI in red test mode: a throwaway log, nothing written to the data repo",
    )
    args = parser.parse_args(argv)

    project_root = find_project_root()
    config_path = args.config
    if config_path is None and args.test_mode:
        # A separate file, not the real config, so poking at the UI never needs settings
        # touched or reverted afterwards — pass --config explicitly to use the real one
        # while in test mode anyway. Falls back to defaults like any other config path if
        # it doesn't exist yet (see load_config).
        config_path = project_root / "config" / "test-settings.json"

    config = load_config(project_root=project_root, config_path=config_path)
    _configure_logging(config.project_root)

    if args.command == "doctor":
        return doctor(config)
    if args.command == "init-data":
        return init_data(config)
    return run_gui(config, test_mode=args.test_mode)


if __name__ == "__main__":
    sys.exit(main())
