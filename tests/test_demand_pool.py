"""3H, I1: the versioned synthetic demand pool and its strict loader (plan ID-1, §6.3)."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from coalition_travel.application.lot_admissibility import lot_admissibility
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.travel_units import build_travel_unit
from coalition_travel.application.trip_planning import route_key
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog
from coalition_travel.infrastructure.demand.demand_pool import DemandPoolError, load_demand_pool
from p4_support import REFERENCE

ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = ROOT / "data/demand/demand_pool_v1.jsonl"
CATALOG_PATH = ROOT / "data/catalog/catalog_v1.json"
POOL_SHA256 = "ef9513a057f2b7d1e87418a4f47ccc4879e4fcb6b5ed985e232119161679d476"
LARGEST_TRAVELLER_REQUEST = 20  # TravelRequestDraft.travellers <= 20
MAX_POOL_REQUESTS_PER_ROUTE = 13  # one component holds at most 14 units


def pool_units():
    return [
        build_travel_unit(item.request_id, item.draft, REFERENCE)
        for item in load_demand_pool(POOL_PATH).requests
    ]


def test_versioned_pool_loads_with_its_manifest():
    pool = load_demand_pool(POOL_PATH)
    assert hashlib.sha256(POOL_PATH.read_bytes()).hexdigest() == POOL_SHA256 == pool.sha256
    assert (pool.version, pool.catalog_version) == ("demand-pool-v1", "catalog-v1")
    assert [item.request_id for item in pool.requests] == [
        "pool-tyo-01",
        "pool-tyo-02",
        "pool-tyo-03",
        "pool-tyo-04",
        "pool-rom-01",
        "pool-rom-02",
    ]
    assert len(pool_units()) == 6  # every request is ready at the reference date


def test_pool_respects_the_route_limit_and_h2_with_the_largest_traveller_request():
    catalog, _ = load_offer_catalog(CATALOG_PATH)
    units = pool_units()
    routes = Counter(route_key(unit) for unit in units)
    assert routes and max(routes.values()) <= MAX_POOL_REQUESTS_PER_ROUTE
    for route in routes:
        largest = build_travel_unit(
            "user",
            TravelRequestDraft(
                destination=route, travellers=LARGEST_TRAVELLER_REQUEST, budget_per_person="900"
            ),
            REFERENCE,
        )
        lot = lot_admissibility(
            [largest, *(unit for unit in units if route_key(unit) == route)], catalog, REFERENCE
        )
        assert lot.status == "optimizable", route
        assert all(check.valid for check in lot.capacity_checks), route


def write_pool(tmp_path, lines, **manifest_changes):
    pool = tmp_path / "pool_v1.jsonl"
    raw = ("".join(line + "\n" for line in lines)).encode("utf-8")
    pool.write_bytes(raw)
    manifest = {
        "version": "test-pool",
        "pool_file": pool.name,
        "pool_sha256": hashlib.sha256(raw).hexdigest(),
        "synthetic": True,
        "catalog_version": "catalog-v1",
        "requests": len(lines),
        "purpose": "test",
        "limitations": ["test"],
    }
    manifest.update(manifest_changes)
    pool.with_suffix(".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pool


GOOD = '{"request_id":"pool-a","synthetic":true,"draft":{"destination":"Tokyo","travellers":1,"budget_per_person":"500"}}'


def test_a_minimal_pool_loads(tmp_path):
    pool = load_demand_pool(write_pool(tmp_path, [GOOD]))
    assert [item.request_id for item in pool.requests] == ["pool-a"]


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (GOOD.replace('"500"', "500.5"), "decimal number"),
        (GOOD.replace('"500"', "NaN"), "constant"),
        (GOOD.replace('"synthetic":true', '"synthetic":true,"synthetic":true'), "duplicate key"),
        (GOOD.replace('"synthetic":true', '"synthetic":false'), "synthetic must be true"),
        (GOOD.replace('"synthetic":true,', ""), "missing keys"),
        (GOOD.replace('"synthetic":true', '"synthetic":true,"note":"x"'), "unknown keys"),
        (GOOD.replace("pool-a", "user-1"), "request_id must match"),
        (GOOD.replace("pool-a", "pool-A"), "request_id must match"),
        (GOOD.replace('"travellers":1', '"travellers":0'), "invalid draft"),
        (GOOD.replace('"travellers":1', '"travellers":1,"price":3'), "invalid draft"),
        ('["not", "an", "object"]', "expected an object"),
        ("{", "invalid JSON"),
    ],
)
def test_malformed_pool_lines_are_refused(tmp_path, line, message):
    with pytest.raises(DemandPoolError, match=message):
        load_demand_pool(write_pool(tmp_path, [line]))


def test_duplicate_identifiers_and_blank_lines_are_refused(tmp_path):
    with pytest.raises(DemandPoolError, match="unique"):
        load_demand_pool(write_pool(tmp_path, [GOOD, GOOD]))
    with pytest.raises(DemandPoolError, match="invalid JSON"):
        load_demand_pool(write_pool(tmp_path, [GOOD, "", GOOD.replace("pool-a", "pool-b")]))
    with pytest.raises(DemandPoolError, match="empty"):
        load_demand_pool(write_pool(tmp_path, []))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"pool_sha256": "0" * 64}, "does not match the file"),
        ({"pool_sha256": "ABC"}, "lowercase SHA-256"),
        ({"requests": 2}, "requests count"),
        ({"synthetic": False}, "synthetic must be true"),
        ({"pool_file": "other.jsonl"}, "pool_file"),
        ({"catalog_version": ""}, "catalog_version"),
        ({"limitations": []}, "limitations"),
        ({"extra": 1}, "unknown keys"),
    ],
)
def test_manifest_inconsistencies_are_refused(tmp_path, changes, message):
    with pytest.raises(DemandPoolError, match=message):
        load_demand_pool(write_pool(tmp_path, [GOOD], **changes))


def test_missing_manifest_and_invalid_utf8_are_refused(tmp_path):
    pool = write_pool(tmp_path, [GOOD])
    pool.with_suffix(".manifest.json").unlink()
    with pytest.raises(DemandPoolError, match="missing demand pool manifest"):
        load_demand_pool(pool)
    pool.write_bytes(b"\xff\xfe")
    with pytest.raises(DemandPoolError, match="UTF-8"):
        load_demand_pool(pool)
    with pytest.raises(DemandPoolError, match="cannot read"):
        load_demand_pool(tmp_path / "absent.jsonl")
