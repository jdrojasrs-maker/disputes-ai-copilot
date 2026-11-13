from typing import Protocol
from uuid import UUID

from disputes.models import Dispute


class DisputeRepository(Protocol):
    def add(self, dispute: Dispute) -> None: ...

    def get(self, dispute_id: UUID) -> Dispute | None: ...


class InMemoryDisputeRepository:
    def __init__(self) -> None:
        self.disputes: dict[UUID, Dispute] = {}

    def add(self, dispute: Dispute) -> None:
        self.disputes[dispute.id] = dispute

    def get(self, dispute_id: UUID) -> Dispute | None:
        return self.disputes.get(dispute_id)
