"""Background worker that commits+pushes each event, off the UI thread.

A single-consumer queue preserves event order. Network/git latency never blocks the UI.
On push failure the local commit still stands (the JSONL line is already fsynced), the
worker reports an ``unpushed`` status, and the next event's push attempt drains the
backlog. A non-fast-forward rejection triggers one ``pull --rebase`` retry.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass

from habito.config.models import EvidenceConfig
from habito.domain.events import Event
from habito.evidence.git import GitError, GitRepo

log = logging.getLogger("habito.evidence")

_SENTINEL = object()


@dataclass(frozen=True)
class EvidenceStatus:
    committed: bool
    pushed: bool
    unpushed_count: int
    error: str | None = None


StatusCallback = Callable[[EvidenceStatus], None]


class EvidenceWorker:
    def __init__(
        self,
        repo: GitRepo,
        config: EvidenceConfig,
        events_filename: str,
        on_status: StatusCallback | None = None,
    ) -> None:
        self._repo = repo
        self._config = config
        self._filename = events_filename
        self._on_status = on_status
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="evidence-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def submit(self, event: Event) -> None:
        """Observer entry point — enqueue an event for commit+push."""
        self._queue.put(event)

    def stop(self, timeout: float | None = 10.0) -> None:
        self._queue.put(_SENTINEL)
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # --- worker loop -----------------------------------------------------
    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SENTINEL:
                    return
                self._process(item)
            finally:
                self._queue.task_done()

    def _process(self, event: Event) -> None:
        cfg = self._config
        message = cfg.commit_message_template.format(
            type=event.type,
            origin=event.origin.value,
            iso=event.timestamp.isoformat(),
        )
        committed = pushed = False
        error: str | None = None
        try:
            self._repo.add(self._filename)
            if cfg.auto_commit:
                self._repo.commit(self._filename, message)
                committed = True
            if cfg.auto_commit and cfg.auto_push:
                pushed = self._try_push()
        except GitError as exc:
            error = str(exc)
            log.warning("evidence step failed: %s", exc)

        unpushed = self._repo.unpushed_count(cfg.remote, cfg.branch)
        self._report(EvidenceStatus(committed, pushed, unpushed, error))

    def _try_push(self) -> bool:
        cfg = self._config
        try:
            self._repo.push(cfg.remote, cfg.branch)
            return True
        except GitError as first:
            # Likely offline, or a non-fast-forward. Try one rebase+push, else defer.
            try:
                self._repo.pull_rebase(cfg.remote, cfg.branch)
                self._repo.push(cfg.remote, cfg.branch)
                return True
            except GitError as second:
                log.warning("push deferred (will retry on next event): %s / %s", first, second)
                return False

    def _report(self, status: EvidenceStatus) -> None:
        if self._on_status is not None:
            try:
                self._on_status(status)
            except Exception:  # noqa: BLE001 - never let a UI callback kill the worker
                log.exception("status callback raised")
