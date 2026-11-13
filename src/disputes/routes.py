from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response

from disputes.errors import DisputeNotFoundError, ErrorResponse
from disputes.models import Dispute, DisputeCreate, DisputeState
from disputes.repository import DisputeRepository, InMemoryDisputeRepository

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
    dispute = Dispute(
        **data.model_dump(),
        id=uuid4(),
        state=DisputeState.OPEN,
        created_at=datetime.now(UTC),
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
