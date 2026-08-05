"""Drift detection. The load-bearing claim of the whole project is that these
functions fire on the drift the generator planted, so that is asserted directly.
"""

from __future__ import annotations

import numpy as np

from app import drift, evaluate as ev, generate as gen, models


def test_psi_is_zero_for_identical_distributions():
    rng = np.random.default_rng(11)
    x = rng.normal(size=20_000)
    assert drift.psi(x, x) < 1e-9


def test_psi_is_near_zero_for_two_draws_from_the_same_distribution():
    rng = np.random.default_rng(12)
    a = rng.normal(size=20_000)
    b = rng.normal(size=20_000)
    assert drift.psi(a, b) < 0.02


def test_psi_grows_with_the_size_of_the_shift():
    rng = np.random.default_rng(13)
    ref = rng.normal(size=20_000)
    values = [drift.psi(ref, rng.normal(loc=shift, size=20_000)) for shift in (0.1, 0.3, 0.6, 1.0)]
    assert values == sorted(values), "PSI must be monotone in shift size"
    assert values[0] < drift.PSI_WATCH < values[-1]
    assert values[-1] > drift.PSI_SHIFT


def test_psi_bands_use_the_conventional_cut_points():
    assert drift.band(0.05) == 0
    assert drift.band(0.15) == 1
    assert drift.band(0.40) == 2
    assert drift.band(float("nan")) == 0


def test_psi_handles_empty_bins_without_blowing_up():
    ref = np.concatenate([np.zeros(500), np.ones(500)])
    cur = np.zeros(500)
    value = drift.psi(ref, cur)
    assert np.isfinite(value) and value > drift.PSI_SHIFT


def test_categorical_psi_detects_a_mix_change():
    ref = ["a"] * 700 + ["b"] * 300
    same = ["a"] * 350 + ["b"] * 150
    shifted = ["a"] * 300 + ["b"] * 700
    assert drift.psi_categorical(ref, same) < 0.01
    assert drift.psi_categorical(ref, shifted) > drift.PSI_SHIFT


def test_jensen_shannon_is_bounded_and_zero_for_identical_inputs():
    p = np.array([0.25, 0.25, 0.5])
    assert abs(drift.js_divergence(p, p)) < 1e-12
    disjoint = drift.js_divergence(np.array([1.0, 0.0]), np.array([0.0, 1.0]))
    assert 0.99 < disjoint <= 1.0, "base-2 JSD of disjoint distributions is 1 bit"


def test_injected_income_drift_is_detectable_by_psi_and_absent_when_switched_off():
    on = gen.generate(n=19_200, seed=7, drift={**gen.DRIFT_ALL_OFF, "covariate_shift": True})
    off = gen.generate(n=19_200, seed=7, drift=gen.DRIFT_ALL_OFF)
    for df, expect_shift in ((on, True), (off, False)):
        ref = df.loc[df["month"] <= 12, "income"].to_numpy(dtype=float)
        late = df.loc[df["month"] == 24, "income"].to_numpy(dtype=float)
        value = drift.psi(ref, late)
        if expect_shift:
            assert value > drift.PSI_SHIFT, f"expected a shifted-band PSI, got {value:.3f}"
        else:
            assert value < drift.PSI_WATCH, f"expected a stable PSI, got {value:.3f}"


def test_missingness_monitor_finds_the_planted_data_quality_incident(small_df):
    miss = drift.missingness(small_df)
    assert "employment_tenure" in miss["features"]
    ref = miss["reference"]["employment_tenure"]
    late = miss["rates"]["employment_tenure"][gen.N_MONTHS]
    assert late - ref > drift.MISSINGNESS_JUMP


def test_feature_drift_table_covers_every_feature_and_month(small_df):
    table = drift.feature_drift(small_df)
    assert set(table["psi"]) == set(gen.FEATURES_ALL)
    assert table["months"] == list(range(1, gen.N_MONTHS + 1))
    # Reference months compared with themselves must be near zero.
    assert max(table["psi"]["debt_ratio"][m] for m in range(1, 13)) < 0.05


def test_alerts_name_the_month_trigger_value_and_action(fitted):
    monthly = ev.monthly_metrics(fitted["months"], fitted["y"], fitted["scores"]["hgb"], n_boot=100)
    miss = drift.missingness(fitted["df"])
    score_psi = drift.score_drift(fitted["df"], fitted["scores"]["hgb"])
    fired = drift.alerts(score_psi, monthly, miss)
    assert fired, "some rule must fire on a dataset with four injected drifts"
    for a in fired:
        assert a["month"] >= gen.VAL_MONTHS[0], "the reference window must not be alerted on"
        assert a["severity"] in ("high", "medium")
        assert np.isfinite(a["value"]) and np.isfinite(a["threshold"])
        assert a["action"] and a["message"]


def _run_alerts(df):
    y = df["default"].to_numpy(dtype=float)
    X = models.design_matrix(df)
    split = models.temporal_split(df)
    scores = models.fit_hgb(X[split["train"]], y[split["train"]]).predict_proba(X)[:, 1]
    monthly = ev.monthly_metrics(df["month"].to_numpy(), y, scores, n_boot=150)
    return drift.alerts(
        drift.score_drift(df, scores),
        monthly,
        drift.missingness(df),
        feature_psi=drift.feature_drift(df),
    )


def test_population_rules_are_silent_on_a_stationary_population():
    """The false-alarm side of the claim: no injected drift, no population alert."""
    clean = gen.generate(n=19_200, seed=7, drift=gen.DRIFT_ALL_OFF)
    fired = _run_alerts(clean)
    offenders = [a for a in fired if a["rule"] in ("feature_psi", "missingness_spike")]
    assert not offenders, f"population rules fired with no drift injected: {offenders}"


def test_outcome_rules_fire_far_more_often_with_drift_than_without():
    """Outcome-based rules are noisy on small cohorts, so the claim is relative.

    A fixed relative threshold does not adjust for cohort size, so a handful of
    false alarms on a stationary population is expected. What must hold is that
    the drifted population trips them far more often.
    """
    clean = gen.generate(n=19_200, seed=7, drift=gen.DRIFT_ALL_OFF)
    drifted = gen.generate(n=19_200, seed=7)
    count = lambda fired: sum(1 for a in fired if a["rule"] == "pd_gap")
    assert count(_run_alerts(drifted)) >= 3 * max(count(_run_alerts(clean)), 1)


def test_verification_scores_every_injected_drift(fitted):
    monthly = ev.monthly_metrics(fitted["months"], fitted["y"], fitted["scores"]["hgb"], n_boot=200)
    baseline = drift.early_production_baseline(
        fitted["months"], fitted["y"], fitted["scores"]["hgb"], n_boot=200
    )
    fired = drift.alerts(
        drift.score_drift(fitted["df"], fitted["scores"]["hgb"]),
        monthly,
        drift.missingness(fitted["df"]),
        feature_psi=drift.feature_drift(fitted["df"]),
        baseline=baseline,
    )
    verification = drift.verify_against_truth(fired, gen.dgp_truth())
    assert verification["verifiable"] is True
    rows = verification["rows"]
    assert len(rows) == 4
    assert all(r["enabled"] for r in rows)
    detected = [r for r in rows if r["detected"]]
    assert len(detected) >= 3, f"expected at least 3 of 4 drifts caught, got {len(detected)}"
    for r in detected:
        assert r["first_detected_month"] >= gen.VAL_MONTHS[0]


def test_verification_refuses_to_score_a_source_with_no_known_schedule():
    """A blank table would read as 'no drift was injected'. It must refuse instead."""
    for truth in (None, {}, {"schedule": {}}):
        out = drift.verify_against_truth([], truth)
        assert out["verifiable"] is False
        assert out["rows"] == []
        assert "known" in out["reason"].lower() and len(out["reason"]) > 60


def test_early_production_baseline_pools_the_first_out_of_sample_months(fitted):
    b = drift.early_production_baseline(
        fitted["months"], fitted["y"], fitted["scores"]["hgb"], window=3, n_boot=200
    )
    assert b["months"] == [gen.VAL_MONTHS[0], gen.VAL_MONTHS[0] + 2]
    assert b["lo"] < b["auc"] < b["hi"]
    per_month = int((fitted["months"] == gen.VAL_MONTHS[0]).sum())
    assert b["n"] > 2 * per_month, "the baseline must pool cohorts, not use one"
