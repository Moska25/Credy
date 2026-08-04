"""Subgroup performance and calibration.

This is a *diagnostic*, not a fairness audit. The data is synthetic, the group
definitions are the ones the generator happens to produce, and no protected
characteristic in the legal sense is modelled at all. What it is good for:
showing that an aggregate AUC can hide a subgroup where the model ranks badly
or misprices risk, and showing how wide the intervals get once a cohort is small.

Read every row with its `n`. A subgroup of 400 applicants with a 9% bad rate has
roughly 36 defaults in it; its AUC interval will be wide enough to drive a bus
through, and no amount of decimal places changes that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import evaluate as ev

AGE_BANDS = [(18, 25), (26, 35), (36, 50), (51, 65), (66, 120)]
MIN_GROUP = 150


def age_band(age: float) -> str:
    for lo, hi in AGE_BANDS:
        if lo <= age <= hi:
            return f"{lo}-{hi}" if hi < 120 else f"{lo}+"
    return "unknown"


def analyse(
    df: pd.DataFrame,
    scores: np.ndarray,
    dimensions=("age_band", "employment_type", "region", "channel"),
    n_boot: int = 500,
    seed: int = 21,
) -> list[dict]:
    """Per-level metrics for each grouping dimension, with intervals."""
    work = df.copy()
    work["age_band"] = work["age"].map(age_band)
    y = df["default"].to_numpy(dtype=float)
    out = []
    for dim in dimensions:
        levels = sorted(work[dim].dropna().unique().tolist())
        rows = []
        for level in levels:
            sel = (work[dim] == level).to_numpy()
            n = int(sel.sum())
            ys, ps = y[sel], scores[sel]
            small = n < MIN_GROUP or ys.sum() < 15
            boot = (
                ev.bootstrap_auc(ys, ps, n_boot=n_boot, seed=seed)
                if not small
                else {"auc": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": n}
            )
            cal = ev.calibration_slope_intercept(ys, ps) if not small else {"slope": float("nan"), "intercept": float("nan")}
            rows.append(
                {
                    "level": str(level),
                    "n": n,
                    "share": n / len(df),
                    "bad_rate": float(ys.mean()) if n else float("nan"),
                    "mean_predicted": float(ps.mean()) if n else float("nan"),
                    "auc": boot["auc"],
                    "lo": boot["lo"],
                    "hi": boot["hi"],
                    "ci_width": (boot["hi"] - boot["lo"]) if np.isfinite(boot.get("hi", np.nan)) else float("nan"),
                    "slope": cal["slope"],
                    "intercept": cal["intercept"],
                    "too_small": bool(small),
                }
            )
        out.append({"dimension": dim, "levels": rows})
    return out


def widest_gap(analysis: list[dict]) -> dict | None:
    """Largest AUC spread within any single dimension, for the summary line."""
    best = None
    for block in analysis:
        usable = [r for r in block["levels"] if np.isfinite(r["auc"])]
        if len(usable) < 2:
            continue
        hi = max(usable, key=lambda r: r["auc"])
        lo = min(usable, key=lambda r: r["auc"])
        gap = hi["auc"] - lo["auc"]
        if best is None or gap > best["gap"]:
            best = {
                "dimension": block["dimension"],
                "gap": gap,
                "best_level": hi["level"],
                "best_auc": hi["auc"],
                "worst_level": lo["level"],
                "worst_auc": lo["auc"],
                "overlapping_intervals": bool(lo["hi"] >= hi["lo"]),
            }
    return best
