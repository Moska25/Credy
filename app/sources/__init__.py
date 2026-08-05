"""Source-agnostic applicant schema and the adapter registry.

The rest of this repository is built on a synthetic population whose drift
schedule is known. That is what makes the verification table on `/drift`
possible, and it is also the project's biggest limitation: the model is being
tested on a world simple enough to write down. This package is the seam that
lets the same pipeline run against real lending data.

Two rules make it worth having.

**A missing column must fail by name.** Without a schema check, a frame that is
missing `debt_ratio` gets all the way into `models.design_matrix` and dies on a
bare `KeyError: 'debt_ratio'` twelve frames deep, which tells a reader nothing
about which source produced the bad frame. `check` raises `SchemaError` naming
the source, the column and what the column is for.

**A source must declare what it cannot fill.** The synthetic schema has fields
that real datasets simply do not carry: Lending Club has no applicant age,
Home Credit has no application date. The dishonest move is to invent them. The
honest one is to fill the column with a null (numeric) or the explicit level
`unknown` (categorical) and report the coverage, so a reader can see which parts
of a result rest on real data and which parts rest on nothing at all.
"""

from __future__ import annotations

from importlib import import_module

import pandas as pd

from .. import generate as gen

# ---------------------------------------------------------------------------
# the schema
# ---------------------------------------------------------------------------
KEY_COLUMNS = ["applicant_id", "month", "default"]
REQUIRED_COLUMNS = KEY_COLUMNS + gen.FEATURES_ALL

#: Columns a real source is allowed to leave entirely null. Every one of them
#: is a genuine gap in at least one public dataset, and `models.design_matrix`
#: already carries a missing indicator for the three that matter most.
NULLABLE_COLUMNS = {
    "age",
    "income",
    "employment_tenure",
    "credit_history_years",
    "prior_delinquencies",
    "term_months",
}

#: The level an adapter uses when a source cannot fill a categorical at all.
#: It is never produced by the generator, so its presence in a frame is always
#: a statement about a real source rather than about the simulation.
UNKNOWN = "unknown"

CATEGORICAL_LEVELS = {
    "employment_type": set(gen.EMPLOYMENT) | {UNKNOWN},
    "region": set(gen.REGIONS) | {UNKNOWN},
    "channel": set(gen.CHANNELS) | {UNKNOWN},
}

COLUMN_PURPOSE = {
    "applicant_id": "surrogate key, unique per application",
    "month": "integer cohort index, 1 = earliest cohort in the extract",
    "default": "binary outcome label, 1 = defaulted within the performance window",
    **{c: "model feature" for c in gen.FEATURES_ALL},
}


class SchemaError(ValueError):
    """A frame does not satisfy the applicant schema.

    Raised at load time, naming the source and the offending column, so the
    failure never reaches `models.design_matrix` as an anonymous KeyError.
    """


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def check(df: pd.DataFrame, source: str = "?") -> None:
    """Raise `SchemaError` unless `df` can be fed to the modelling pipeline.

    Checks only what would otherwise corrupt a result silently: a missing
    column, a non-positive cohort index, a label outside {0, 1}, and a
    categorical level the one-hot encoder does not know about. An unmapped
    level is the nastiest of the four, because `design_matrix` encodes it as an
    all-zero row rather than failing, so the applicant quietly becomes the
    reference level and nothing anywhere says so.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(
            f"source {source!r} is missing required column(s) "
            + ", ".join(f"{c!r} ({COLUMN_PURPOSE[c]})" for c in missing)
            + f". The applicant schema needs all of: {', '.join(REQUIRED_COLUMNS)}."
        )
    if df.empty:
        raise SchemaError(f"source {source!r} produced zero rows.")

    months = pd.to_numeric(df["month"], errors="coerce")
    if months.isna().any() or (months < 1).any() or (months % 1 != 0).any():
        raise SchemaError(
            f"source {source!r} has a bad 'month': every row needs a positive "
            "integer cohort index (1 = earliest cohort in the extract)."
        )

    labels = pd.to_numeric(df["default"], errors="coerce").dropna().unique()
    bad = sorted(v for v in labels if v not in (0, 1))
    if bad:
        raise SchemaError(
            f"source {source!r} has 'default' values outside {{0, 1}}: {bad}. "
            "An unresolved outcome must be excluded or left null, never coerced to good."
        )

    for col, allowed in CATEGORICAL_LEVELS.items():
        seen = set(df[col].dropna().unique())
        unknown = sorted(seen - allowed)
        if unknown:
            raise SchemaError(
                f"source {source!r} has unmapped level(s) in {col!r}: {unknown}. "
                f"Map them onto {sorted(allowed)} in the adapter. An unmapped level is "
                "encoded as an all-zero one-hot row, so it would silently become the "
                "reference level instead of failing."
            )

    for col in REQUIRED_COLUMNS:
        if col in NULLABLE_COLUMNS or col in CATEGORICAL_LEVELS:
            continue
        if df[col].isna().any():
            raise SchemaError(
                f"source {source!r} has nulls in {col!r} "
                f"({COLUMN_PURPOSE[col]}), which is not a nullable column."
            )


def coverage(df: pd.DataFrame) -> dict:
    """Per-column share of rows carrying a real value.

    A column an adapter could not fill reads 0.0 here. This is the number that
    keeps a real-data run honest: it says which conclusions rest on data.
    """
    out = {}
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            out[col] = 0.0
            continue
        present = df[col].notna()
        if col in CATEGORICAL_LEVELS:
            present &= df[col] != UNKNOWN
        out[col] = round(float(present.mean()), 4)
    return out


# ---------------------------------------------------------------------------
# the registry
# ---------------------------------------------------------------------------
#: name -> (module, callable). Modules are imported lazily so a missing
#: optional dependency in one adapter cannot break the synthetic path.
SOURCES = {
    "synthetic": (None, None),
    "home_credit": ("app.sources.home_credit", "read"),
    "lending_club": ("app.sources.lending_club", "read"),
}


def load(source: str = "synthetic", **kwargs) -> pd.DataFrame:
    """Return a schema-checked applicant frame from any registered source.

    The frame carries its provenance on `df.attrs["source"]`: the source name,
    the row count, anything the adapter excluded and why, and the per-column
    coverage. Nothing downstream has to know which source it is looking at.
    """
    if source not in SOURCES:
        raise SchemaError(
            f"unknown source {source!r}. Registered sources: {', '.join(SOURCES)}."
        )

    if source == "synthetic":
        df = gen.generate(**kwargs)
        report = {"excluded": 0, "notes": ["Simulated by app/generate.py; drift schedule known."]}
    else:
        module_name, func_name = SOURCES[source]
        df, report = getattr(import_module(module_name), func_name)(**kwargs)

    check(df, source)
    df.attrs["source"] = {
        "name": source,
        "rows": int(len(df)),
        "months": int(df["month"].max()),
        "bad_rate": round(float(df["default"].mean()), 4),
        "coverage": coverage(df),
        **report,
    }
    return df
