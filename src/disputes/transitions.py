from disputes.models import DisputeState

# The only place that lists which state changes are allowed. The closed states have no way out.
ALLOWED_TRANSITIONS: dict[DisputeState, frozenset[DisputeState]] = {
    DisputeState.OPEN: frozenset({DisputeState.UNDER_REVIEW, DisputeState.WITHDRAWN}),
    DisputeState.UNDER_REVIEW: frozenset(
        {DisputeState.RESOLVED, DisputeState.REJECTED, DisputeState.WITHDRAWN}
    ),
    DisputeState.RESOLVED: frozenset(),
    DisputeState.REJECTED: frozenset(),
    DisputeState.WITHDRAWN: frozenset(),
}


def is_allowed(from_state: DisputeState, to_state: DisputeState) -> bool:
    return to_state in ALLOWED_TRANSITIONS[from_state]
