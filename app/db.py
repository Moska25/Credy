"""SQLite persistence. Plain sqlite3, plain SQL strings, no ORM.

Three tables:
  applicants  - the generated cohort, one row per application
  predictions - one row per applicant per model, filled at seed time
  artifacts   - key -> JSON blob, everything the web app renders

The web app only ever reads. All fitting happens in `seed.py`.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "credy.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS applicants (
  applicant_id         INTEGER PRIMARY KEY,
  month                INTEGER NOT NULL,
  age                  REAL,
  income               REAL,
  employment_type      TEXT,
  employment_tenure    REAL,
  debt_ratio           REAL,
  credit_history_years REAL,
  prior_delinquencies  REAL,
  loan_amount          REAL,
  term_months          REAL,
  region               TEXT,
  channel              TEXT,
  true_pd              REAL,
  "default"            INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_applicants_month ON applicants(month);

CREATE TABLE IF NOT EXISTS predictions (
  applicant_id INTEGER NOT NULL,
  model        TEXT NOT NULL,
  score        REAL NOT NULL,
  PRIMARY KEY (applicant_id, model)
);

CREATE TABLE IF NOT EXISTS artifacts (
  key     TEXT PRIMARY KEY,
  payload TEXT NOT NULL
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def reset(conn: sqlite3.Connection) -> None:
    """Drop and rebuild. Seeding is idempotent by rebuilding, not by upserting."""
    conn.executescript(
        "DROP TABLE IF EXISTS applicants;"
        "DROP TABLE IF EXISTS predictions;"
        "DROP TABLE IF EXISTS artifacts;"
    )
    init(conn)


def write_applicants(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    cols = [
        "applicant_id", "month", "age", "income", "employment_type", "employment_tenure",
        "debt_ratio", "credit_history_years", "prior_delinquencies", "loan_amount",
        "term_months", "region", "channel", "true_pd", "default",
    ]
    rows = df[cols].astype(object).where(pd.notnull(df[cols]), None).itertuples(index=False, name=None)
    conn.executemany(
        'INSERT INTO applicants (applicant_id, month, age, income, employment_type, '
        'employment_tenure, debt_ratio, credit_history_years, prior_delinquencies, '
        'loan_amount, term_months, region, channel, true_pd, "default") '
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


def write_predictions(conn: sqlite3.Connection, applicant_ids, scores_by_model: dict) -> None:
    payload = [
        (int(aid), model, float(score))
        for model, scores in scores_by_model.items()
        for aid, score in zip(applicant_ids, scores)
    ]
    conn.executemany("INSERT INTO predictions (applicant_id, model, score) VALUES (?,?,?)", payload)
    conn.commit()


def put(conn: sqlite3.Connection, key: str, payload) -> None:
    conn.execute(
        "INSERT INTO artifacts (key, payload) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload",
        (key, json.dumps(payload, default=_jsonable)),
    )
    conn.commit()


def get(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT payload FROM artifacts WHERE key = ?", (key,)).fetchone()
    return json.loads(row["payload"]) if row else default


def all_artifacts(conn: sqlite3.Connection) -> dict:
    return {r["key"]: json.loads(r["payload"]) for r in conn.execute("SELECT key, payload FROM artifacts")}


def is_seeded(conn: sqlite3.Connection, version: str) -> bool:
    try:
        meta = get(conn, "meta")
    except sqlite3.OperationalError:
        return False
    return bool(meta and meta.get("seed_version") == version)


def _jsonable(obj):
    import numpy as np

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    raise TypeError(f"not JSON serialisable: {type(obj)}")
