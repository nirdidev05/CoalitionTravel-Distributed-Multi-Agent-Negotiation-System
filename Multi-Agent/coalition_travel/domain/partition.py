"""Coalition partition validation and shared agent identifier checks."""


def _validate_agents(agents):
    try:
        unique_count = len(set(agents))
    except TypeError as exc:
        raise TypeError("agent identifiers must be hashable") from exc
    if unique_count != len(agents):
        raise ValueError("agent identifiers must be unique")


def validate_partition(agents, structure):
    """Raise ValueError unless structure partitions the agents exactly once."""
    expected = set(agents)
    seen = set()
    for coalition in structure:
        members = set(coalition)
        if not members:
            raise ValueError("partitions cannot contain empty coalitions")
        if not members <= expected:
            raise ValueError("partition contains unknown agents")
        if seen.intersection(members):
            raise ValueError("partition assigns an agent more than once")
        seen.update(members)
    if seen != expected:
        raise ValueError("partition does not cover every agent")
    return True
