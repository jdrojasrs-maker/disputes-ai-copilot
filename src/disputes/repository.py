import threading
from datetime import datetime
from typing import Protocol
from uuid import UUID

from disputes.models import Dispute, DisputeState, StateChange


class DisputeRepository(Protocol):
    def add(self, dispute: Dispute) -> None: ...

    def get(self, dispute_id: UUID) -> Dispute | None: ...

    def transition(
        self,
        dispute_id: UUID,
        from_state: DisputeState,
        to_state: DisputeState,
        note: str | None,
        at: datetime,
    ) -> Dispute | None: ...


class InMemoryDisputeRepository:
    def __init__(self) -> None:
        self.disputes: dict[UUID, Dispute] = {}
        # Routes run in a thread pool: without this, two threads could both read the same state
        # in `transition` and both write. `get` needs no lock; it reads one whole object.
        self._lock = threading.Lock()

    def add(self, dispute: Dispute) -> None:
        with self._lock:
            self.disputes[dispute.id] = dispute

    def get(self, dispute_id: UUID) -> Dispute | None:
        return self.disputes.get(dispute_id)

    def transition(
        self,
        dispute_id: UUID,
        from_state: DisputeState,
        to_state: DisputeState,
        note: str | None,
        at: datetime,
    ) -> Dispute | None:
        with self._lock:
            current = self.disputes.get(dispute_id)
            if current is None or current.state != from_state:
                return None
            # The route reads the clock before this runs, so `at` can be older than the stored
            # time; max keeps time from going backwards.
            effective_at = max(at, current.updated_at)
            change = StateChange(
                from_state=from_state, to_state=to_state, note=note, changed_at=effective_at
            )
            updated = current.model_copy(
                update={
                    "state": to_state,
                    "updated_at": effective_at,
                    "history": [*current.history, change],
                }
            )
            self.disputes[dispute_id] = updated
            return updated
