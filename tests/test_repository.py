from datetime import UTC, datetime
from uuid import uuid4

from disputes.models import Dispute
from disputes.repository import InMemoryDisputeRepository


def make_dispute() -> Dispute:
    return Dispute(
        id=uuid4(),
        transaction_id="txn_0001",
        customer_id="cust_0001",
        amount="125.50",
        currency="USD",
        reason="duplicate_charge",
        created_at=datetime.now(UTC),
    )


def test_add_then_get_returns_the_same_dispute():
    repository = InMemoryDisputeRepository()
    dispute = make_dispute()

    repository.add(dispute)

    assert repository.get(dispute.id) == dispute


def test_get_unknown_id_returns_none():
    repository = InMemoryDisputeRepository()

    assert repository.get(uuid4()) is None


def test_two_repositories_do_not_share_data():
    first = InMemoryDisputeRepository()
    second = InMemoryDisputeRepository()
    dispute = make_dispute()

    first.add(dispute)

    assert second.get(dispute.id) is None
    assert second.disputes == {}
