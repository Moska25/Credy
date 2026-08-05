"""One-shot pipeline: generate -> fit -> evaluate -> monitor -> persist.

Everything expensive happens exactly once, here. The web app opens the SQLite
file, reads precomputed JSON artifacts, and renders. No model is fitted inside a
request, so every page is fast and identical on every reload.

Idempotent: rerunning with the same SEED_VERSION is a no-op; `--force` rebuilds.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import pandas as pd

from . import charts  # noqa: F401  (import kept so a broken chart module fails at seed time)
from . import db, drift, evaluate as ev, generate as gen, models, policy, sources, subgroups

SEED_VERSION = "credy-1"
N_ROWS = 40_000
DATA_SEED = 7
N_BOOT = 500
N_BOOT_MONTHLY = 300
CHAMPION = "hgb"


def _log(msg: str, t0: float) -> None:
    print(f"[seed] {time.time() - t0:6.1f}s  {msg}", flush=True)


def _control_alerts(n_rows: int, n_boot: int) -> dict:
    """Run the whole monitoring stack against a population with no drift at all.

    Same size, same model family, same rules, all four drift switches off. Any
    alert this produces is a false alarm by construction, which is the only
    honest way to read the alert counts on the real cohort.
    """
    df = sources.load(
        "synthetic", n=n_rows, seed=DATA_SEED + 101, drift=gen.DRIFT_ALL_OFF
    )
    y = df["default"].to_numpy(dtype=float)
    X = models.design_matrix(df)
    split = models.temporal_split(df)
    scores = models.fit_hgb(X[split["train"]], y[split["train"]]).predict_proba(X)[:, 1]
    monthly = ev.monthly_metrics(df["month"].to_numpy(), y, scores, n_boot=N_BOOT_MONTHLY)
    baseline = drift.early_production_baseline(
        df["month"].to_numpy(), y, scores, n_boot=n_boot
    )
    fired = drift.alerts(
        drift.score_drift(df, scores),
        monthly,
        drift.missingness(df),
        feature_psi=drift.feature_drift(df),
        baseline=baseline,
    )
    counts: dict[str, int] = {}
    for a in fired:
        counts[a["rule"]] = counts.get(a["rule"], 0) + 1
    return {
        "rows": int(len(df)),
        "monitored_months": gen.N_MONTHS - gen.TRAIN_MONTHS[1],
        "alerts": fired,
        "by_rule": counts,
        "bad_rate_first_year": float(y[df["month"].to_numpy() <= 12].mean()),
        "bad_rate_second_year": float(y[df["month"].to_numpy() > 12].mean()),
    }


def build(n_rows: int = N_ROWS, n_boot: int = N_BOOT, verbose: bool = True) -> dict:
    """Run the whole pipeline in memory and return (df, scores, artifacts)."""
    t0 = time.time()
    say = (lambda m: _log(m, t0)) if verbose else (lambda m: None)

    # ---- 1. data ----------------------------------------------------------
    # Through the adapter rather than calling the generator directly, so the
    # schema check that guards the real-data sources also guards this one. A
    # generator change that broke the contract would otherwise only be caught
    # by the tests, and the pipeline would seed a subtly wrong database first.
    df = sources.load("synthetic", n=n_rows, seed=DATA_SEED)
    truth = gen.dgp_truth()
    say(f"generated {len(df):,} applicants over {gen.N_MONTHS} months")

    y = df["default"].to_numpy(dtype=float)
    months = df["month"].to_numpy()
    loan = df["loan_amount"].to_numpy(dtype=float)

    # ---- 2. splits and fitting -------------------------------------------
    tsplit = models.temporal_split(df)
    sizes = {k: len(v) for k, v in tsplit.items()}
    rsplit = models.random_split(df, sizes)

    temporal_models = models.fit_all(df, tsplit["train"])
    scores = models.predict_all(temporal_models, df)
    say("fitted scorecard / logistic / gradient boosting on months 1-12")

    random_models = models.fit_all(df, rsplit["train"])
    random_scores = models.predict_all(random_models, df)
    say("fitted the same three under a naive random split")

    # ---- 3. the headline: temporal vs random ------------------------------
    comparison = []
    for name in ("scorecard", "logistic", "hgb"):
        t_idx, r_idx = tsplit["test"], rsplit["test"]
        # Same seed as the per-model test report below, so the two tables on
        # /performance quote identical intervals rather than two draws of it.
        t = ev.bootstrap_auc(y[t_idx], scores[name][t_idx], n_boot=n_boot, seed=43)
        r = ev.bootstrap_auc(y[r_idx], random_scores[name][r_idx], n_boot=n_boot, seed=32)
        comparison.append(
            {
                "model": name,
                "label": models.MODEL_LABELS[name],
                "temporal": t,
                "random": r,
                "overstatement": r["auc"] - t["auc"],
                "intervals_overlap": bool(r["lo"] <= t["hi"] and t["lo"] <= r["hi"]),
            }
        )
    say("temporal vs random split comparison done")

    # ---- 4. performance ---------------------------------------------------
    val_idx, test_idx, train_idx = tsplit["validation"], tsplit["test"], tsplit["train"]
    per_model = {}
    for name in ("scorecard", "logistic", "hgb"):
        per_model[name] = {
            "label": models.MODEL_LABELS[name],
            "train": ev.full_report(y[train_idx], scores[name][train_idx], n_boot=n_boot, seed=41),
            "validation": ev.full_report(y[val_idx], scores[name][val_idx], n_boot=n_boot, seed=42),
            "test": ev.full_report(y[test_idx], scores[name][test_idx], n_boot=n_boot, seed=43),
        }

    champ = scores[CHAMPION]
    monthly = ev.monthly_metrics(months, y, champ, n_boot=N_BOOT_MONTHLY)
    decay = ev.bootstrap_auc_difference(
        y[val_idx], champ[val_idx], y[test_idx], champ[test_idx], n_boot=n_boot
    )
    say("bootstrap intervals and month-by-month decay computed")

    # ---- 5. calibration ---------------------------------------------------
    platt = ev.fit_platt(y[val_idx], champ[val_idx])
    isotonic = ev.fit_isotonic(y[val_idx], champ[val_idx])
    champ_platt = platt(champ)
    champ_iso = isotonic(champ)
    calibration = {
        "champion": CHAMPION,
        "champion_label": models.MODEL_LABELS[CHAMPION],
        "fitted_on": "validation months 13-18",
        "variants": {
            "raw": ev.calibration_report(y[test_idx], champ[test_idx]),
            "platt": ev.calibration_report(y[test_idx], champ_platt[test_idx]),
            "isotonic": ev.calibration_report(y[test_idx], champ_iso[test_idx]),
        },
        "validation_raw": ev.calibration_report(y[val_idx], champ[val_idx]),
        "auc_unchanged": {
            "raw": ev.auc(y[test_idx], champ[test_idx]),
            "platt": ev.auc(y[test_idx], champ_platt[test_idx]),
            "isotonic": ev.auc(y[test_idx], champ_iso[test_idx]),
        },
        "monthly_slope": [
            {"month": r["month"], "slope": r["slope"], "intercept": r["intercept"]} for r in monthly
        ],
    }
    say("calibration and recalibration done")

    # ---- 6. drift ---------------------------------------------------------
    feat_drift = drift.feature_drift(df)
    score_psi = drift.score_drift(df, champ)
    miss = drift.missingness(df)
    baseline = drift.early_production_baseline(months, y, champ, n_boot=n_boot)
    fired = drift.alerts(score_psi, monthly, miss, feature_psi=feat_drift, baseline=baseline)
    verification = drift.verify_against_truth(fired, truth)
    say(f"drift monitoring done, {len(fired)} alerts fired")

    # ---- 6b. control: the same rules against a population with no drift ----
    # A detector that fires is only interesting if it stays quiet when nothing
    # happened. This runs the identical alert stack over a stationary cohort of
    # the same size, so every rule gets a false-alarm count next to its hit count.
    control = _control_alerts(n_rows, n_boot)
    say(f"stationary control run done, {len(control['alerts'])} false alarms")

    # ---- 7. subgroups (test cohort only) ----------------------------------
    sub = subgroups.analyse(df.iloc[test_idx], champ[test_idx], n_boot=n_boot)
    sub_gap = subgroups.widest_gap(sub)
    say("subgroup analysis done")

    # ---- 8. policy --------------------------------------------------------
    # Reference cohort for setting policy = months 13-18, i.e. the most recent
    # data available at deployment that the model was NOT fitted on.
    ref_scores = champ_platt[val_idx]
    ref_grid = policy.grid(ref_scores, y[val_idx], loan[val_idx])
    test_grid = policy.grid(champ_platt[test_idx], y[test_idx], loan[test_idx])
    presets = policy.preset_thresholds(ref_scores)
    stale = policy.stale_threshold_cost(ref_grid, test_grid)
    say("policy grids computed")

    # ---- 9. estimated vs true coefficients --------------------------------
    est = models.logistic_coefficients(temporal_models["logistic"])
    true_map = {
        "z_age": gen.COEF["z_age"],
        "z_log_income": gen.COEF["z_income"],
        "z_tenure": gen.COEF["z_tenure"],
        "debt_ratio": gen.COEF["debt_ratio"],
        "z_credit_history": gen.COEF["z_credit_history"],
        "prior_delinquencies": gen.COEF["prior_delinquencies"],
        "loan_to_income": gen.COEF["loan_to_income"],
        "z_term": gen.COEF["z_term"],
        "missing_income": gen.COEF["missing_income"],
        "missing_credit_history": gen.COEF["missing_credit_history"],
        "log_loan_amount": None,
        "missing_employment_tenure": 0.0,
        **{f"employment_type={k}": v for k, v in gen.EMPLOYMENT_COEF.items() if k != "salaried"},
        **{f"region={k}": v for k, v in gen.REGION_COEF.items() if k != "south"},
        **{f"channel={k}": v for k, v in gen.CHANNEL_COEF.items() if k != "branch"},
    }
    coef_rows = [
        {
            "feature": name,
            "estimated": est[name],
            "true": true_map.get(name),
            "sign_match": (
                None
                if true_map.get(name) in (None, 0.0)
                else bool(np.sign(est[name]) == np.sign(true_map[name]))
            ),
        }
        for name in models.FEATURE_NAMES
    ]

    artifacts = {
        "meta": {
            "seed_version": SEED_VERSION,
            "rows": int(len(df)),
            "months": gen.N_MONTHS,
            "data_seed": DATA_SEED,
            "n_boot": n_boot,
            "n_boot_monthly": N_BOOT_MONTHLY,
            "champion": CHAMPION,
            "champion_label": models.MODEL_LABELS[CHAMPION],
            "splits": {k: {"n": len(v)} for k, v in tsplit.items()},
            "split_months": {
                "train": list(gen.TRAIN_MONTHS),
                "validation": list(gen.VAL_MONTHS),
                "test": list(gen.TEST_MONTHS),
            },
            "overall_bad_rate": float(y.mean()),
            "built_seconds": None,
        },
        "truth": truth,
        "comparison": comparison,
        "performance": {
            "per_model": per_model,
            "monthly": monthly,
            "decay": decay,
            "train_months_in_sample": list(gen.TRAIN_MONTHS),
        },
        "calibration": calibration,
        "drift": {
            "feature": feat_drift,
            "score": score_psi,
            "missingness": miss,
            "alerts": fired,
            "verification": verification,
            "baseline": baseline,
            "control": control,
            "by_rule": {
                rule: {
                    "drifted": sum(1 for a in fired if a["rule"] == rule),
                    "control": control["by_rule"].get(rule, 0),
                }
                for rule in sorted(
                    {a["rule"] for a in fired} | set(control["by_rule"])
                    | {"score_psi", "auc_decline"}
                )
            },
            "thresholds": {
                "psi_watch": drift.PSI_WATCH,
                "psi_shift": drift.PSI_SHIFT,
                "score_psi_alert": drift.SCORE_PSI_ALERT,
                "slope_band": list(drift.SLOPE_BAND),
                "auc_floor": drift.AUC_FLOOR,
                "missingness_jump": drift.MISSINGNESS_JUMP,
                "pd_gap": drift.PD_GAP_ALERT,
            },
        },
        "subgroups": {"analysis": sub, "widest_gap": sub_gap, "min_group": subgroups.MIN_GROUP},
        "policy": {
            "reference_grid": ref_grid,
            "test_grid": test_grid,
            "presets": presets,
            "preset_rates": policy.PRESET_APPROVAL_RATES,
            "defaults": policy.DEFAULTS,
            "stale": stale,
            "reference_label": "months 13-18 (validation)",
            "test_label": "months 19-24 (test)",
            "reference_n": int(len(val_idx)),
            "test_n": int(len(test_idx)),
        },
        "coefficients": coef_rows,
        "bad_rate_by_month": [
            {"month": int(m), "bad_rate": float(y[months == m].mean()), "n": int((months == m).sum())}
            for m in sorted(np.unique(months).tolist())
        ],
    }

    all_scores = {
        "scorecard": scores["scorecard"],
        "logistic": scores["logistic"],
        "hgb": scores["hgb"],
        "hgb_platt": champ_platt,
    }
    artifacts["meta"]["built_seconds"] = round(time.time() - t0, 1)
    return {"df": df, "scores": all_scores, "artifacts": artifacts, "truth": truth}


def seed(force: bool = False, n_rows: int = N_ROWS, n_boot: int = N_BOOT) -> None:
    conn = db.connect()
    db.init(conn)
    if not force and db.is_seeded(conn, SEED_VERSION):
        print(f"[seed] already seeded at version {SEED_VERSION}; nothing to do.")
        conn.close()
        return

    built = build(n_rows=n_rows, n_boot=n_boot)
    db.reset(conn)
    db.write_applicants(conn, built["df"])
    db.write_predictions(conn, built["df"]["applicant_id"].tolist(), built["scores"])
    for key, payload in built["artifacts"].items():
        db.put(conn, key, payload)
    conn.close()

    truth_path = db.DATA_DIR / "dgp_truth.json"
    truth_path.write_text(json.dumps(built["truth"], indent=2))
    print(
        f"[seed] wrote {len(built['df']):,} applicants, "
        f"{len(built['scores']) * len(built['df']):,} predictions and "
        f"{len(built['artifacts'])} artifacts to {db.DB_PATH}"
    )
    print(f"[seed] true DGP parameters written to {truth_path}")
    print(f"[seed] total {built['artifacts']['meta']['built_seconds']}s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the Credy dataset, models and artifacts.")
    ap.add_argument("--force", action="store_true", help="rebuild even if already seeded")
    ap.add_argument("--rows", type=int, default=N_ROWS)
    ap.add_argument("--boot", type=int, default=N_BOOT)
    args = ap.parse_args(argv)
    seed(force=args.force, n_rows=args.rows, n_boot=args.boot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
