import csv
from io import StringIO
import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from peakledger.api import app, SECTIONS
from peakledger.settings import DEFAULT_BUDGET, DEFAULT_DAY


@pytest.fixture
def handler(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSHOP_DB", str(tmp_path / "http.db"))
    with TestClient(app) as client:
        yield client


def test_cli_http_and_csv_same_batch(handler):
    summary = subprocess.run(
        [sys.executable, "-m", "peakledger.cli", "plan", "--summary"],
        check=True,
        capture_output=True,
        text=True,
    )
    cli = json.loads(summary.stdout)
    trial = handler.get("/api/plan").json()
    assert cli["run_id"] == trial["run_id"]
    assert cli["used"] == trial["summary"]["used"]
    records = list(
        csv.DictReader(
            StringIO(handler.get("/api/decisions.csv").text.lstrip("\ufeff"))
        )
    )
    assert len(records) == trial["summary"]["cases"]
    assert {row["case_id"] for row in records} == set(trial["row_evidence"])


def test_every_module_evidence_and_detail_are_reachable(handler):
    report = handler.get("/api/plan").json()
    for module in SECTIONS:
        response = handler.get(f"/api/modules/{module}")
        assert (
            response.status_code == 200
            and response.json()["run_id"] == report["run_id"]
        )
        assert response.json()["evidence"]
    row = report["decisions"][0]
    assert handler.get("/api/decisions/" + row["case_id"]).json()["decision"] == row
    assert handler.get("/api/modules/missing").status_code == 404
    assert handler.get("/api/decisions/INVALID-TEMP").status_code == 404


def test_invalid_quota_and_unknown_schema_return_422(handler):
    assert handler.get("/api/plan?capacity=-1").status_code == 422
    assert handler.post("/api/plan", json={"capacity": "4"}).status_code == 422
    assert (
        handler.post(
            "/api/plan", json={"packet": {"observations": [], "mystery": []}}
        ).status_code
        == 422
    )
    over = handler.post(
        "/api/plan",
        content=b" " * 2_000_001,
        headers={"Content-Type": "application/json"},
    )
    assert over.status_code == 413


def test_explicit_plan_and_generation_guard_round_trip(handler, original):
    original_digest = handler.get("/api/plan").json()["run_id"]
    command = {"packet": original, "capacity": DEFAULT_BUDGET, "as_of": DEFAULT_DAY}
    assert handler.post("/api/plan", json=command).json()["run_id"] == original_digest
    command.update(expected_generation=0, run_id=original_digest)
    first = handler.post("/api/releases", json=command)
    assert first.status_code == 201 and first.json()["generation"] == 1
    assert handler.post("/api/releases", json=command).json()["replayed"]
    result = handler.get("/api/releases/1").json()
    assert result["run_id"] == original_digest
    assert handler.get("/api/releases?limit=1").json()[0]["generation"] == 1
    assert handler.get("/api/releases/99").status_code == 404
    different = handler.get("/api/plan?capacity=0").json()["run_id"]
    assert (
        handler.post(
            "/api/releases",
            json={"capacity": 0, "expected_generation": 0, "run_id": different},
        ).status_code
        == 409
    )


def test_gear_packet_round_trips_through_plan_and_release(handler, original):
    packet = {
        **original,
        "coefficients": [
            {"case_id": "G1", "group": "商业综合体", "day": 143, "arrived": 143,
             "revision": 1, "coefficient": 0.7},
            {"case_id": "G2", "group": "商业综合体", "day": 143, "arrived": 143,
             "revision": 1, "coefficient": 0.85},
        ],
    }
    command = {"packet": packet, "capacity": DEFAULT_BUDGET, "as_of": DEFAULT_DAY}
    trial = handler.post("/api/plan", json=command)
    assert trial.status_code == 200
    body = trial.json()
    confirmation = body["confirmation"]
    assert confirmation["pending"] == {"商业综合体": [0.7, 0.85]}
    assert set(confirmation["roster"]) == {
        row["case_id"] for row in body["decisions"] if row["status"] == "allocated"
    }
    assert handler.get("/api/summary").json()["confirmation"] is None
    command.update(expected_generation=0, run_id=body["run_id"])
    registered = handler.post("/api/releases", json=command)
    assert registered.status_code == 201
    archived = handler.get(f"/api/releases/{registered.json()['generation']}").json()
    assert archived["evidence"]["confirmation"] == confirmation

