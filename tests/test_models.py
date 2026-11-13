from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from disputes.models import Dispute, DisputeCreate, DisputeState, Reason

VALID_DATA = {
    "transaction_id": "txn_0001",
    "customer_id": "cust_0001",
    "amount": "125.50",
    "currency": "USD",
    "reason": "duplicate_charge",
}


def test_dispute_create_builds_from_valid_data():
    dispute = DisputeCreate(**VALID_DATA)

    assert dispute.transaction_id == "txn_0001"
    assert dispute.customer_id == "cust_0001"
    assert dispute.amount == Decimal("125.50")
    assert dispute.currency == "USD"
    assert dispute.reason is Reason.DUPLICATE_CHARGE
    assert dispute.description is None


def test_reason_values_match_the_contract():
    assert {reason.value for reason in Reason} == {
        "duplicate_charge",
        "unrecognized_charge",
        "product_not_received",
        "incorrect_amount",
        "devolution",
    }


def test_dispute_starts_open():
    create = DisputeCreate(**VALID_DATA)

    dispute = Dispute(**create.model_dump(), id=uuid4(), created_at=datetime.now(UTC))

    assert dispute.state is DisputeState.OPEN
    assert DisputeState.OPEN.value == "open"


# --- Validation rules (US2) -------------------------------------------------


@pytest.mark.parametrize("amount", ["0", "-1", "10.001", "12345678901.23"])
def test_invalid_amount_is_rejected(amount: str):
    with pytest.raises(ValidationError):
        DisputeCreate(**{**VALID_DATA, "amount": amount})


@pytest.mark.parametrize("amount", ["0.01", "10.50", "1234567890.12"])
def test_valid_amount_is_accepted(amount: str):
    dispute = DisputeCreate(**{**VALID_DATA, "amount": amount})

    assert dispute.amount == Decimal(amount)


@pytest.mark.parametrize("reason", ["refund", "Duplicate Charge"])
def test_reason_outside_the_list_is_rejected(reason: str):
    with pytest.raises(ValidationError):
        DisputeCreate(**{**VALID_DATA, "reason": reason})


@pytest.mark.parametrize("currency", ["usd", "US", "USDX", ""])
def test_invalid_currency_is_rejected(currency: str):
    with pytest.raises(ValidationError):
        DisputeCreate(**{**VALID_DATA, "currency": currency})


@pytest.mark.parametrize("field", ["transaction_id", "customer_id"])
@pytest.mark.parametrize("value", ["", "   ", "a" * 65])
def test_invalid_identifier_is_rejected(field: str, value: str):
    with pytest.raises(ValidationError):
        DisputeCreate(**{**VALID_DATA, field: value})


@pytest.mark.parametrize("field", ["transaction_id", "customer_id"])
@pytest.mark.parametrize("value", ["a", "a" * 64])
def test_identifier_length_limits_are_accepted(field: str, value: str):
    dispute = DisputeCreate(**{**VALID_DATA, field: value})

    assert getattr(dispute, field) == value


@pytest.mark.parametrize("field", ["transaction_id", "customer_id"])
def test_identifier_is_stripped(field: str):
    dispute = DisputeCreate(**{**VALID_DATA, field: "  abc  "})

    assert getattr(dispute, field) == "abc"


def test_description_of_1000_characters_is_accepted():
    dispute = DisputeCreate(**VALID_DATA, description="x" * 1000)

    assert len(dispute.description) == 1000


def test_description_of_1001_characters_is_rejected():
    with pytest.raises(ValidationError):
        DisputeCreate(**VALID_DATA, description="x" * 1001)


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        DisputeCreate(**VALID_DATA, state="closed")
