import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from disputes.models import Dispute, DisputeState, StateChange
from disputes.repository import InMemoryDisputeRepository


def make_dispute() -> Dispute:
    created_at = datetime.now(UTC)
    return Dispute(
        id=uuid4(),
        transaction_id="txn_0001",
        customer_id="cust_0001",
        amount="125.50",
        currency="USD",
        reason="duplicate_charge",
        created_at=created_at,
        updated_at=created_at,
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


# --- transition (feature 002) -------------------------------------------------

OPEN = DisputeState.OPEN
UNDER_REVIEW = DisputeState.UNDER_REVIEW
RESOLVED = DisputeState.RESOLVED


def stored_dispute(repository: InMemoryDisputeRepository) -> Dispute:
    dispute = make_dispute()
    repository.add(dispute)
    return dispute


def test_transition_moves_the_dispute_and_records_one_history_entry():
    repository = InMemoryDisputeRepository()
    dispute = stored_dispute(repository)
    at = dispute.updated_at + timedelta(seconds=5)

    result = repository.transition(dispute.id, OPEN, UNDER_REVIEW, "note", at)

    assert result is not None
    assert result.state is UNDER_REVIEW
    assert result.updated_at == at
    assert result.history == [
        StateChange(from_state=OPEN, to_state=UNDER_REVIEW, note="note", changed_at=at)
    ]


def test_get_returns_the_transitioned_dispute():
    repository = InMemoryDisputeRepository()
    dispute = stored_dispute(repository)
    at = dispute.updated_at + timedelta(seconds=5)

    result = repository.transition(dispute.id, OPEN, UNDER_REVIEW, None, at)

    assert repository.get(dispute.id) == result


def test_transition_does_not_mutate_the_dispute_stored_before():
    repository = InMemoryDisputeRepository()
    dispute = stored_dispute(repository)
    at = dispute.updated_at + timedelta(seconds=5)

    repository.transition(dispute.id, OPEN, UNDER_REVIEW, None, at)

    assert dispute.state is OPEN
    assert dispute.history == []


def test_transition_with_a_stale_from_state_returns_none_and_changes_nothing():
    repository = InMemoryDisputeRepository()
    dispute = stored_dispute(repository)
    at = dispute.updated_at + timedelta(seconds=5)

    result = repository.transition(dispute.id, UNDER_REVIEW, RESOLVED, None, at)

    assert result is None
    assert repository.get(dispute.id) == dispute


def test_transition_of_an_unknown_id_returns_none():
    repository = InMemoryDisputeRepository()

    result = repository.transition(uuid4(), OPEN, UNDER_REVIEW, None, datetime.now(UTC))

    assert result is None


def test_transition_without_a_note_records_none():
    repository = InMemoryDisputeRepository()
    dispute = stored_dispute(repository)
    at = dispute.updated_at + timedelta(seconds=5)

    result = repository.transition(dispute.id, OPEN, UNDER_REVIEW, None, at)

    assert result is not None
    assert result.history[0].note is None


def test_two_transitions_build_a_history_in_order():
    repository = InMemoryDisputeRepository()
    dispute = stored_dispute(repository)
    first_at = dispute.updated_at + timedelta(seconds=5)
    second_at = first_at + timedelta(seconds=5)

    repository.transition(dispute.id, OPEN, UNDER_REVIEW, "first", first_at)
    result = repository.transition(dispute.id, UNDER_REVIEW, RESOLVED, "second", second_at)

    assert result is not None
    assert [(c.from_state, c.to_state, c.note) for c in result.history] == [
        (OPEN, UNDER_REVIEW, "first"),
        (UNDER_REVIEW, RESOLVED, "second"),
    ]
    assert result.updated_at == second_at


def test_time_never_goes_backwards():
    repository = InMemoryDisputeRepository()
    dispute = stored_dispute(repository)
    stored_time = dispute.updated_at

    late = repository.transition(
        dispute.id, OPEN, UNDER_REVIEW, None, stored_time - timedelta(seconds=1)
    )

    assert late is not None
    assert late.updated_at == stored_time
    assert late.history[-1].changed_at == stored_time

    later = repository.transition(
        dispute.id, UNDER_REVIEW, RESOLVED, None, stored_time + timedelta(seconds=1)
    )

    assert later is not None
    assert later.updated_at == stored_time + timedelta(seconds=1)
    assert later.history[-1].changed_at == stored_time + timedelta(seconds=1)


# --- atomicity (US3) ----------------------------------------------------------

THREADS = 8


class SlowDict(dict):
    """A dict whose reads pause briefly, so unprotected check-then-write code overlaps.

    The value is read first and the pause comes after, so a caller holds a stale value while
    other threads read the same one; sleeping before the read would leave almost no overlap.
    """

    def get(self, key, default=None):
        value = super().get(key, default)
        time.sleep(0.05)
        return value

    def __getitem__(self, key):
        value = super().__getitem__(key)
        time.sleep(0.05)
        return value


def run_together(calls) -> list:
    """Run each callable in its own thread, released at the same moment; return the results."""
    barrier = threading.Barrier(len(calls))

    def wait_then_call(call):
        barrier.wait()
        return call()

    with ThreadPoolExecutor(len(calls)) as pool:
        futures = [pool.submit(wait_then_call, call) for call in calls]
        return [future.result() for future in futures]


def test_transition_is_atomic_under_a_slow_read():
    repository = InMemoryDisputeRepository()
    repository.disputes = SlowDict()
    dispute = stored_dispute(repository)
    now = datetime.now(UTC)

    results = run_together(
        [
            lambda: repository.transition(dispute.id, OPEN, UNDER_REVIEW, None, now)
            for _ in range(THREADS)
        ]
    )

    assert sum(result is not None for result in results) == 1
    assert sum(result is None for result in results) == THREADS - 1
    stored = repository.get(dispute.id)
    assert stored is not None
    assert len(stored.history) == 1


def test_transitions_on_different_disputes_all_succeed_together():
    repository = InMemoryDisputeRepository()
    repository.disputes = SlowDict()
    disputes = [stored_dispute(repository) for _ in range(THREADS)]
    now = datetime.now(UTC)

    def move(dispute_id: UUID):
        return lambda: repository.transition(dispute_id, OPEN, UNDER_REVIEW, None, now)

    results = run_together([move(dispute.id) for dispute in disputes])

    assert all(result is not None for result in results)
    assert all(result.state is UNDER_REVIEW for result in results)
