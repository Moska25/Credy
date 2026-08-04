"""Synthetic credit applicant generator with a fully documented data-generating
process (DGP) and four independently switchable forms of temporal drift.

Everything here is fiction. The point of writing the DGP by hand is that the
ground truth is known: we can inject a specific covariate shift in a specific
month and then check that the drift detectors in `drift.py` actually fire on it.
A real lending dataset cannot prove that, because nobody knows what its true
drift was.

The DGP, in one line:

    logit(P(default)) = b0(month) + sum_j beta_j * f_j(applicant)

with beta on standardised numeric features so the coefficients are directly
comparable to the standardised logistic regression fitted in `models.py`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_MONTHS = 24
TRAIN_MONTHS = (1, 12)
VAL_MONTHS = (13, 18)
TEST_MONTHS = (19, 24)

EMPLOYMENT = ["salaried", "self_employed", "contract", "retired", "unemployed"]
EMPLOYMENT_P = [0.52, 0.16, 0.18, 0.09, 0.05]
REGIONS = ["north", "south", "east", "west", "central"]
REGION_P = [0.24, 0.22, 0.19, 0.20, 0.15]
CHANNELS = ["branch", "online", "broker", "partner"]
CHANNEL_P = [0.34, 0.31, 0.20, 0.15]
TERMS = [12, 24, 36, 48, 60]

# ---------------------------------------------------------------------------
# True coefficients. Numeric features enter as z-scores (see `_true_logit`),
# categoricals as additive offsets against the reference level.
# ---------------------------------------------------------------------------
COEF = {
    "intercept": -4.05,
    "z_age": -0.18,
    "z_income": -0.55,
    "debt_ratio": 1.25,
    "z_credit_history": -0.30,
    "prior_delinquencies": 0.42,
    "loan_to_income": 0.65,
    "z_term": 0.15,
    "z_tenure": -0.12,
    "missing_income": 0.45,
    "missing_credit_history": 0.55,
}
EMPLOYMENT_COEF = {
    "salaried": 0.00,
    "self_employed": 0.35,
    "contract": 0.22,
    "retired": -0.10,
    "unemployed": 0.75,
}
REGION_COEF = {"north": -0.08, "south": 0.00, "east": 0.12, "west": 0.05, "central": -0.03}
# `broker` is the concept-drift carrier; see `broker_coef`.
CHANNEL_COEF = {"branch": 0.00, "online": 0.10, "broker": -0.30, "partner": 0.18}

# Employment type also shifts the income level (log scale).
EMPLOYMENT_INCOME = {
    "salaried": 0.05,
    "self_employed": 0.00,
    "contract": -0.10,
    "retired": -0.25,
    "unemployed": -0.60,
}

# Correlation structure of the latent factors [age, income, debt, history].
LATENT_CORR = np.array(
    [
        [1.00, 0.25, -0.10, 0.55],
        [0.25, 1.00, -0.35, 0.15],
        [-0.10, -0.35, 1.00, -0.08],
        [0.55, 0.15, -0.08, 1.00],
    ]
)

DRIFT_ALL_ON = {
    "covariate_shift": True,
    "prior_shift": True,
    "concept_drift": True,
    "quality_drift": True,
}
DRIFT_ALL_OFF = {k: False for k in DRIFT_ALL_ON}

# --- drift schedule constants (documented in README / /data) ----------------
# The business story behind all four: an issuer chasing volume in year two.
# Applicants get poorer (a), the book gets riskier (b), the broker panel is
# opened up so broker volume grows (a) while broker quality collapses (c), and
# an upstream HR feed starts dropping employment tenure (d).
COVARIATE_START = 13  # month the income distribution starts sliding down
COVARIATE_MAX_LOG_SHIFT = -0.30  # log-income shift reached at month 24
BROKER_SHARE_MAX_GAIN = 0.18  # broker mix 0.20 -> 0.38, taken from `online`
PRIOR_START = 13
PRIOR_MAX_INTERCEPT_SHIFT = 0.40  # logit units added to b0 by month 24
CONCEPT_START = 17  # month the broker coefficient starts moving
CONCEPT_END_COEF = 1.40  # broker coefficient at month 24 (was -0.30)
QUALITY_START = 22  # month employment-tenure missingness spikes
TENURE_MISSING_BASE = 0.03
TENURE_MISSING_SPIKE = 0.30


def _ramp(month: int, start: int, end: int) -> float:
    """0 before `start`, 1 at `end`, linear in between."""
    if month <= start:
        return 0.0
    if month >= end:
        return 1.0
    return (month - start) / (end - start)


def income_log_shift(month: int, drift: dict) -> float:
    """Covariate shift (a): mean log-income slides down over the second year."""
    if not drift.get("covariate_shift"):
        return 0.0
    return COVARIATE_MAX_LOG_SHIFT * _ramp(month, COVARIATE_START - 1, N_MONTHS)


def channel_probs(month: int, drift: dict) -> list[float]:
    """Covariate shift (a), second signature: the broker channel mix grows.

    Marginal distribution of an input only - this changes P(x), not P(y|x).
    The change to P(y|x) lives in `broker_coef` and switches independently.
    """
    probs = dict(zip(CHANNELS, CHANNEL_P))
    if drift.get("covariate_shift"):
        gain = BROKER_SHARE_MAX_GAIN * _ramp(month, COVARIATE_START - 1, N_MONTHS)
        probs["broker"] += gain
        probs["online"] -= gain
    return [probs[c] for c in CHANNELS]


def intercept_shift(month: int, drift: dict) -> float:
    """Prior-probability shift (b): the base default rate rises."""
    if not drift.get("prior_shift"):
        return 0.0
    return PRIOR_MAX_INTERCEPT_SHIFT * _ramp(month, PRIOR_START - 1, N_MONTHS)


def broker_coef(month: int, drift: dict) -> float:
    """Concept drift (c): the broker channel's true effect flips sign.

    Story: a broker panel that used to be well-screened is opened up mid-window,
    so the same observable feature value now means something different about risk.
    """
    base = CHANNEL_COEF["broker"]
    if not drift.get("concept_drift"):
        return base
    return base + (CONCEPT_END_COEF - base) * _ramp(month, CONCEPT_START - 1, N_MONTHS)


def tenure_missing_rate(month: int, drift: dict) -> float:
    """Data-quality drift (d): an upstream feed starts dropping the field."""
    if drift.get("quality_drift") and month >= QUALITY_START:
        return TENURE_MISSING_SPIKE
    return TENURE_MISSING_BASE


def _true_logit(f: dict, month: int, drift: dict) -> np.ndarray:
    """The DGP itself. `f` holds latent (pre-masking) feature values."""
    logit = np.full(len(f["age"]), COEF["intercept"] + intercept_shift(month, drift))
    logit += COEF["z_age"] * ((f["age"] - 40.0) / 12.0)
    logit += COEF["z_income"] * ((np.log(f["income"]) - 10.70) / 0.45)
    logit += COEF["debt_ratio"] * f["debt_ratio"]
    logit += COEF["z_credit_history"] * ((f["credit_history_years"] - 8.0) / 5.0)
    logit += COEF["prior_delinquencies"] * f["prior_delinquencies"]
    logit += COEF["loan_to_income"] * f["loan_to_income"]
    logit += COEF["z_term"] * ((f["term_months"] - 36.0) / 16.0)
    logit += COEF["z_tenure"] * ((f["employment_tenure"] - 6.0) / 5.0)
    logit += np.vectorize(EMPLOYMENT_COEF.get)(f["employment_type"]).astype(float)
    logit += np.vectorize(REGION_COEF.get)(f["region"]).astype(float)

    chan = np.vectorize(CHANNEL_COEF.get)(f["channel"]).astype(float)
    chan = np.where(f["channel"] == "broker", broker_coef(month, drift), chan)
    logit += chan

    # Informative missingness: the *fact* of a missing field carries risk.
    logit += COEF["missing_income"] * f["income_missing"]
    logit += COEF["missing_credit_history"] * f["credit_history_missing"]
    return logit


def _month_frame(month: int, n: int, rng: np.random.Generator, drift: dict) -> pd.DataFrame:
    chol = np.linalg.cholesky(LATENT_CORR)
    z = rng.standard_normal((n, 4)) @ chol.T
    z_age, z_inc, z_debt, z_hist = z[:, 0], z[:, 1], z[:, 2], z[:, 3]

    # Round age here, not at storage time: everything downstream (credit history
    # cap, the true logit) must be derived from the value the model will see, or
    # the stored data can violate its own documented constraints.
    age = np.round(np.clip(40.0 + 12.0 * z_age, 18, 78))
    employment_type = rng.choice(EMPLOYMENT, size=n, p=EMPLOYMENT_P)
    region = rng.choice(REGIONS, size=n, p=REGION_P)
    channel = rng.choice(CHANNELS, size=n, p=channel_probs(month, drift))

    emp_inc = np.vectorize(EMPLOYMENT_INCOME.get)(employment_type).astype(float)
    log_income = 10.70 + 0.45 * z_inc + emp_inc + income_log_shift(month, drift)
    income = np.exp(log_income)

    debt_ratio = np.clip(0.28 + 0.14 * z_debt, 0.01, 1.10)

    max_hist = np.maximum(age - 18.0, 0.0)
    credit_history_years = np.clip(np.round(0.35 * (age - 18.0) + 3.0 * z_hist), 0.0, max_hist)

    tenure = np.clip(np.round(np.exp(1.4 + 0.55 * rng.standard_normal(n)) * (0.4 + 0.02 * (age - 18))), 0, 40)
    tenure = np.where(employment_type == "unemployed", 0.0, tenure)

    lam = 0.22 * np.exp(0.9 * debt_ratio - 0.25 * z_hist)
    prior_delinquencies = np.clip(rng.poisson(lam), 0, 6).astype(float)

    loan_to_income = np.clip(np.exp(-1.10 + 0.45 * rng.standard_normal(n)), 0.05, 3.0)
    loan_amount = np.round(income * loan_to_income, -2)
    term_idx = np.clip(np.digitize(loan_to_income, [0.15, 0.30, 0.55, 0.90]), 0, 4)
    term_months = np.array(TERMS, dtype=float)[term_idx]

    # --- missingness -------------------------------------------------------
    # Income missing more often for self-employed / unemployed applicants
    # (MAR on employment type) and carries its own risk coefficient.
    p_income_missing = np.where(
        np.isin(employment_type, ["self_employed", "unemployed"]), 0.11, 0.025
    )
    income_missing = rng.random(n) < p_income_missing
    # Thin-file applicants: no usable credit history.
    p_hist_missing = np.clip(0.16 - 0.012 * credit_history_years, 0.01, 0.35)
    credit_history_missing = rng.random(n) < p_hist_missing
    tenure_missing = rng.random(n) < tenure_missing_rate(month, drift)

    latent = {
        "age": age,
        "income": income,
        "debt_ratio": debt_ratio,
        "credit_history_years": credit_history_years,
        "prior_delinquencies": prior_delinquencies,
        "loan_to_income": loan_to_income,
        "term_months": term_months,
        "employment_tenure": tenure,
        "employment_type": employment_type,
        "region": region,
        "channel": channel,
        "income_missing": income_missing.astype(float),
        "credit_history_missing": credit_history_missing.astype(float),
    }
    logit = _true_logit(latent, month, drift)
    true_pd = 1.0 / (1.0 + np.exp(-logit))
    default = (rng.random(n) < true_pd).astype(int)

    return pd.DataFrame(
        {
            "month": month,
            "age": age,
            "income": np.where(income_missing, np.nan, np.round(income, -2)),
            "employment_type": employment_type,
            "employment_tenure": np.where(tenure_missing, np.nan, tenure),
            "debt_ratio": debt_ratio.round(4),
            "credit_history_years": np.where(credit_history_missing, np.nan, credit_history_years),
            "prior_delinquencies": prior_delinquencies,
            "loan_amount": loan_amount,
            "term_months": term_months,
            "region": region,
            "channel": channel,
            "true_pd": true_pd,
            "default": default,
        }
    )


def generate(n: int = 40_000, seed: int = 7, drift: dict | None = None) -> pd.DataFrame:
    """Generate `n` applicants spread over `N_MONTHS` monthly cohorts.

    Deterministic: the same (n, seed, drift) always returns the identical frame.
    """
    drift = dict(DRIFT_ALL_ON if drift is None else drift)
    rng = np.random.default_rng(seed)
    base, extra = divmod(n, N_MONTHS)
    counts = [base + (1 if i < extra else 0) for i in range(N_MONTHS)]
    frames = [_month_frame(m, counts[m - 1], rng, drift) for m in range(1, N_MONTHS + 1)]
    df = pd.concat(frames, ignore_index=True)
    df.insert(0, "applicant_id", np.arange(1, len(df) + 1))
    return df


def dgp_truth(drift: dict | None = None) -> dict:
    """Serialisable record of the true parameters, for estimated-vs-true tables."""
    drift = dict(DRIFT_ALL_ON if drift is None else drift)
    return {
        "drift_switches": drift,
        "coefficients": COEF,
        "employment_coef": EMPLOYMENT_COEF,
        "region_coef": REGION_COEF,
        "channel_coef": CHANNEL_COEF,
        "schedule": {
            "covariate_shift": {
                "feature": "income (level) and channel (mix)",
                "starts_month": COVARIATE_START,
                "log_shift_at_month_24": COVARIATE_MAX_LOG_SHIFT,
                "broker_share_month_1": CHANNEL_P[CHANNELS.index("broker")],
                "broker_share_month_24": channel_probs(N_MONTHS, drift)[CHANNELS.index("broker")],
                "per_month": {m: round(income_log_shift(m, drift), 4) for m in range(1, N_MONTHS + 1)},
                "broker_share_per_month": {
                    m: round(channel_probs(m, drift)[CHANNELS.index("broker")], 4)
                    for m in range(1, N_MONTHS + 1)
                },
            },
            "prior_shift": {
                "target": "intercept b0",
                "starts_month": PRIOR_START,
                "shift_at_month_24": PRIOR_MAX_INTERCEPT_SHIFT,
                "per_month": {m: round(intercept_shift(m, drift), 4) for m in range(1, N_MONTHS + 1)},
            },
            "concept_drift": {
                "feature": "channel=broker",
                "starts_month": CONCEPT_START,
                "coef_month_1": CHANNEL_COEF["broker"],
                "coef_month_24": broker_coef(N_MONTHS, drift),
                "per_month": {m: round(broker_coef(m, drift), 4) for m in range(1, N_MONTHS + 1)},
            },
            "quality_drift": {
                "feature": "employment_tenure",
                "starts_month": QUALITY_START,
                "missing_rate_before": TENURE_MISSING_BASE,
                "missing_rate_after": TENURE_MISSING_SPIKE,
                "per_month": {m: tenure_missing_rate(m, drift) for m in range(1, N_MONTHS + 1)},
            },
        },
        "splits": {"train": TRAIN_MONTHS, "validation": VAL_MONTHS, "test": TEST_MONTHS},
    }


DATA_DICTIONARY = [
    ("applicant_id", "integer", "Surrogate key, 1..N in generation order.", "-"),
    ("month", "integer 1-24", "Application cohort month. 1-12 train, 13-18 validation, 19-24 test.", "-"),
    ("age", "years, 18-78", "Clipped normal, mean 40, sd 12.", "never"),
    ("income", "currency / year", "Lognormal; mean shifts down from month 13 (covariate drift).", "2.5% / 11% (self-employed, unemployed)"),
    ("employment_type", "5 categories", "salaried, self_employed, contract, retired, unemployed.", "never"),
    ("employment_tenure", "years, 0-40", "Years in current employment; 0 for unemployed.", "3% -> 30% from month 22 (quality drift)"),
    ("debt_ratio", "ratio 0.01-1.10", "Existing debt service over income. Negatively correlated with income.", "never"),
    ("credit_history_years", "years", "Length of usable credit file, capped at age-18.", "1-35%, higher for thin files"),
    ("prior_delinquencies", "count 0-6", "Poisson, rate rises with debt ratio and falls with history length.", "never"),
    ("loan_amount", "currency", "income x loan-to-income ratio, rounded to 100.", "never"),
    ("term_months", "12/24/36/48/60", "Assigned by loan-to-income band.", "never"),
    ("region", "5 categories", "north, south, east, west, central.", "never"),
    ("channel", "4 categories", "branch, online, broker, partner. Broker effect flips sign from month 17.", "never"),
    ("true_pd", "probability", "The DGP's true default probability. Never used as a model feature.", "never"),
    ("default", "0/1", "Bernoulli draw from true_pd. The label.", "never"),
]

FEATURES_NUMERIC = [
    "age",
    "income",
    "employment_tenure",
    "debt_ratio",
    "credit_history_years",
    "prior_delinquencies",
    "loan_amount",
    "term_months",
]
FEATURES_CATEGORICAL = ["employment_type", "region", "channel"]
FEATURES_ALL = FEATURES_NUMERIC + FEATURES_CATEGORICAL
