from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class Reason(StrEnum):
    DUPLICATE_CHARGE = "duplicate_charge"
    UNRECOGNIZED_CHARGE = "unrecognized_charge"
    PRODUCT_NOT_RECEIVED = "product_not_received"
    INCORRECT_AMOUNT = "incorrect_amount"
    DEVOLUTION = "devolution"


class DisputeState(StrEnum):
    OPEN = "open"


class DisputeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: Identifier
    customer_id: Identifier
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    reason: Reason
    description: str | None = Field(default=None, max_length=1000)


class Dispute(DisputeCreate):
    # Fields with defaults (state) are always present in responses, so mark them required
    # in the generated OpenAPI schema.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: UUID
    state: DisputeState = DisputeState.OPEN
    created_at: datetime
