"""Export the seeded artifacts to JSON for the Next.js UI in web/.

The FastAPI app reads app artifacts straight out of SQLite. The Next app is a
static build with no Python at request time, so the same artifacts are written
out once, here, and committed. Same numbers, one source.

    ./.venv/bin/python -m scripts.export_artifacts

Re-run it after ``python -m app.seed``. Nothing in web/ invents a figure.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import db, generate as gen

OUT = Path(__file__).resolve().parent.parent / "web" / "lib" / "artifacts.json"

MODEL_ORDER = ["scorecard", "logistic", "hgb"]
WINDOWS = ["train", "validation", "test"]


def by_month(d: dict, months: list[int]) -> list[float]:
    """JSON object keys come back as strings; the UI wants a month-ordered array."""
    return [d[str(m)] for m in months]


def money(x: float, places: int = 1) -> str:
    sign = "-" if x < 0 else ""
    v = abs(x)
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if v >= cut:
            return f"{sign}{v / cut:,.{places}f}{suffix}"
    return f"{sign}{v:,.0f}"


def ece(curve: list[dict]) -> float:
    """Expected calibration error over the equal-count bins the seeder wrote."""
    n = sum(b["n"] for b in curve)
    return sum(b["n"] / n * abs(b["observed"] - b["mean_pred"]) for b in curve) if n else 0.0


def subgroup_note(block: dict, widest: dict, floor: int) -> str:
    small = [r["level"] for r in block["levels"] if r["too_small"]]
    if small:
        return (
            f"Not scored: {', '.join(small)}. Below the {floor}-application floor "
            "or fewer than 15 defaults."
        )
    if block["dimension"] == widest.get("dimension"):
        overlap = "overlapping" if widest.get("overlapping_intervals") else "disjoint"
        return f"Widest spread of any dimension: {widest['gap']:.3f} AUC, with {overlap} intervals."
    return "No level in this dimension falls below the reporting floor."


def drift_schedule(truth: dict) -> list[list[str]]:
    """The four switches, written out of the schedule the generator recorded."""
    s, on = truth["schedule"], truth["drift_switches"]
    last = 24
    rows = []
    if on["covariate_shift"]:
        c = s["covariate_shift"]
        rows.append([
            "covariate_shift", f"{c['starts_month']} → {last}",
            f"Mean log-income slides by {c['log_shift_at_month_24']:+.2f}; broker share grows "
            f"{c['broker_share_month_1']:.2f} → {c['broker_share_month_24']:.2f}, taken from online.",
            "P(x) only",
        ])
    if on["prior_shift"]:
        c = s["prior_shift"]
        rows.append([
            "prior_shift", f"{c['starts_month']} → {last}",
            f"{c['shift_at_month_24']:+.2f} logit units added to the intercept, so the base "
            "default rate rises.",
            "P(y)",
        ])
    if on["concept_drift"]:
        c = s["concept_drift"]
        rows.append([
            "concept_drift", f"{c['starts_month']} → {last}",
            f"Broker channel coefficient moves from {c['coef_month_1']:+.2f} to "
            f"{c['coef_month_24']:+.2f}: the same feature value now means something different.",
            "P(y|x)",
        ])
    if on["quality_drift"]:
        c = s["quality_drift"]
        rows.append([
            "quality_drift", str(c["starts_month"]),
            f"{c['feature']} missingness steps from {c['missing_rate_before']:.0%} to "
            f"{c['missing_rate_after']:.0%} in one month.",
            "observability",
        ])
    return rows


RULE_VERDICT = {
    # (fires on drifted, fires on control) -> how the drift page reads the row
    "idle": "never fired",
    "bad": "not discriminating",
    "ok": "clean signal",
}


def build() -> dict:
    conn = db.connect()
    try:
        art = db.all_artifacts(conn)
        if not art:
            raise SystemExit("Not seeded. Run: ./.venv/bin/python -m app.seed")
        sample = [
            list(r)
            for r in conn.execute(
                'SELECT applicant_id, month, age, income, employment_type, employment_tenure, '
                'debt_ratio, credit_history_years, prior_delinquencies, loan_amount, term_months, '
                'region, channel, true_pd, "default" FROM applicants '
                "WHERE applicant_id % 3571 = 0 ORDER BY applicant_id LIMIT 12"
            )
        ]
        cohorts = [
            {"month": r[0], "n": r[1], "badRate": r[2], "incomePresent": r[3]}
            for r in conn.execute(
                'SELECT month, COUNT(*), AVG("default"), AVG(COALESCE(income, 0) > 0) '
                "FROM applicants GROUP BY month ORDER BY month"
            )
        ]
    finally:
        conn.close()

    meta = art["meta"]
    months = art["drift"]["feature"]["months"]
    monthly = art["performance"]["monthly"]
    d = art["drift"]
    champ_key = meta["champion"]
    champ = next(c for c in art["comparison"] if c["model"] == champ_key)
    cal = art["calibration"]
    sg = art["subgroups"]
    pol = art["policy"]

    feature_psi = {f: by_month(v, months) for f, v in d["feature"]["psi"].items()}
    worst_feature = max(feature_psi, key=lambda f: max(feature_psi[f]))
    worst_psi = max(feature_psi[worst_feature])
    score_psi = [r["psi"] for r in d["score"]]

    alerts = [
        {
            "month": a["month"],
            "severity": a["severity"],
            "rule": a["rule"],
            "title": a["message"],
            "trigger": (
                f"trigger {a['rule']} on {a['subject']} · value {a['value']:.3f} "
                f"against threshold {a['threshold']:.3f}"
            ),
            "action": a["action"],
        }
        for a in d["alerts"]
    ]

    by_rule = []
    for rule, counts in sorted(
        d["by_rule"].items(), key=lambda kv: (-kv[1]["drifted"], kv[0])
    ):
        if counts["drifted"] == 0 and counts["control"] == 0:
            kind = "idle"
        elif counts["control"] > 0:
            kind = "bad"
        else:
            kind = "ok"
        by_rule.append(
            {"rule": rule, "drifted": counts["drifted"], "control": counts["control"],
             "verdict": RULE_VERDICT[kind], "kind": kind}
        )

    variants = []
    order = sorted(("raw", "platt", "isotonic"), key=lambda k: ece(cal["variants"][k]["curve"]))
    heat_for = {order[0]: 1, order[1]: 2, order[2]: 4}
    for key, label in (("raw", "Raw model output"), ("platt", "Platt scaling"),
                       ("isotonic", "Isotonic regression")):
        v = cal["variants"][key]
        variants.append({
            "key": key, "label": label, "slope": v["slope"], "intercept": v["intercept"],
            "brier": v["brier"], "logLoss": v["log_loss"], "ece": ece(v["curve"]),
            "heat": heat_for[key],
        })

    reliability = {
        key: [[b["mean_pred"], b["observed"]] for b in cal["variants"][key]["curve"]]
        for key in ("raw", "platt", "isotonic")
    }
    rel_bounds = [p for c in reliability.values() for p in c]

    bounds = [
        v for block in sg["analysis"] for r in block["levels"]
        if not r["too_small"] and r.get("lo") is not None for v in (r["lo"], r["hi"])
    ]
    pad = max((max(bounds) - min(bounds)) * 0.06, 0.004)

    hero_lo = min(champ["temporal"]["lo"], champ["random"]["lo"])
    hero_hi = max(champ["temporal"]["hi"], champ["random"]["hi"])
    hero_pad = max((hero_hi - hero_lo) * 0.12, 0.004)

    per_model = [
        {
            "label": art["performance"]["per_model"][m]["label"],
            "windows": [
                {
                    "window": w,
                    "n": art["performance"]["per_model"][m][w]["n"],
                    "badRate": art["performance"]["per_model"][m][w]["bad_rate"],
                    "auc": art["performance"]["per_model"][m][w]["auc"],
                    "lo": art["performance"]["per_model"][m][w]["lo"],
                    "hi": art["performance"]["per_model"][m][w]["hi"],
                    "gini": art["performance"]["per_model"][m][w]["gini"],
                    "ks": art["performance"]["per_model"][m][w]["ks"],
                    "logLoss": art["performance"]["per_model"][m][w]["log_loss"],
                    "brier": art["performance"]["per_model"][m][w]["brier"],
                    "slope": art["performance"]["per_model"][m][w]["calibration"]["slope"],
                }
                for w in WINDOWS
            ],
        }
        for m in MODEL_ORDER
    ]
    champ_windows = {
        w["window"]: w for w in next(p for p in per_model if p["label"] == meta["champion_label"])["windows"]
    }

    n_levels = sum(len(b["levels"]) for b in sg["analysis"])
    n_scored = sum(1 for b in sg["analysis"] for r in b["levels"] if not r["too_small"])

    return {
        "meta": {
            "build": meta["seed_version"],
            "rows": meta["rows"],
            "months": meta["months"],
            "dataSeed": meta["data_seed"],
            "champion": meta["champion_label"],
            "nBoot": meta["n_boot"],
            "nBootMonthly": meta["n_boot_monthly"],
            "builtSeconds": meta["built_seconds"],
            "splits": {k: list(v) for k, v in meta["split_months"].items()},
            "splitSizes": {k: v["n"] for k, v in meta["splits"].items()},
            "perMonth": round(meta["rows"] / meta["months"]),
        },
        "months": months,
        "auc": [r["auc"] for r in monthly],
        "aucLo": [r["lo"] for r in monthly],
        "aucHi": [r["hi"] for r in monthly],
        "badRate": [r["bad_rate"] for r in monthly],
        "meanPredicted": [r["mean_predicted"] for r in monthly],
        "scorePsi": score_psi,
        "scoreJs": [r["js"] for r in d["score"]],
        "scorePsiMax": max(score_psi),
        "scorePsiFinal": score_psi[-1],
        "thresholds": {
            "scorePsiAlert": d["thresholds"]["score_psi_alert"],
            "psiWatch": d["thresholds"]["psi_watch"],
            "psiShift": d["thresholds"]["psi_shift"],
            "aucFloor": d["thresholds"]["auc_floor"],
            "aucBaseline": d["baseline"]["auc"],
            "slopeBand": d["thresholds"]["slope_band"],
            "pdGap": d["thresholds"]["pd_gap"],
            "missingnessJump": d["thresholds"]["missingness_jump"],
        },
        "featurePsi": feature_psi,
        "worstFeature": {"name": worst_feature, "psi": worst_psi},
        "missingness": {
            f: {"ref": d["missingness"]["reference"][f],
                "rates": by_month(d["missingness"]["rates"][f], months)}
            for f in d["missingness"]["features"]
        },
        "alerts": alerts,
        "alertTotals": {
            "total": len(alerts),
            "high": sum(1 for a in alerts if a["severity"] == "high"),
            "firstMonth": min(a["month"] for a in alerts) if alerts else None,
        },
        "byRule": by_rule,
        "control": {
            "rows": d["control"]["rows"],
            "alerts": len(d["control"]["alerts"]),
            "badRateYear1": d["control"]["bad_rate_first_year"],
            "badRateYear2": d["control"]["bad_rate_second_year"],
        },
        "verification": [
            {"injected": r["injected"], "starts": r["starts_month"], "detector": r["detector"],
             "first": r["first_detected_month"], "lag": r["lag_months"],
             "alerts": r["n_alerts"], "detected": r["detected"]}
            for r in d["verification"]["rows"]
        ],
        "comparison": [
            {"label": c["label"],
             "temporal": [c["temporal"]["auc"], c["temporal"]["lo"], c["temporal"]["hi"]],
             "random": [c["random"]["auc"], c["random"]["lo"], c["random"]["hi"]],
             "overstatement": c["overstatement"],
             "disjoint": not c["intervals_overlap"],
             "champion": c["model"] == champ_key}
            for c in art["comparison"]
        ],
        "hero": {
            "overstatement": champ["overstatement"],
            "domain": [hero_lo - hero_pad, hero_hi + hero_pad],
            "clearAir": (
                [champ["temporal"]["hi"], champ["random"]["lo"]]
                if not champ["intervals_overlap"] else None
            ),
            "temporal": {k: champ["temporal"][k] for k in ("auc", "lo", "hi")},
            "random": {k: champ["random"][k] for k in ("auc", "lo", "hi")},
        },
        "decay": {
            "delta": art["performance"]["decay"]["delta"],
            "lo": art["performance"]["decay"]["lo"],
            "hi": art["performance"]["decay"]["hi"],
            "excludesZero": art["performance"]["decay"]["excludes_zero"],
            "validation": {k: champ_windows["validation"][k] for k in ("auc", "lo", "hi")},
            "test": {k: champ_windows["test"][k] for k in ("auc", "lo", "hi")},
        },
        "perModel": per_model,
        "operatingPoints": [
            {"rejectRate": o["reject_rate"], "threshold": o["threshold"],
             "nRejected": o["n_rejected"], "precision": o["precision"],
             "recall": o["recall"], "approvedBadRate": o["approved_bad_rate"]}
            for o in art["performance"]["per_model"][champ_key]["test"]["operating_points"]
        ],
        "calibration": {
            "variants": variants,
            "fittedOn": cal["fitted_on"],
            "aucUnchanged": cal["auc_unchanged"],
            "reliability": reliability,
            "reliabilityDomain": [
                0, max(p[0] for p in rel_bounds) * 1.06,
                0, max(p[1] for p in rel_bounds) * 1.08,
            ],
        },
        "subgroups": {
            "blocks": [
                {
                    "dimension": block["dimension"].replace("_", " "),
                    "note": subgroup_note(block, sg["widest_gap"], sg["min_group"]),
                    "levels": [
                        {"level": r["level"], "n": r["n"], "badRate": r["bad_rate"],
                         "auc": r["auc"], "lo": r["lo"], "hi": r["hi"]}
                        for r in block["levels"] if not r["too_small"] and r.get("auc") is not None
                    ],
                }
                for block in sg["analysis"]
            ],
            "domain": [min(bounds) - pad, max(bounds) + pad],
            "minGroup": sg["min_group"],
            "levels": n_levels,
            "scored": n_scored,
            "widestGap": {
                "dimension": sg["widest_gap"]["dimension"],
                "gap": sg["widest_gap"]["gap"],
                "best": sg["widest_gap"]["best_auc"],
                "worst": sg["widest_gap"]["worst_auc"],
                "bestLevel": sg["widest_gap"]["best_level"],
                "worstLevel": sg["widest_gap"]["worst_level"],
                "overlapping": sg["widest_gap"]["overlapping_intervals"],
            },
        },
        "coefficients": [[c["feature"], c["estimated"], c["true"]] for c in art["coefficients"]],
        "dataDictionary": gen.DATA_DICTIONARY,
        "driftSchedule": drift_schedule(art["truth"]),
        "sampleRows": sample,
        "cohorts": cohorts,
        "policy": {
            "referenceGrid": pol["reference_grid"],
            "testGrid": pol["test_grid"],
            "presets": pol["presets"],
            "presetRates": pol["preset_rates"],
            "defaults": pol["defaults"],
            "referenceLabel": pol["reference_label"],
            "testLabel": pol["test_label"],
            "referenceN": pol["reference_n"],
            "testN": pol["test_n"],
            "stale": {
                "profitGap": pol["stale"]["profit_gap"],
                "profitGapPct": pol["stale"]["profit_gap_pct"],
                "profitGapLabel": money(pol["stale"]["profit_gap"]),
            },
        },
        "figures": {
            "alerts": str(len(alerts)),
            "decay": f"{art['performance']['decay']['delta']:+.3f}",
            "calibrationSlope": f"{cal['variants']['raw']['slope']:.3f}",
            "worstPsi": f"{worst_psi:.2f}",
            "widestGap": f"{sg['widest_gap']['gap']:.3f}",
            "staleCost": money(pol["stale"]["profit_gap"]),
            "staleCostPct": f"{pol['stale']['profit_gap_pct'] * 100:.1f}%",
            "testAuc": f"{champ['temporal']['auc']:.3f}",
            "controlAlerts": f"{len(d['control']['alerts'])} alerts",
        },
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
