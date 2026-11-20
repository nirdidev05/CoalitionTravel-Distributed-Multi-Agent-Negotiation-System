"""I2, decision D-I2-3: the two hardening reserves of the I1 review (I1 report, §9)."""

import hashlib
import json

import pytest
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.trip_planning import (
    DemandPoolSnapshot,
    PlanningInputError,
    PlanningRequest,
)
from coalition_travel.infrastructure.demand.demand_pool import DemandPoolError, load_demand_pool

DRAFT = TravelRequestDraft(destination="Tokyo", travellers=1, budget_per_person="500")


@pytest.mark.parametrize("digest", ["x", "0" * 63, "0" * 65, "A" * 64, "g" * 64, " " + "0" * 63])
def test_a_snapshot_needs_a_lowercase_sha256_digest(digest):
    """Reserve 1: a directly built DemandPoolSnapshot carries a real provenance digest."""
    with pytest.raises(PlanningInputError, match="64 lowercase hexadecimal"):
        DemandPoolSnapshot("pool", digest, "catalog-v1", (PlanningRequest("pool-a", DRAFT),))
    valid = DemandPoolSnapshot("pool", "a" * 64, "catalog-v1", ())
    assert valid.sha256 == "a" * 64


def test_an_invalid_manifest_encoding_is_a_demand_pool_error(tmp_path):
    """Reserve 2: the manifest's UTF-8 decoding is wrapped like the pool file's."""
    line = json.dumps(
        {"request_id": "pool-a", "synthetic": True, "draft": DRAFT.model_dump(mode="json")}
    )
    pool = tmp_path / "pool_v1.jsonl"
    pool.write_bytes((line + "\n").encode("utf-8"))
    pool.with_suffix(".manifest.json").write_bytes(b"\xff\xfe{}")
    with pytest.raises(DemandPoolError, match="invalid UTF-8"):
        load_demand_pool(pool)
    assert hashlib.sha256(pool.read_bytes()).hexdigest()  # the pool file itself is fine
