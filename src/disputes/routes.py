from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response

from disputes.errors import DisputeNotFoundError, ErrorResponse, InvalidTransitionError
from disputes.models import Dispute, DisputeCreate, DisputeState, TransitionRequest
from disputes.repository import DisputeRepository, InMemoryDisputeRepository
from disputes.transitions import is_allowed

router = APIRouter()

_repository = InMemoryDisputeRepository()


def get_repository() -> DisputeRepository:
    return _repository


RepositoryDep = Annotated[DisputeRepository, Depends(get_repository)]


@router.post(
    "/disputes",
    status_code=201,
    responses={
        201: {
            "description": "Dispute created in state open",
            "headers": {
                "Location": {
                    "description": "Path of the new dispute, /disputes/{id}",
                    "schema": {"type": "string"},
                }
            },
        },
        422: {"model": ErrorResponse, "description": "Invalid input; nothing was created"},
    },
)
def create_dispute(
    data: DisputeCreate, response: Response, repository: RepositoryDep
) -> Dispute:
    now = datetime.now(UTC)
    dispute = Dispute(
        **data.model_dump(),
        id=uuid4(),
        state=DisputeState.OPEN,
        created_at=now,
        updated_at=now,
        history=[],
    )
    repository.add(dispute)
    response.headers["Location"] = f"/disputes/{dispute.id}"
    return dispute


@router.get(
    "/disputes/{dispute_id}",
    responses={
        404: {"model": ErrorResponse, "description": "No dispute with this id"},
        422: {"model": ErrorResponse, "description": "The id is not a valid UUID"},
    },
)
def get_dispute(dispute_id: UUID, repository: RepositoryDep) -> Dispute:
    dispute = repository.get(dispute_id)
    if dispute is None:
        raise DisputeNotFoundError()
    return dispute


@router.post(
    "/disputes/{dispute_id}/transitions",
    responses={
        404: {"model": ErrorResponse, "description": "No dispute with this id"},
        409: {
            "model": ErrorResponse,
            "description": "The move is not allowed from the dispute's state, or the state "
            "changed while the request was being handled; the dispute is unchanged",
        },
        422: {"model": ErrorResponse, "description": "Invalid id or body; nothing changed"},
    },
)
def transition_dispute(
    dispute_id: UUID, body: TransitionRequest, repository: RepositoryDep
) -> Dispute:
    current = repository.get(dispute_id)
    if current is None:
        raise DisputeNotFoundError()
    if not is_allowed(current.state, body.to_state):
        raise InvalidTransitionError(current.state, body.to_state)
    updated = repository.transition(
        dispute_id, current.state, body.to_state, body.note, datetime.now(UTC)
    )
    if updated is None:
        # The state changed after the read above. Say so instead of "not allowed": the move
        # may be allowed from the new state.
        latest = repository.get(dispute_id)
        if latest is None:
            raise DisputeNotFoundError()
        raise InvalidTransitionError(latest.state, body.to_state, state_changed=True)
    return updated
