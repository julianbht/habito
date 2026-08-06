"""Background worker that commits+pushes each event, off the UI thread.

A single-consumer queue preserves event order. Network/git latency never blocks the UI.
On push failure the local commit still stands (the JSONL line is already fsynced) and the
worker reports an ``unpushed`` status. The backlog is flushed by a later push attempt:
when the next event fires, on startup (:meth:`flush`), and on graceful shutdown. A
non-fast-forward rejection triggers one ``pull --rebase`` retry.
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
_FLUSH = object()


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
        habit_dir: str,
        on_status: StatusCallback | None = None,
    ) -> None:
        self._repo = repo
        self._config = config
        # A directory, not a file — git add/commit/diff all take a pathspec, so staging
        # the whole habit tree picks up whichever day file the event just landed in.
        self._pathspec = habit_dir
        self._on_status = on_status
        self._queue: queue.Queue[object] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="evidence-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def submit(self, event: Event) -> None:
        """Observer entry point — enqueue an event for commit+push."""
        self._queue.put(event)

    def flush(self) -> None:
        """Request a push of any unpushed backlog (e.g. on startup / reconnect)."""
        self._queue.put(_FLUSH)

    def wait_idle(self) -> None:
        """Block until every submitted event has been processed (mainly for tests)."""
        self._queue.join()

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
                    self._flush()  # best-effort final push on graceful close
                    return
                if item is _FLUSH:
                    self._flush()
                else:
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
            self._repo.add(self._pathspec)
            # A prior commit may already contain this line (events that fired close
            # together bundle into one commit). That's fine — skip the empty commit,
            # but still push so any backlog is flushed.
            if cfg.auto_commit and self._repo.has_staged_changes(self._pathspec):
                self._repo.commit(self._pathspec, message)
                committed = True
            if cfg.auto_push:
                pushed = self._try_push()
        except GitError as exc:
            error = str(exc)
            log.warning("evidence step failed: %s", exc)

        unpushed = self._repo.unpushed_count(cfg.remote, cfg.branch)
        self._report(EvidenceStatus(committed, pushed, unpushed, error))

    def _flush(self) -> None:
        """Push any backlog. No-op (and silent) when already in sync or push disabled."""
        cfg = self._config
        if not cfg.auto_push:
            return
        if self._repo.unpushed_count(cfg.remote, cfg.branch) == 0:
            return  # nothing pending — don't overwrite the current status label
        pushed = self._try_push()
        after = self._repo.unpushed_count(cfg.remote, cfg.branch)
        self._report(EvidenceStatus(committed=False, pushed=pushed, unpushed_count=after))

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
                log.warning("push deferred (retries on next event/flush): %s / %s", first, second)
                return False

    def _report(self, status: EvidenceStatus) -> None:
        if self._on_status is not None:
            try:
                self._on_status(status)
            except Exception:  # noqa: BLE001 - never let a UI callback kill the worker
                log.exception("status callback raised")
