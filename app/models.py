"""Feature engineering, the three models, and the split strategies.

Three candidates, deliberately including a non-ML baseline that a credit risk
team would actually recognise:

1. `scorecard`  - hand-built points table, no learning beyond a 1-D calibration
                  of points to probability on the training months.
2. `logistic`   - median-imputed, standardised logistic regression with explicit
                  missing indicators.
3. `hgb`        - HistGradientBoostingClassifier, which consumes NaN natively.

And two ways of splitting the same 40k rows:

* `temporal_split` - months 1-12 train, 13-18 validation, 19-24 test. Honest.
* `random_split`   - the same row counts drawn at random. Dishonest, and that is
                     the point: the gap between the two is the headline result.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import generate as gen

# Reference levels are dropped from the one-hot block so the coefficients line
# up with the DGP offsets, which are also relative to these levels.
EMPLOYMENT_LEVELS = ["self_employed", "contract", "retired", "unemployed"]
REGION_LEVELS = ["north", "east", "west", "central"]
CHANNEL_LEVELS = ["online", "broker", "partner"]

NUMERIC_COLUMNS = [
    "z_age",
    "z_log_income",
    "z_tenure",
    "debt_ratio",
    "z_credit_history",
    "prior_delinquencies",
    "log_loan_amount",
    "z_term",
    "loan_to_income",
]
INDICATOR_COLUMNS = ["missing_income", "missing_employment_tenure", "missing_credit_history"]

FEATURE_NAMES = (
    NUMERIC_COLUMNS
    + INDICATOR_COLUMNS
    + [f"employment_type={v}" for v in EMPLOYMENT_LEVELS]
    + [f"region={v}" for v in REGION_LEVELS]
    + [f"channel={v}" for v in CHANNEL_LEVELS]
)

MODEL_LABELS = {
    "scorecard": "Points scorecard",
    "logistic": "Logistic regression",
    "hgb": "Gradient boosting",
}


def design_matrix(df: pd.DataFrame) -> np.ndarray:
    """Numeric design matrix. NaN is preserved (HGB uses it, LR imputes it).

    Numerics are pre-centred with the same constants the DGP uses, so a fitted
    standardised logistic coefficient is directly comparable to the true one.
    """
    income = df["income"].to_numpy(dtype=float)
    loan = df["loan_amount"].to_numpy(dtype=float)
    cols = {
        "z_age": (df["age"].to_numpy(dtype=float) - 40.0) / 12.0,
        "z_log_income": (np.log(income) - 10.70) / 0.45,
        "z_tenure": (df["employment_tenure"].to_numpy(dtype=float) - 6.0) / 5.0,
        "debt_ratio": df["debt_ratio"].to_numpy(dtype=float),
        "z_credit_history": (df["credit_history_years"].to_numpy(dtype=float) - 8.0) / 5.0,
        "prior_delinquencies": df["prior_delinquencies"].to_numpy(dtype=float),
        "log_loan_amount": np.log(loan),
        "z_term": (df["term_months"].to_numpy(dtype=float) - 36.0) / 16.0,
        "loan_to_income": loan / income,
        "missing_income": df["income"].isna().to_numpy(dtype=float),
        "missing_employment_tenure": df["employment_tenure"].isna().to_numpy(dtype=float),
        "missing_credit_history": df["credit_history_years"].isna().to_numpy(dtype=float),
    }
    for level in EMPLOYMENT_LEVELS:
        cols[f"employment_type={level}"] = (df["employment_type"] == level).to_numpy(dtype=float)
    for level in REGION_LEVELS:
        cols[f"region={level}"] = (df["region"] == level).to_numpy(dtype=float)
    for level in CHANNEL_LEVELS:
        cols[f"channel={level}"] = (df["channel"] == level).to_numpy(dtype=float)
    return np.column_stack([cols[name] for name in FEATURE_NAMES])


# ---------------------------------------------------------------------------
# Baseline: a transparent points scorecard
# ---------------------------------------------------------------------------
# Bands and points are hand-set from ordinary underwriting reasoning, never
# tuned against the test months. Higher points = higher assessed risk.
SCORECARD_RULES = [
    ("debt_ratio", [(0.20, 0), (0.35, 8), (0.50, 18), (0.70, 30), (9e9, 42)]),
    ("prior_delinquencies", [(0.5, 0), (1.5, 14), (2.5, 26), (9e9, 40)]),
    ("credit_history_years", [(2, 22), (5, 14), (10, 6), (9e9, 0)]),
    ("loan_to_income", [(0.20, 0), (0.40, 7), (0.75, 16), (9e9, 26)]),
    ("age", [(25, 10), (35, 4), (55, 0), (9e9, 3)]),
]
SCORECARD_EMPLOYMENT_POINTS = {
    "salaried": 0,
    "contract": 7,
    "self_employed": 11,
    "retired": 0,
    "unemployed": 22,
}
SCORECARD_MISSING_POINTS = {"income": 12, "credit_history_years": 15}


def scorecard_points(df: pd.DataFrame) -> np.ndarray:
    """Sum the points table. Missing values score the documented penalty."""
    n = len(df)
    lti = (df["loan_amount"] / df["income"]).to_numpy(dtype=float)
    values = {
        "debt_ratio": df["debt_ratio"].to_numpy(dtype=float),
        "prior_delinquencies": df["prior_delinquencies"].to_numpy(dtype=float),
        "credit_history_years": df["credit_history_years"].to_numpy(dtype=float),
        "loan_to_income": lti,
        "age": df["age"].to_numpy(dtype=float),
    }
    points = np.zeros(n)
    for name, bands in SCORECARD_RULES:
        v = values[name]
        band_points = np.full(n, float(bands[-1][1]))
        assigned = np.zeros(n, dtype=bool)
        for edge, pts in bands:
            take = (~assigned) & (v < edge)
            band_points[take] = pts
            assigned |= take
        band_points[np.isnan(v)] = 0.0  # penalty handled below, not double-counted
        points += band_points
    points += df["employment_type"].map(SCORECARD_EMPLOYMENT_POINTS).to_numpy(dtype=float)
    points += df["income"].isna().to_numpy(dtype=float) * SCORECARD_MISSING_POINTS["income"]
    points += (
        df["credit_history_years"].isna().to_numpy(dtype=float)
        * SCORECARD_MISSING_POINTS["credit_history_years"]
    )
    return points


class Scorecard:
    """Points table plus a 1-D logistic map from points to probability.

    The map is fitted on the training months only; the points themselves are
    fixed constants, so this stays a transparent baseline rather than a model
    that quietly learned the answer.
    """

    def __init__(self) -> None:
        self._lr = LogisticRegression()

    def fit(self, df: pd.DataFrame, y: np.ndarray) -> "Scorecard":
        self._lr.fit(scorecard_points(df).reshape(-1, 1) / 100.0, y)
        return self

    def predict_proba1(self, df: pd.DataFrame) -> np.ndarray:
        return self._lr.predict_proba(scorecard_points(df).reshape(-1, 1) / 100.0)[:, 1]


def fit_logistic(X: np.ndarray, y: np.ndarray) -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("lr", LogisticRegression(max_iter=2000, C=1.0)),
        ]
    ).fit(X, y)


def fit_hgb(X: np.ndarray, y: np.ndarray) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=180,
        learning_rate=0.05,
        max_leaf_nodes=12,
        min_samples_leaf=150,
        l2_regularization=3.0,
        # Early stopping on a random 15% slice of the *training months* only.
        # Deterministic given random_state, and it keeps the in-sample AUC from
        # inflating to the point where the month-by-month chart is misleading.
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=15,
        random_state=0,
    ).fit(X, y)


def logistic_coefficients(pipe: Pipeline) -> dict[str, float]:
    """Coefficients rescaled back into design-matrix units.

    The pipeline standardises internally, so `coef_` is per standard deviation.
    Dividing by the scaler's sd puts them back on the same scale the DGP uses,
    which makes an estimated-vs-true comparison meaningful rather than decorative.
    """
    scale = pipe.named_steps["scale"].scale_
    coefs = pipe.named_steps["lr"].coef_[0] / scale
    return dict(zip(FEATURE_NAMES, coefs.tolist()))


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------
def temporal_split(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Positional index arrays for the strictly time-ordered split."""
    m = df["month"].to_numpy()
    lo, hi = gen.TRAIN_MONTHS
    vlo, vhi = gen.VAL_MONTHS
    tlo, thi = gen.TEST_MONTHS
    return {
        "train": np.flatnonzero((m >= lo) & (m <= hi)),
        "validation": np.flatnonzero((m >= vlo) & (m <= vhi)),
        "test": np.flatnonzero((m >= tlo) & (m <= thi)),
    }


def random_split(df: pd.DataFrame, sizes: dict[str, int], seed: int = 11) -> dict[str, np.ndarray]:
    """Same row counts as the temporal split, drawn uniformly at random.

    This is the split a careless notebook produces: rows from month 24 sit in
    the training set, so the model is scored on a period it has already seen.
    """
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(df))
    a, b = sizes["train"], sizes["train"] + sizes["validation"]
    return {
        "train": np.sort(order[:a]),
        "validation": np.sort(order[a:b]),
        "test": np.sort(order[b : b + sizes["test"]]),
    }


def fit_all(df: pd.DataFrame, train_idx: np.ndarray) -> dict[str, object]:
    """Fit all three candidates on one training index. Returns fitted objects."""
    X = design_matrix(df)
    y = df["default"].to_numpy()
    return {
        "scorecard": Scorecard().fit(df.iloc[train_idx], y[train_idx]),
        "logistic": fit_logistic(X[train_idx], y[train_idx]),
        "hgb": fit_hgb(X[train_idx], y[train_idx]),
    }


def predict_all(models: dict[str, object], df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Predicted default probability for every row, for every fitted model."""
    X = design_matrix(df)
    out = {"scorecard": models["scorecard"].predict_proba1(df)}
    for name in ("logistic", "hgb"):
        out[name] = models[name].predict_proba(X)[:, 1]
    return out
