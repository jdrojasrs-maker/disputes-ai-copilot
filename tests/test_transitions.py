from itertools import product

import pytest

from disputes.models import DisputeState
from disputes.transitions import ALLOWED_TRANSITIONS, is_allowed

S = DisputeState

ALLOWED_PAIRS = {
    (S.OPEN, S.UNDER_REVIEW),
    (S.OPEN, S.WITHDRAWN),
    (S.UNDER_REVIEW, S.RESOLVED),
    (S.UNDER_REVIEW, S.REJECTED),
    (S.UNDER_REVIEW, S.WITHDRAWN),
}

ALL_PAIRS = list(product(DisputeState, DisputeState))


def test_there_are_25_pairs_and_5_of_them_are_allowed():
    assert len(ALL_PAIRS) == 25
    assert len(ALLOWED_PAIRS) == 5


@pytest.mark.parametrize(("from_state", "to_state"), ALL_PAIRS)
def test_is_allowed_is_true_for_exactly_the_five_pairs(
    from_state: DisputeState, to_state: DisputeState
):
    assert is_allowed(from_state, to_state) is ((from_state, to_state) in ALLOWED_PAIRS)


@pytest.mark.parametrize("state", list(DisputeState))
def test_a_state_to_itself_is_refused(state: DisputeState):
    assert is_allowed(state, state) is False


@pytest.mark.parametrize("state", list(DisputeState))
def test_no_state_goes_back_to_open(state: DisputeState):
    assert is_allowed(state, S.OPEN) is False


def test_the_table_has_a_key_for_each_state():
    assert set(ALLOWED_TRANSITIONS) == set(DisputeState)


@pytest.mark.parametrize("state", [S.RESOLVED, S.REJECTED, S.WITHDRAWN])
def test_closed_states_have_no_way_out(state: DisputeState):
    assert ALLOWED_TRANSITIONS[state] == frozenset()
