"""Lending Club adapter, with an explicit performance window.

Source: the public Lending Club accepted-loans extract (`accepted_*.csv`).
Not vendored; see the README for where to obtain it.

The whole point of this adapter is the exclusion rule, because getting it wrong
is the single most common error made on this dataset.

A loan issued three months ago and still `Current` has not defaulted **yet**.
Labelling it 0 mixes "did not default" with "has not had the chance to", which
biases the base rate downward, and biases it *more* for recent cohorts than old
ones. On a project about temporal drift that manufactures a fake downward trend
in the default rate: exactly the artefact the rest of this repository exists to
detect. So the rule is stated, applied, and the count it removes is reported:

    Keep a loan only if its outcome is already resolved (Fully Paid, Charged
    Off, Default), or if it has been observed for at least its full term.
    Everything else is excluded as immature, never labelled good.

`as_of` is the observation date the window is measured against. It defaults to
the latest issue date in the file plus the longest term, which keeps a run
reproducible from the file alone rather than from today's clock.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import UNKNOWN, SchemaError

#: loan_status -> resolved outcome. Anything not listed is unresolved and is
#: subject to the maturity rule.
RESOLVED = {
    "Fully Paid": 0,
    "Does not meet the credit policy. Status:Fully Paid": 0,
    "Charged Off": 1,
    "Default": 1,
    "Does not meet the credit policy. Status:Charged Off": 1,
}

#: home_ownership is the only employment-adjacent categorical in the file, and
#: it is not employment. Lending Club records `emp_length` (years) but not the
#: kind of employment, so employment_type is unknown for every row and the
#: coverage report says so.
COLUMNS = ["issue_d", "term", "loan_amnt", "annual_inc", "dti", "loan_status"]


def read(path: str, as_of: str | None = None, **kwargs) -> tuple[pd.DataFrame, dict]:
    """Map an accepted-loans extract onto the applicant schema."""
    raw = pd.read_csv(path, low_memory=False, **kwargs)

    missing = [c for c in COLUMNS if c not in raw.columns]
    if missing:
        raise SchemaError(
            f"lending_club: {path} does not look like an accepted-loans extract; "
            f"missing {', '.join(missing)}."
        )

    # Lending Club writes issue_d as "Jan-2015". Parsing with the known format
    # is vectorised; format="mixed" falls back to per-element parsing, which on
    # a 2.2M-row extract is the difference between a second and a minute.
    issued = pd.to_datetime(raw["issue_d"], format="%b-%Y", errors="coerce")
    if issued.isna().all():
        issued = pd.to_datetime(raw["issue_d"], format="mixed", errors="coerce")
    # " 36 months" -> 36
    term = pd.to_numeric(
        raw["term"].astype(str).str.extract(r"(\d+)", expand=False), errors="coerce"
    )

    parseable = issued.notna() & term.notna()
    observed_to = (
        pd.to_datetime(as_of)
        if as_of is not None
        else issued.max() + pd.DateOffset(months=int(term.max()))
    )

    status = raw["loan_status"].astype(str).str.strip()
    resolved = status.map(RESOLVED)

    # Maturity in whole months. issue_d carries no day of month, so month
    # arithmetic is both the vectorised form and the honest one. A plain
    # year*12+month ordinal keeps it as integers rather than Period objects.
    issue_ordinal = issued.dt.year * 12 + issued.dt.month
    observed_ordinal = observed_to.year * 12 + observed_to.month
    mature_enough = (issue_ordinal + term) <= observed_ordinal

    keep = parseable & (resolved.notna() | mature_enough)
    # A loan that is mature but still has no terminal status tells us nothing
    # usable either, so it goes too. Only a resolved outcome becomes a label.
    keep &= resolved.notna()

    n_unparseable = int((~parseable).sum())
    n_immature = int((parseable & resolved.isna() & ~mature_enough).sum())
    n_unresolved_mature = int((parseable & resolved.isna() & mature_enough).sum())

    sub = raw.loc[keep]
    kept_ordinal = issue_ordinal[keep]
    month = (kept_ordinal - kept_ordinal.min() + 1).astype("int64")

    income = pd.to_numeric(sub["annual_inc"], errors="coerce").astype(float)
    emp_years = pd.to_numeric(
        sub.get("emp_length", pd.Series(index=sub.index, dtype=object))
        .astype(str)
        .str.extract(r"(\d+)", expand=False),
        errors="coerce",
    )

    df = pd.DataFrame(
        {
            "applicant_id": (
                pd.to_numeric(sub["id"], errors="coerce")
                if "id" in sub.columns
                else pd.Series(np.arange(1, len(sub) + 1), index=sub.index)
            )
            .fillna(pd.Series(np.arange(1, len(sub) + 1), index=sub.index))
            .astype("int64")
            .to_numpy(),
            "month": month.to_numpy(),
            # Lending Club records no applicant age and no credit-file length
            # in this extract, and it is a consumer-lending dataset in a
            # jurisdiction where age is not collected for underwriting.
            "age": np.nan,
            "income": income.to_numpy(),
            "employment_type": UNKNOWN,
            "employment_tenure": emp_years.to_numpy(dtype=float),
            # dti is reported in percent.
            "debt_ratio": (
                pd.to_numeric(sub["dti"], errors="coerce").astype(float) / 100.0
            ).clip(0.0, 1.1).fillna(0.0).to_numpy(),
            "credit_history_years": np.nan,
            "prior_delinquencies": pd.to_numeric(
                sub.get("delinq_2yrs", np.nan), errors="coerce"
            ).to_numpy(dtype=float),
            "loan_amount": pd.to_numeric(sub["loan_amnt"], errors="coerce")
            .astype(float)
            .to_numpy(),
            "term_months": term[keep].to_numpy(dtype=float),
            "region": UNKNOWN,
            "channel": UNKNOWN,
            "default": resolved[keep].astype("int64").to_numpy(),
        }
    )

    report = {
        "excluded": n_unparseable + n_immature + n_unresolved_mature,
        "notes": [
            f"Lending Club accepted-loans extract via {path}.",
            f"Observation date {observed_to.date()}"
            + (" (supplied)" if as_of else " (latest issue date plus the longest term)."),
            f"{n_immature} loan(s) excluded as immature: issued too recently to have completed "
            "their term and not yet resolved. They are excluded, never labelled good.",
            f"{n_unresolved_mature} matured loan(s) excluded for having no terminal status.",
            f"{n_unparseable} row(s) excluded for an unparseable issue_d or term.",
            "age, credit_history_years, region and channel are absent from this extract; "
            "employment_type is unknown because the file records tenure but not employment kind.",
        ],
    }
    return df, report
