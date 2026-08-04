"""Composition root and CLI entry point.

Wires config → store → engine → evidence → UI, keeping every layer unaware of the
others' construction. Subcommands:

    habito              launch the timer UI
    habito doctor       check config and the data repo's evidence readiness
    habito init-data    create + ``git init`` the data repo (you still add the remote)
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from habito.config.loader import load_config
from habito.config.models import Config
from habito.engine.clock import SystemClock
from habito.engine.pomodoro import PomodoroEngine
from habito.evidence.git import GitRepo
from habito.evidence.recorder import EvidenceRecorder
from habito.evidence.worker import EvidenceWorker
from habito.storage.event_store import EventStore


def _build_engine_and_store(config: Config) -> tuple[PomodoroEngine, EventStore]:
    store = EventStore(config.events_path())
    engine = PomodoroEngine(config.pomodoro, sink=store.append, clock=SystemClock())
    return engine, store


def run_gui(config: Config) -> int:
    import customtkinter as ctk

    from habito.ui.app import HabitoApp

    ctk.set_appearance_mode(config.ui.theme)
    ctk.set_default_color_theme(config.ui.color_theme)

    engine, store = _build_engine_and_store(config)
    app = HabitoApp(config, engine, store)

    repo = GitRepo(config.data_repo_path())
    if repo.is_repo():
        worker = EvidenceWorker(
            repo,
            config.evidence,
            config.paths.events_filename,
            on_status=app.on_evidence_status,
        )
        worker.start()
        store.subscribe(EvidenceRecorder(worker))
        app.attach_worker(worker)
        if repo.has_remote(config.evidence.remote):
            app.set_evidence_mode("evidence: ready", "gray60")
        else:
            app.set_evidence_mode("evidence: no remote (local commits)", "#d9863b")
    else:
        app.set_evidence_mode("evidence: off — run 'habito doctor'", "#d9863b")

    app.run()
    return 0


def doctor(config: Config) -> int:
    print("Habito configuration check")
    print(f"  project root : {config.project_root}")
    print(f"  data repo    : {config.data_repo_path()}")
    print(f"  events file  : {config.events_path()}")

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
    events = config.events_path()
    if not events.exists():
        events.touch()
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
    parser.add_argument("--config", type=Path, default=None, help="path to settings.toml")
    args = parser.parse_args(argv)

    config = load_config(config_path=args.config)

    if args.command == "doctor":
        return doctor(config)
    if args.command == "init-data":
        return init_data(config)
    return run_gui(config)


if __name__ == "__main__":
    sys.exit(main())
