"""Observer that bridges the event store to the evidence worker.

Kept as its own tiny type (rather than passing ``worker.submit`` directly) so the wiring
reads intentionally and the coupling between storage and git stays explicit and one-way.
"""

from __future__ import annotations

from habito.domain.events import Event
from habito.evidence.worker import EvidenceWorker


class EvidenceRecorder:
    def __init__(self, worker: EvidenceWorker) -> None:
        self._worker = worker

    def __call__(self, event: Event) -> None:
        self._worker.submit(event)
