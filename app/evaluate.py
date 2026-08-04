"""Discrimination, calibration and uncertainty.

Two opinions are baked in here:

* A point estimate of AUC without an interval is close to useless when you are
  about to claim one model beat another, so `bootstrap_auc` is the primary
  entry point and every headline number on the site carries an interval.
* Calibration is a separate question from ranking. A model can rank perfectly
  and still price every loan wrong, so slope/intercept and the reliability
  curve are treated as first-class metrics rather than a footnote.

The bootstrap is vectorised: instead of resampling indices B times and calling
roc_auc_score in a Python loop, we draw multinomial weights over the rows
(exactly the with-replacement bootstrap) and evaluate all replicates with a few
array operations. That keeps the whole seed step well under a minute.
"""

from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

EPS = 1e-6
DEFAULT_BOOTSTRAP = 500
REJECT_RATES = [0.05, 0.10, 0.20, 0.30]


# ---------------------------------------------------------------------------
# Discrimination
# ---------------------------------------------------------------------------
def _sorted_groups(y: np.ndarray, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(s, kind="mergesort")
    ys = y[order].astype(np.float64)
    ss = np.asarray(s, dtype=np.float64)[order]
    starts = np.flatnonzero(np.concatenate(([True], ss[1:] != ss[:-1])))
    return ys, starts


def _auc_weighted(ys: np.ndarray, starts: np.ndarray, w: np.ndarray) -> np.ndarray:
    """AUC with per-row weights, tie-corrected. `w` may be 1-D or (B, n)."""
    pos = w * ys
    neg = w - pos
    pg = np.add.reduceat(pos, starts, axis=-1)
    ng = np.add.reduceat(neg, starts, axis=-1)
    p_tot = pg.sum(axis=-1)
    n_tot = ng.sum(axis=-1)
    above = p_tot[..., None] - np.cumsum(pg, axis=-1)
    num = (ng * (above + 0.5 * pg)).sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / (p_tot * n_tot)


def auc(y: np.ndarray, s: np.ndarray) -> float:
    """Area under the ROC curve. Matches sklearn.roc_auc_score, ties included."""
    y = np.asarray(y, dtype=np.float64)
    if y.sum() == 0 or y.sum() == len(y):
        return float("nan")
    ys, starts = _sorted_groups(y, np.asarray(s, dtype=np.float64))
    return float(_auc_weighted(ys, starts, np.ones(len(ys))))


def gini(y: np.ndarray, s: np.ndarray) -> float:
    return 2.0 * auc(y, s) - 1.0


def ks(y: np.ndarray, s: np.ndarray) -> float:
    """Kolmogorov-Smirnov: max gap between the good and bad score CDFs."""
    y = np.asarray(y, dtype=np.float64)
    order = np.argsort(np.asarray(s, dtype=np.float64), kind="mergesort")
    ys = y[order]
    cum_bad = np.cumsum(ys) / max(ys.sum(), 1.0)
    cum_good = np.cumsum(1.0 - ys) / max((1.0 - ys).sum(), 1.0)
    return float(np.max(np.abs(cum_bad - cum_good)))


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=np.float64), EPS, 1 - EPS)
    y = np.asarray(y, dtype=np.float64)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=np.float64) - np.asarray(y, dtype=np.float64)) ** 2))


def bootstrap_auc(
    y: np.ndarray,
    s: np.ndarray,
    n_boot: int = DEFAULT_BOOTSTRAP,
    seed: int = 3,
    alpha: float = 0.05,
    chunk: int = 100,
) -> dict:
    """Percentile bootstrap interval for AUC (and the implied Gini).

    Resampling is over rows with replacement, which is the right unit here: the
    applicants are independent draws. The interval says nothing about whether
    the *next* cohort looks like this one - that is what the drift page is for.
    """
    y = np.asarray(y, dtype=np.float64)
    s = np.asarray(s, dtype=np.float64)
    point = auc(y, s)
    n = len(y)
    if not np.isfinite(point) or n < 30:
        return {"auc": point, "lo": float("nan"), "hi": float("nan"), "n": int(n),
                "gini": 2 * point - 1, "gini_lo": float("nan"), "gini_hi": float("nan"),
                "n_boot": 0}
    ys, starts = _sorted_groups(y, s)
    rng = np.random.default_rng(seed)
    pvals = np.full(n, 1.0 / n)
    draws = []
    done = 0
    while done < n_boot:
        b = min(chunk, n_boot - done)
        w = rng.multinomial(n, pvals, size=b).astype(np.float64)
        draws.append(_auc_weighted(ys, starts, w))
        done += b
    vals = np.concatenate(draws)
    vals = vals[np.isfinite(vals)]
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return {
        "auc": point,
        "lo": float(lo),
        "hi": float(hi),
        "gini": 2 * point - 1,
        "gini_lo": float(2 * lo - 1),
        "gini_hi": float(2 * hi - 1),
        "n": int(n),
        "n_boot": int(len(vals)),
    }


def bootstrap_auc_difference(
    y_a: np.ndarray,
    s_a: np.ndarray,
    y_b: np.ndarray,
    s_b: np.ndarray,
    n_boot: int = DEFAULT_BOOTSTRAP,
    seed: int = 5,
    alpha: float = 0.05,
) -> dict:
    """Interval for AUC(a) - AUC(b) on two *independent* samples.

    Honest reading: if the interval excludes zero the samples are unlikely to
    have come from equally-discriminating settings, under the assumption that
    rows are independent draws. It is not a corrected test over many
    comparisons, and it cannot tell you *why* the difference exists.
    """
    ya, sa = np.asarray(y_a, float), np.asarray(s_a, float)
    yb, sb = np.asarray(y_b, float), np.asarray(s_b, float)
    ys_a, st_a = _sorted_groups(ya, sa)
    ys_b, st_b = _sorted_groups(yb, sb)
    rng = np.random.default_rng(seed)
    na, nb = len(ya), len(yb)
    wa = rng.multinomial(na, np.full(na, 1.0 / na), size=n_boot).astype(np.float64)
    wb = rng.multinomial(nb, np.full(nb, 1.0 / nb), size=n_boot).astype(np.float64)
    diff = _auc_weighted(ys_a, st_a, wa) - _auc_weighted(ys_b, st_b, wb)
    diff = diff[np.isfinite(diff)]
    lo, hi = np.quantile(diff, [alpha / 2, 1 - alpha / 2])
    point = auc(ya, sa) - auc(yb, sb)
    return {
        "delta": float(point),
        "lo": float(lo),
        "hi": float(hi),
        "excludes_zero": bool(lo > 0 or hi < 0),
        "n_boot": int(len(diff)),
    }


def operating_points(y: np.ndarray, p: np.ndarray, rates=REJECT_RATES) -> list[dict]:
    """Reject the riskiest `rate` share; report what that decision catches."""
    y = np.asarray(y, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    total_bad = y.sum()
    out = []
    for rate in rates:
        cut = float(np.quantile(p, 1 - rate))
        rejected = p >= cut
        n_rej = int(rejected.sum())
        bad_rej = float(y[rejected].sum())
        out.append(
            {
                "reject_rate": rate,
                "threshold": cut,
                "n_rejected": n_rej,
                "precision": bad_rej / n_rej if n_rej else float("nan"),
                "recall": bad_rej / total_bad if total_bad else float("nan"),
                "approved_bad_rate": float(y[~rejected].mean()) if (~rejected).any() else float("nan"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=np.float64), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def calibration_slope_intercept(y: np.ndarray, p: np.ndarray) -> dict:
    """Cox calibration: regress the outcome on logit(p) with a free slope.

    slope 1 / intercept 0 is perfect. slope < 1 means the score is too
    spread out (over-confident at both ends); intercept > 0 means the model is
    systematically under-predicting the level of risk.
    """
    y = np.asarray(y, dtype=np.float64)
    x = _logit(p).reshape(-1, 1)
    if len(np.unique(y)) < 2:
        return {"slope": float("nan"), "intercept": float("nan")}
    lr = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(x, y)
    return {"slope": float(lr.coef_[0][0]), "intercept": float(lr.intercept_[0])}


def reliability(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    """Quantile-binned reliability curve with Wilson intervals on observed rate."""
    y = np.asarray(y, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, len(edges) - 2)
    rows = []
    for k in range(len(edges) - 1):
        m = idx == k
        n = int(m.sum())
        if n == 0:
            continue
        obs = float(y[m].mean())
        z = 1.96
        denom = 1 + z * z / n
        centre = (obs + z * z / (2 * n)) / denom
        half = z * np.sqrt(obs * (1 - obs) / n + z * z / (4 * n * n)) / denom
        rows.append(
            {
                "bin": k + 1,
                "n": n,
                "mean_pred": float(p[m].mean()),
                "observed": obs,
                "lo": float(max(0.0, centre - half)),
                "hi": float(min(1.0, centre + half)),
            }
        )
    return rows


def brier_decomposition(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict:
    """Murphy decomposition: Brier = reliability - resolution + uncertainty.

    With quantile bins the identity is approximate; the leftover is reported as
    `binning_residual` instead of being swept under the rug.
    """
    y = np.asarray(y, dtype=np.float64)
    rows = reliability(y, p, bins=bins)
    n_total = len(y)
    base = float(y.mean())
    rel = sum(r["n"] * (r["mean_pred"] - r["observed"]) ** 2 for r in rows) / n_total
    res = sum(r["n"] * (r["observed"] - base) ** 2 for r in rows) / n_total
    unc = base * (1 - base)
    score = brier(y, p)
    return {
        "brier": score,
        "reliability": float(rel),
        "resolution": float(res),
        "uncertainty": float(unc),
        "binning_residual": float(score - (rel - res + unc)),
    }


def fit_platt(y: np.ndarray, p: np.ndarray):
    """Platt scaling on the logit scale. Returns a callable p -> p_calibrated."""
    lr = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(
        _logit(p).reshape(-1, 1), np.asarray(y, dtype=np.float64)
    )
    return lambda q: lr.predict_proba(_logit(q).reshape(-1, 1))[:, 1]


def fit_isotonic(y: np.ndarray, p: np.ndarray):
    """Isotonic regression. More flexible than Platt, more prone to overfit."""
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(
        np.asarray(p, dtype=np.float64), np.asarray(y, dtype=np.float64)
    )
    return lambda q: np.clip(iso.predict(np.asarray(q, dtype=np.float64)), EPS, 1 - EPS)


def calibration_report(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict:
    si = calibration_slope_intercept(y, p)
    return {
        **si,
        "brier": brier(y, p),
        "log_loss": log_loss(y, p),
        "mean_predicted": float(np.mean(p)),
        "observed_rate": float(np.mean(y)),
        "curve": reliability(y, p, bins=bins),
        "decomposition": brier_decomposition(y, p, bins=bins),
    }


def full_report(y: np.ndarray, p: np.ndarray, n_boot: int = DEFAULT_BOOTSTRAP, seed: int = 3) -> dict:
    """Everything for one (labels, scores) pair."""
    boot = bootstrap_auc(y, p, n_boot=n_boot, seed=seed)
    return {
        **boot,
        "ks": ks(y, p),
        "log_loss": log_loss(y, p),
        "brier": brier(y, p),
        "bad_rate": float(np.mean(y)),
        "calibration": calibration_slope_intercept(y, p),
        "operating_points": operating_points(y, p),
    }


def monthly_metrics(
    months: np.ndarray,
    y: np.ndarray,
    p: np.ndarray,
    n_boot: int = 300,
    seed: int = 9,
) -> list[dict]:
    """Per-cohort discrimination and calibration across the whole window."""
    months = np.asarray(months)
    y = np.asarray(y, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    rows = []
    for m in sorted(np.unique(months).tolist()):
        sel = months == m
        boot = bootstrap_auc(y[sel], p[sel], n_boot=n_boot, seed=seed + int(m))
        cal = calibration_slope_intercept(y[sel], p[sel])
        rows.append(
            {
                "month": int(m),
                "n": int(sel.sum()),
                "bad_rate": float(y[sel].mean()),
                "mean_predicted": float(p[sel].mean()),
                "auc": boot["auc"],
                "lo": boot["lo"],
                "hi": boot["hi"],
                "brier": brier(y[sel], p[sel]),
                "slope": cal["slope"],
                "intercept": cal["intercept"],
            }
        )
    return rows
