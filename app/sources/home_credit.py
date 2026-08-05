"""Home Credit Default Risk adapter.

Source: the Kaggle competition "Home Credit Default Risk", file
`application_train.csv` (about 308k rows). It is **not vendored into this
repository** and never will be: it is 166 MB, it is covered by the competition
rules, and a portfolio repo has no business shipping someone else's dataset.
See the README for where to obtain it.

Two honest notes about what this adapter can and cannot do.

**There is no application date.** Home Credit is anonymised by design. Every
time field in `application_train.csv` is a negative day offset relative to the
application itself (`DAYS_BIRTH`, `DAYS_EMPLOYED`, `DAYS_REGISTRATION`), so the
file contains no absolute calendar date and therefore no derivable cohort. This
matters more here than in most projects, because the entire repository is about
temporal validation: without a cohort index there is no temporal split, no
month-by-month PSI and no drift verification. Rather than invent a time axis by
sorting on `SK_ID_CURR` (which would be fabricating the one thing this project
claims to measure), the adapter requires `date_column` and raises a named error
when the extract has none.

**`DAYS_EMPLOYED` has a sentinel.** Roughly 18% of rows carry 365243, a
placeholder meaning "not employed" rather than a thousand years of tenure.
Feeding it in as a number moves the mean by two orders of magnitude. It is
mapped to 0 tenure with `employment_type = unemployed`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import UNKNOWN, SchemaError

#: Not employed. Kaggle's own discussion threads confirm it is a placeholder.
DAYS_EMPLOYED_SENTINEL = 365243

#: NAME_INCOME_TYPE -> the schema's employment_type. Anything absent from this
#: map is an unmapped level and must fail the schema check rather than pass
#: silently, so the mapping is exhaustive over the levels the file contains.
INCOME_TYPE = {
    "Working": "salaried",
    "State servant": "salaried",
    "Commercial associate": "salaried",
    "Businessman": "self_employed",
    "Maternity leave": "contract",
    "Student": "contract",
    "Pensioner": "retired",
    "Unemployed": "unemployed",
}

COLUMNS = [
    "SK_ID_CURR", "TARGET", "DAYS_BIRTH", "AMT_INCOME_TOTAL", "NAME_INCOME_TYPE",
    "DAYS_EMPLOYED", "AMT_ANNUITY", "AMT_CREDIT", "NAME_CONTRACT_TYPE",
]


def read(path: str, date_column: str | None = None, **kwargs) -> tuple[pd.DataFrame, dict]:
    """Map `application_train.csv` onto the applicant schema.

    `date_column` names a parseable application date. The public Kaggle file has
    none, so this argument is mandatory in practice and a dated extract has to
    supply it. Cohorts are numbered from the earliest calendar month present.
    """
    raw = pd.read_csv(path, **kwargs)

    missing = [c for c in COLUMNS if c not in raw.columns]
    if missing:
        raise SchemaError(
            f"home_credit: {path} does not look like application_train.csv; "
            f"missing {', '.join(missing)}."
        )

    if date_column is None or date_column not in raw.columns:
        raise SchemaError(
            "home_credit: no application date available. "
            f"{'The public Kaggle application_train.csv is anonymised: every time field is a ' if date_column is None else f'{date_column!r} is not a column in the file. '}"
            "negative day offset relative to the application, so there is no calendar date to "
            "build a cohort index from. Pass date_column=<name of a parseable date column> from "
            "a dated extract. This adapter will not fabricate a time axis by sorting on the id, "
            "because the temporal ordering is the thing this project measures."
        )

    dates = pd.to_datetime(raw[date_column], errors="coerce")
    usable = dates.notna()
    period = dates[usable].dt.to_period("M")
    month = (period - period.min()).apply(lambda p: p.n) + 1

    days_employed = raw.loc[usable, "DAYS_EMPLOYED"]
    not_employed = days_employed == DAYS_EMPLOYED_SENTINEL
    tenure = np.where(not_employed, 0.0, (-days_employed / 365.25).clip(lower=0.0))

    employment = raw.loc[usable, "NAME_INCOME_TYPE"].map(INCOME_TYPE).fillna(UNKNOWN)
    employment = employment.where(~not_employed, "unemployed")

    income = raw.loc[usable, "AMT_INCOME_TOTAL"].astype(float)
    annuity = raw.loc[usable, "AMT_ANNUITY"].astype(float)

    df = pd.DataFrame(
        {
            "applicant_id": raw.loc[usable, "SK_ID_CURR"].astype("int64").to_numpy(),
            "month": month.to_numpy(),
            # Cash loans amortise over roughly credit/annuity years; revolving
            # credit has no term, so it is left null rather than guessed.
            "term_months": np.where(
                raw.loc[usable, "NAME_CONTRACT_TYPE"].eq("Cash loans") & annuity.gt(0),
                (raw.loc[usable, "AMT_CREDIT"].astype(float) / annuity * 12).round(),
                np.nan,
            ),
            "age": (-raw.loc[usable, "DAYS_BIRTH"] / 365.25).to_numpy(),
            "income": income.to_numpy(),
            "employment_type": employment.to_numpy(),
            "employment_tenure": tenure,
            # Annuity over income is the file's closest analogue to a debt
            # service ratio. It is a different quantity from the generator's
            # debt_ratio and is labelled as such in the coverage report.
            "debt_ratio": (annuity / income).clip(0.0, 1.1).to_numpy(),
            "credit_history_years": np.nan,
            "prior_delinquencies": np.nan,
            "loan_amount": raw.loc[usable, "AMT_CREDIT"].astype(float).to_numpy(),
            # Region rating is an ordinal risk grade, not one of the schema's
            # named regions, and channel is not recorded at all.
            "region": UNKNOWN,
            "channel": UNKNOWN,
            "default": raw.loc[usable, "TARGET"].astype("int64").to_numpy(),
        }
    )
    df["debt_ratio"] = df["debt_ratio"].fillna(0.0)

    report = {
        "excluded": int((~usable).sum()),
        "notes": [
            f"Home Credit application_train.csv via {path}.",
            f"{int((~usable).sum())} row(s) dropped for an unparseable {date_column!r}.",
            f"{int(not_employed.sum())} row(s) had DAYS_EMPLOYED == {DAYS_EMPLOYED_SENTINEL}, "
            "the not-employed sentinel, mapped to 0 tenure and employment_type=unemployed.",
            "debt_ratio here is AMT_ANNUITY / AMT_INCOME_TOTAL, which is a payment-to-income "
            "ratio, not the generator's total debt service ratio.",
            "credit_history_years, prior_delinquencies, region and channel are not in this file "
            "and are left null or unknown.",
        ],
    }
    return df, report
