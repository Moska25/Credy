"""Population-stability monitoring and the alert rules built on top of it.

The reference window is always the training months (1-12). Every later cohort
is compared back to it, feature by feature, so the numbers answer the operational
question: "does this month still look like the data the model was fitted on?"

Two views on purpose. PSI is what a credit risk function will ask for, but it is
unbounded and sensitive to empty bins. Jensen-Shannon divergence is bounded in
[0, 1] and better behaved in the tails, so it is a useful sanity check on any
PSI value that looks dramatic.

The thresholds below (0.10 / 0.25) are industry convention, not statistics.
They have no distributional justification; they are useful because everyone
reads them the same way. Treat them as a triage aid, not a test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import generate as gen

PSI_WATCH = 0.10
PSI_SHIFT = 0.25
SMOOTH = 1e-6

# Alert thresholds
SCORE_PSI_ALERT = 0.25
SLOPE_BAND = (0.80, 1.20)
AUC_FLOOR = 0.70
MISSINGNESS_JUMP = 0.10  # percentage points above the training reference
PD_GAP_ALERT = 0.25  # relative gap between observed bad rate and mean predicted PD


def bin_edges(reference: np.ndarray, bins: int = 10) -> np.ndarray:
    """Quantile edges from the reference sample, open at both ends."""
    ref = np.asarray(reference, dtype=np.float64)
    ref = ref[~np.isnan(ref)]
    if len(ref) == 0:
        return np.array([-np.inf, np.inf])
    inner = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1))[1:-1])
    return np.concatenate(([-np.inf], inner, [np.inf]))


def _shares(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    v = np.asarray(values, dtype=np.float64)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return np.full(len(edges) - 1, 1.0 / (len(edges) - 1))
    counts = np.histogram(v, bins=edges)[0].astype(np.float64)
    return counts / counts.sum()


def psi_from_shares(ref: np.ndarray, cur: np.ndarray) -> float:
    """PSI between two share vectors. Zero shares are smoothed, not dropped."""
    r = np.clip(np.asarray(ref, dtype=np.float64), SMOOTH, None)
    c = np.clip(np.asarray(cur, dtype=np.float64), SMOOTH, None)
    r = r / r.sum()
    c = c / c.sum()
    return float(np.sum((c - r) * np.log(c / r)))


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """PSI for a numeric feature. NaN is excluded; track it via `missingness`."""
    edges = bin_edges(reference, bins=bins)
    return psi_from_shares(_shares(reference, edges), _shares(current, edges))


def category_shares(labels, categories) -> np.ndarray:
    s = pd.Series(labels).value_counts()
    counts = np.array([float(s.get(c, 0)) for c in categories])
    total = counts.sum()
    return counts / total if total else np.full(len(categories), 1.0 / len(categories))


def psi_categorical(reference, current) -> float:
    cats = sorted(set(pd.Series(reference).dropna().unique()) | set(pd.Series(current).dropna().unique()))
    return psi_from_shares(category_shares(reference, cats), category_shares(current, cats))


def js_divergence(ref: np.ndarray, cur: np.ndarray) -> float:
    """Jensen-Shannon divergence in bits, bounded in [0, 1]."""
    r = np.clip(np.asarray(ref, dtype=np.float64), SMOOTH, None)
    c = np.clip(np.asarray(cur, dtype=np.float64), SMOOTH, None)
    r, c = r / r.sum(), c / c.sum()
    m = 0.5 * (r + c)
    kl = lambda a, b: float(np.sum(a * np.log2(a / b)))
    return 0.5 * kl(r, m) + 0.5 * kl(c, m)


def js_numeric(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    edges = bin_edges(reference, bins=bins)
    return js_divergence(_shares(reference, edges), _shares(current, edges))


def band(value: float) -> int:
    """0 = stable, 1 = watch, 2 = shifted. Conventional cut-points."""
    if value is None or not np.isfinite(value):
        return 0
    if value > PSI_SHIFT:
        return 2
    if value > PSI_WATCH:
        return 1
    return 0


BAND_LABEL = {0: "stable", 1: "watch", 2: "shifted"}
BAND_PILL = {0: "pill-pass", 1: "pill-warn", 2: "pill-fail"}


# ---------------------------------------------------------------------------
# Monthly tables
# ---------------------------------------------------------------------------
def feature_drift(df: pd.DataFrame, reference_months=gen.TRAIN_MONTHS) -> dict:
    """PSI and JS per feature per month, against the training reference."""
    lo, hi = reference_months
    ref = df[(df["month"] >= lo) & (df["month"] <= hi)]
    months = sorted(df["month"].unique().tolist())
    psi_rows, js_rows = {}, {}
    for feat in gen.FEATURES_ALL:
        is_cat = feat in gen.FEATURES_CATEGORICAL
        if is_cat:
            cats = sorted(df[feat].dropna().unique().tolist())
            ref_shares = category_shares(ref[feat], cats)
        else:
            edges = bin_edges(ref[feat].to_numpy(dtype=float))
            ref_shares = _shares(ref[feat].to_numpy(dtype=float), edges)
        p_by_month, j_by_month = {}, {}
        for m in months:
            cur = df.loc[df["month"] == m, feat]
            if is_cat:
                cur_shares = category_shares(cur, cats)
            else:
                cur_shares = _shares(cur.to_numpy(dtype=float), edges)
            p_by_month[m] = psi_from_shares(ref_shares, cur_shares)
            j_by_month[m] = js_divergence(ref_shares, cur_shares)
        psi_rows[feat] = p_by_month
        js_rows[feat] = j_by_month
    return {"months": months, "psi": psi_rows, "js": js_rows}


def score_drift(
    df: pd.DataFrame, scores: np.ndarray, reference_months=gen.TRAIN_MONTHS
) -> list[dict]:
    """PSI of the model's own output distribution - the single best early warning."""
    lo, hi = reference_months
    ref_mask = (df["month"] >= lo) & (df["month"] <= hi)
    ref = scores[ref_mask.to_numpy()]
    edges = bin_edges(ref)
    ref_shares = _shares(ref, edges)
    months = df["month"].to_numpy()
    out = []
    for m in sorted(np.unique(months).tolist()):
        cur = scores[months == m]
        cur_shares = _shares(cur, edges)
        value = psi_from_shares(ref_shares, cur_shares)
        out.append(
            {
                "month": int(m),
                "psi": value,
                "js": js_divergence(ref_shares, cur_shares),
                "mean_score": float(np.mean(cur)),
                "band": band(value),
            }
        )
    return out


def missingness(df: pd.DataFrame, reference_months=gen.TRAIN_MONTHS) -> dict:
    """Missing-rate per feature per month, plus the training reference rate."""
    lo, hi = reference_months
    ref = df[(df["month"] >= lo) & (df["month"] <= hi)]
    months = sorted(df["month"].unique().tolist())
    tracked = [c for c in gen.FEATURES_ALL if df[c].isna().any()]
    rates = {}
    reference = {}
    for feat in tracked:
        reference[feat] = float(ref[feat].isna().mean())
        rates[feat] = {m: float(df.loc[df["month"] == m, feat].isna().mean()) for m in months}
    return {"months": months, "features": tracked, "reference": reference, "rates": rates}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
def early_production_baseline(
    months: np.ndarray,
    y: np.ndarray,
    scores: np.ndarray,
    window: int = 3,
    n_boot: int = 500,
    seed: int = 17,
) -> dict:
    """Pooled AUC over the first few *out-of-sample* months.

    In-sample training months are the wrong yardstick for "has the model got
    worse" - they are flattering by construction. The first months in production
    are the right one, so decline is measured against them. Pooling the window
    matters: a single 1,700-row cohort has an interval too wide to detect
    anything against.
    """
    from . import evaluate as ev

    lo_m = gen.VAL_MONTHS[0]
    hi_m = lo_m + window - 1
    sel = (np.asarray(months) >= lo_m) & (np.asarray(months) <= hi_m)
    boot = ev.bootstrap_auc(np.asarray(y)[sel], np.asarray(scores)[sel], n_boot=n_boot, seed=seed)
    return {"months": [lo_m, hi_m], "auc": boot["auc"], "lo": boot["lo"], "hi": boot["hi"], "n": boot["n"]}


def alerts(
    score_psi: list[dict],
    monthly: list[dict],
    miss: dict,
    feature_psi: dict | None = None,
    first_monitored_month: int = gen.VAL_MONTHS[0],
    baseline: dict | None = None,
) -> list[dict]:
    """Turn the monitoring tables into things a human should act on.

    Each rule states the month, what tripped, the observed value against its
    threshold, and what to do. Only months after the training window are
    monitored - alerting on the reference period would be circular.
    """
    out = []
    by_month = {r["month"]: r for r in monthly}

    for row in score_psi:
        m = row["month"]
        if m < first_monitored_month:
            continue
        if row["psi"] > SCORE_PSI_ALERT:
            out.append(
                {
                    "month": m,
                    "rule": "score_psi",
                    "subject": "model score",
                    "value": row["psi"],
                    "threshold": SCORE_PSI_ALERT,
                    "severity": "high",
                    "message": f"Score distribution PSI {row['psi']:.3f} exceeds {SCORE_PSI_ALERT:.2f}",
                    "action": "Compare feature PSI to find the driver; hold new limit changes until the score is re-baselined.",
                }
            )

    for m, row in by_month.items():
        if m < first_monitored_month:
            continue
        slope = row.get("slope")
        if slope is not None and np.isfinite(slope) and not (SLOPE_BAND[0] <= slope <= SLOPE_BAND[1]):
            out.append(
                {
                    "month": m,
                    "rule": "calibration_slope",
                    "subject": "calibration",
                    "value": float(slope),
                    "threshold": SLOPE_BAND[1] if slope > SLOPE_BAND[1] else SLOPE_BAND[0],
                    "severity": "high",
                    "message": f"Calibration slope {slope:.2f} outside [{SLOPE_BAND[0]:.1f}, {SLOPE_BAND[1]:.1f}]",
                    "action": "Refit the Platt/isotonic layer on recent months before using PDs for pricing or provisioning.",
                }
            )
        predicted = row.get("mean_predicted")
        observed = row.get("bad_rate")
        if predicted:
            gap = (observed - predicted) / predicted
            if abs(gap) > PD_GAP_ALERT:
                direction = "under" if gap > 0 else "over"
                out.append(
                    {
                        "month": m,
                        "rule": "pd_gap",
                        "subject": "predicted level",
                        "value": float(gap),
                        "threshold": PD_GAP_ALERT,
                        "severity": "high",
                        "message": (
                            f"Observed bad rate {observed:.1%} vs mean predicted PD {predicted:.1%} "
                            f"- the model {direction}-predicts risk by {abs(gap):.0%}"
                        ),
                        "action": "Prior-probability shift: re-baseline the intercept before these PDs touch provisioning.",
                    }
                )
        hi = row.get("hi")
        lo = row.get("lo")
        if hi is not None and np.isfinite(hi) and hi < AUC_FLOOR:
            out.append(
                {
                    "month": m,
                    "rule": "auc_floor",
                    "subject": "discrimination",
                    "value": float(row["auc"]),
                    "threshold": AUC_FLOOR,
                    "severity": "high",
                    "message": f"AUC {row['auc']:.3f} with 95% CI upper bound {hi:.3f} below the {AUC_FLOOR:.2f} floor",
                    "action": "Escalate to model owner; the whole interval sits under the agreed floor.",
                }
            )
        elif lo is not None and np.isfinite(lo) and lo < AUC_FLOOR:
            out.append(
                {
                    "month": m,
                    "rule": "auc_floor",
                    "subject": "discrimination",
                    "value": float(row["auc"]),
                    "threshold": AUC_FLOOR,
                    "severity": "medium",
                    "message": f"AUC {row['auc']:.3f} CI [{lo:.3f}, {hi:.3f}] cannot rule out being below the {AUC_FLOOR:.2f} floor",
                    "action": "Watch; a single cohort of this size cannot settle it. Re-check next month.",
                }
            )

    if baseline:
        for m, row in by_month.items():
            if m <= baseline["months"][1]:
                continue
            hi = row.get("hi")
            if hi is not None and np.isfinite(hi) and hi < baseline["lo"]:
                out.append(
                    {
                        "month": m,
                        "rule": "auc_decline",
                        "subject": "discrimination",
                        "value": float(row["auc"]),
                        "threshold": float(baseline["lo"]),
                        "severity": "high",
                        "message": (
                            f"AUC {row['auc']:.3f} (CI upper {hi:.3f}) is below the early-production "
                            f"baseline of {baseline['auc']:.3f} from months "
                            f"{baseline['months'][0]}-{baseline['months'][1]}"
                        ),
                        "action": "Ranking has genuinely degraded, not just the level. Investigate concept drift before recalibrating - a new intercept will not fix it.",
                    }
                )

    for feat in miss["features"]:
        ref_rate = miss["reference"][feat]
        for m in miss["months"]:
            if m < first_monitored_month:
                continue
            rate = miss["rates"][feat][m]
            if rate - ref_rate > MISSINGNESS_JUMP:
                out.append(
                    {
                        "month": m,
                        "rule": "missingness_spike",
                        "subject": feat,
                        "value": rate,
                        "threshold": ref_rate + MISSINGNESS_JUMP,
                        "severity": "high",
                        "message": f"{feat} missing in {rate:.1%} of applications vs {ref_rate:.1%} in training",
                        "action": "Treat as an upstream data incident first; check the feed before blaming the model.",
                    }
                )

    if feature_psi:
        for feat, by_m in feature_psi["psi"].items():
            for m, value in by_m.items():
                if m < first_monitored_month or value <= PSI_WATCH:
                    continue
                shifted = value > PSI_SHIFT
                out.append(
                    {
                        "month": m,
                        "rule": "feature_psi",
                        "subject": feat,
                        "value": float(value),
                        "threshold": PSI_SHIFT if shifted else PSI_WATCH,
                        "severity": "high" if shifted else "medium",
                        "message": (
                            f"{feat} PSI {value:.3f} is in the "
                            f"{'shifted' if shifted else 'watch'} band "
                            f"(> {PSI_SHIFT if shifted else PSI_WATCH:.2f}) against the training reference"
                        ),
                        "action": "Confirm whether the input population genuinely changed or an upstream mapping broke.",
                    }
                )

    out.sort(key=lambda a: (a["month"], 0 if a["severity"] == "high" else 1, a["rule"]))
    return out


def verify_against_truth(fired: list[dict], truth: dict | None) -> dict:
    """Did the detectors catch the drift we planted, and in which month?

    This is the whole argument for a synthetic dataset: the expected month is
    known, so the alert table can be scored rather than admired.

    On a real source there is no known schedule, and the honest answer is not an
    empty table. It is a refusal: `{"verifiable": False, "reason": ...}`. A blank
    verification table reads as "nothing was injected", which on real data is an
    unfalsifiable claim rather than a result. Every caller must render the
    reason instead.
    """
    schedule = (truth or {}).get("schedule")
    if not schedule:
        return {
            "verifiable": False,
            "reason": (
                "No known drift schedule for this source. Detection lag and hit rate can only "
                "be scored against a population whose drift was planted at a known month. On "
                "real lending data nobody knows the true schedule, so a quiet month cannot be "
                "distinguished from an insensitive detector, and this table is withheld rather "
                "than shown empty."
            ),
            "rows": [],
        }
    expectations = [
        {
            "injected": "Covariate shift - income distribution slides down",
            "starts_month": schedule["covariate_shift"]["starts_month"],
            "enabled": truth["drift_switches"]["covariate_shift"],
            "detector": "feature PSI (income)",
            "match": lambda a: a["rule"] == "feature_psi" and a["subject"] == "income",
        },
        {
            "injected": "Prior shift - base default rate rises",
            "starts_month": schedule["prior_shift"]["starts_month"],
            "enabled": truth["drift_switches"]["prior_shift"],
            "detector": "predicted-vs-observed level gap / calibration slope",
            "match": lambda a: a["rule"] in ("pd_gap", "calibration_slope"),
        },
        {
            "injected": "Concept drift - broker channel effect flips sign",
            "starts_month": schedule["concept_drift"]["starts_month"],
            "enabled": truth["drift_switches"]["concept_drift"],
            "detector": "AUC decline vs early-production baseline",
            "match": lambda a: a["rule"] == "auc_decline",
        },
        {
            "injected": "Data-quality drift - employment_tenure feed degrades",
            "starts_month": schedule["quality_drift"]["starts_month"],
            "enabled": truth["drift_switches"]["quality_drift"],
            "detector": "missingness spike (employment_tenure)",
            "match": lambda a: a["rule"] == "missingness_spike" and a["subject"] == "employment_tenure",
        },
    ]
    rows = []
    for exp in expectations:
        hits = [a["month"] for a in fired if exp["match"](a)]
        first = min(hits) if hits else None
        rows.append(
            {
                "injected": exp["injected"],
                "enabled": exp["enabled"],
                "starts_month": exp["starts_month"],
                "detector": exp["detector"],
                "first_detected_month": first,
                "n_alerts": len(hits),
                "detected": first is not None,
                "lag_months": (first - exp["starts_month"]) if first is not None else None,
            }
        )
    return {"verifiable": True, "reason": "", "rows": rows}
