"""Persistence, seeding idempotency, and route smoke tests.

Route tests need a seeded database; they skip cleanly if the repo has not been
seeded yet, which is the state a fresh clone is in before `./run.sh` runs.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import charts, db, generate as gen

ROUTES = ["/", "/performance", "/calibration", "/drift", "/subgroups", "/policy",
          "/model-card", "/data"]


@pytest.fixture(scope="module")
def client():
    conn = db.connect()
    try:
        seeded = bool(db.all_artifacts(conn))
    except Exception:
        seeded = False
    finally:
        conn.close()
    if not seeded:
        pytest.skip("database not seeded; run `python -m app.seed` first")
    from app.main import app

    return TestClient(app)


@pytest.mark.parametrize("route", ROUTES)
def test_every_nav_route_returns_html(client, route):
    r = client.get(route)
    assert r.status_code == 200, route
    assert "text/html" in r.headers["content-type"]
    assert "<h1>" in r.text
    assert 'class="lede"' in r.text


def test_every_page_labels_the_data_as_synthetic(client):
    for route in ROUTES:
        assert "note-warn" in client.get(route).text, f"{route} lacks a synthetic-data warning"


def test_policy_form_parameters_change_the_answer(client):
    strict = client.get("/policy?threshold=0.02&lgd=0.65&margin=0.09&fr_cost=45").text
    loose = client.get("/policy?threshold=0.40&lgd=0.65&margin=0.09&fr_cost=45").text
    assert strict != loose
    for preset in ("conservative", "balanced", "growth"):
        assert client.get(f"/policy?preset={preset}").status_code == 200


def test_policy_clamps_out_of_range_input(client):
    assert client.get("/policy?threshold=99&lgd=-5&margin=50&fr_cost=1e9").status_code == 200


def test_sqlite_round_trip_preserves_missing_values(tmp_path):
    df = gen.generate(n=1_200, seed=3)
    conn = db.connect(tmp_path / "t.db")
    db.init(conn)
    db.write_applicants(conn, df)
    rows = conn.execute(
        "SELECT COUNT(*) AS n, SUM(income IS NULL) AS missing FROM applicants"
    ).fetchone()
    assert rows["n"] == len(df)
    assert rows["missing"] == int(df["income"].isna().sum())
    conn.close()


def test_artifacts_round_trip_through_json(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init(conn)
    payload = {"a": np.float64(1.5), "b": np.int64(3), "c": [np.bool_(True)]}
    db.put(conn, "k", payload)
    assert db.get(conn, "k") == {"a": 1.5, "b": 3, "c": [True]}
    db.put(conn, "k", {"a": 2.0})
    assert db.get(conn, "k") == {"a": 2.0}, "put must upsert, not duplicate"
    conn.close()


def test_seeding_is_idempotent(tmp_path):
    """A second run with the same version must not duplicate rows."""
    from app import seed as seed_mod

    conn = db.connect(tmp_path / "t.db")
    db.init(conn)
    df = gen.generate(n=1_200, seed=3)
    db.write_applicants(conn, df)
    db.put(conn, "meta", {"seed_version": seed_mod.SEED_VERSION})
    assert db.is_seeded(conn, seed_mod.SEED_VERSION)
    assert not db.is_seeded(conn, "some-other-version")

    db.reset(conn)
    db.write_applicants(conn, df)
    assert conn.execute("SELECT COUNT(*) AS n FROM applicants").fetchone()["n"] == len(df)
    conn.close()


def test_chart_renders_axis_labels_and_units():
    svg = str(
        charts.line_chart(
            [{"name": "series", "points": [(1, 0.5), (2, 0.7)]}],
            "Application month",
            "AUC (0.5 = coin flip)",
        )
    )
    assert svg.startswith('<div class="chart">')
    assert "Application month" in svg
    assert "AUC (0.5 = coin flip)" in svg
    assert "<polyline" in svg and "viewBox" in svg


def test_chart_handles_an_empty_series_without_crashing():
    assert "empty" in str(charts.line_chart([], "x", "y"))


def test_chart_series_helper_drops_non_finite_points():
    rows = [{"month": 1, "v": 0.5}, {"month": 2, "v": float("nan")}, {"month": 3, "v": 0.7}]
    s = charts.series(rows, "month", "v", "x")
    assert s["points"] == [(1, 0.5), (3, 0.7)]
