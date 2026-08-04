"""The business layer: turning a probability into an approve/decline decision
and then into money.

A model is only as good as the cut-off applied to it, and the cut-off is an
economic choice, not a statistical one. The arithmetic is deliberately simple
and stated in full so it can be checked by hand:

    approve if PD < threshold

    revenue      = margin  * principal of approved loans that did not default
    credit loss  = lgd     * principal of approved loans that did default
    opportunity  = fr_cost * number of good applicants that were declined
    profit       = revenue - credit loss - opportunity

`margin`, `lgd` and `fr_cost` are inputs, not findings. The defaults are
plausible illustrative values, not a claim about any real lender's economics.
"""

from __future__ import annotations

import numpy as np

DEFAULTS = {"lgd": 0.65, "margin": 0.09, "fr_cost": 45.0}
PRESET_APPROVAL_RATES = {"conservative": 0.60, "balanced": 0.80, "growth": 0.92}
GRID = np.round(np.arange(0.005, 0.6005, 0.005), 4)


def outcomes(
    scores: np.ndarray,
    y: np.ndarray,
    loan: np.ndarray,
    threshold: float,
    lgd: float = DEFAULTS["lgd"],
    margin: float = DEFAULTS["margin"],
    fr_cost: float = DEFAULTS["fr_cost"],
) -> dict:
    """Full economics of one threshold on one cohort."""
    scores = np.asarray(scores, dtype=float)
    y = np.asarray(y, dtype=float)
    loan = np.asarray(loan, dtype=float)
    approved = scores < threshold
    n = len(scores)
    n_appr = int(approved.sum())
    bad = approved & (y == 1)
    good = approved & (y == 0)
    rejected_good = (~approved) & (y == 0)
    principal_good = float(loan[good].sum())
    principal_bad = float(loan[bad].sum())
    revenue = margin * principal_good
    loss = lgd * principal_bad
    opportunity = fr_cost * float(rejected_good.sum())
    return {
        "threshold": float(threshold),
        "n": n,
        "n_approved": n_appr,
        "approval_rate": n_appr / n if n else 0.0,
        "n_approved_bad": int(bad.sum()),
        "approved_bad_rate": float(bad.sum()) / n_appr if n_appr else 0.0,
        "principal_approved": principal_good + principal_bad,
        "principal_good": principal_good,
        "principal_bad": principal_bad,
        "revenue": revenue,
        "expected_loss": loss,
        "opportunity_cost": opportunity,
        "profit": revenue - loss - opportunity,
        "n_rejected_good": int(rejected_good.sum()),
    }


def grid(scores: np.ndarray, y: np.ndarray, loan: np.ndarray, thresholds=GRID) -> list[dict]:
    """Threshold-independent aggregates, computed once.

    Everything the profit formula needs is a cumulative sum over score order, so
    the whole curve costs one sort. The web app never refits anything: it reads
    this grid and applies the formula for whatever lgd/margin/fr_cost the user
    typed.
    """
    scores = np.asarray(scores, dtype=float)
    y = np.asarray(y, dtype=float)
    loan = np.asarray(loan, dtype=float)
    order = np.argsort(scores, kind="mergesort")
    s, ys, ls = scores[order], y[order], loan[order]
    n = len(s)
    cum_bad = np.concatenate(([0.0], np.cumsum(ys)))
    cum_loan_bad = np.concatenate(([0.0], np.cumsum(ls * ys)))
    cum_loan_good = np.concatenate(([0.0], np.cumsum(ls * (1 - ys))))
    total_good = float((1 - ys).sum())
    rows = []
    for t in thresholds:
        k = int(np.searchsorted(s, t, side="left"))  # approved = first k rows
        n_bad = cum_bad[k]
        good_appr = k - n_bad
        rows.append(
            {
                "threshold": float(t),
                "n_approved": k,
                "approval_rate": k / n if n else 0.0,
                "n_approved_bad": float(n_bad),
                "approved_bad_rate": float(n_bad / k) if k else 0.0,
                "principal_good": float(cum_loan_good[k]),
                "principal_bad": float(cum_loan_bad[k]),
                "n_rejected_good": float(total_good - good_appr),
            }
        )
    return rows


def apply_economics(
    row: dict,
    lgd: float = DEFAULTS["lgd"],
    margin: float = DEFAULTS["margin"],
    fr_cost: float = DEFAULTS["fr_cost"],
) -> dict:
    """Same formula as `outcomes`, applied to a precomputed grid row."""
    revenue = margin * row["principal_good"]
    loss = lgd * row["principal_bad"]
    opportunity = fr_cost * row["n_rejected_good"]
    return {
        **row,
        "revenue": revenue,
        "expected_loss": loss,
        "opportunity_cost": opportunity,
        "profit": revenue - loss - opportunity,
        "principal_approved": row["principal_good"] + row["principal_bad"],
    }


def curve(grid_rows: list[dict], **econ) -> list[dict]:
    return [apply_economics(r, **econ) for r in grid_rows]


def optimal(grid_rows: list[dict], **econ) -> dict:
    return max(curve(grid_rows, **econ), key=lambda r: r["profit"])


def preset_thresholds(reference_scores: np.ndarray) -> dict[str, float]:
    """Presets defined by target approval rate on the training cohort.

    Expressing a preset as "approve 80% of the reference population" is how a
    credit policy is actually written; a bare PD cut-off means nothing without
    knowing the score distribution it sits on.
    """
    ref = np.asarray(reference_scores, dtype=float)
    return {
        name: float(np.quantile(ref, rate)) for name, rate in PRESET_APPROVAL_RATES.items()
    }


def stale_threshold_cost(
    train_grid: list[dict],
    test_grid: list[dict],
    **econ,
) -> dict:
    """What it costs to keep last year's cut-off after the population moved.

    Pick the profit-maximising threshold on the training months, then apply it
    to the test months and compare with the threshold you would have picked had
    you re-optimised on the test months.
    """
    stale = optimal(train_grid, **econ)
    fresh = optimal(test_grid, **econ)
    test_curve = curve(test_grid, **econ)
    applied = min(test_curve, key=lambda r: abs(r["threshold"] - stale["threshold"]))
    return {
        "stale_threshold": stale["threshold"],
        "fresh_threshold": fresh["threshold"],
        "threshold_move": fresh["threshold"] - stale["threshold"],
        "profit_stale_on_test": applied["profit"],
        "profit_fresh_on_test": fresh["profit"],
        "profit_gap": fresh["profit"] - applied["profit"],
        "profit_gap_pct": (
            (fresh["profit"] - applied["profit"]) / abs(fresh["profit"]) if fresh["profit"] else float("nan")
        ),
        "approval_rate_stale": applied["approval_rate"],
        "approval_rate_fresh": fresh["approval_rate"],
        "bad_rate_stale": applied["approved_bad_rate"],
        "bad_rate_fresh": fresh["approved_bad_rate"],
    }
