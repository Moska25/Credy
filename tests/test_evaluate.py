"""Metrics, bootstrap intervals and calibration.

The AUC implementation is checked against sklearn rather than against itself,
and the calibration metrics are checked against input whose correct answer is
known by construction.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score

from app import evaluate as ev


def test_auc_matches_sklearn_including_ties():
    rng = np.random.default_rng(1)
    y = (rng.random(5_000) < 0.3).astype(float)
    s = rng.random(5_000)
    assert abs(ev.auc(y, s) - roc_auc_score(y, s)) < 1e-10
    # heavy ties: scores rounded to 1 decimal place
    tied = np.round(s, 1)
    assert abs(ev.auc(y, tied) - roc_auc_score(y, tied)) < 1e-10


def test_auc_of_a_perfect_and_a_useless_score():
    y = np.array([0.0, 0, 0, 1, 1, 1] * 50)
    assert ev.auc(y, y) == 1.0
    assert abs(ev.auc(y, np.zeros_like(y)) - 0.5) < 1e-12


def test_gini_is_the_auc_transform():
    rng = np.random.default_rng(2)
    y = (rng.random(2_000) < 0.2).astype(float)
    s = rng.random(2_000)
    assert abs(ev.gini(y, s) - (2 * ev.auc(y, s) - 1)) < 1e-12


def test_ks_is_bounded_and_maximal_for_perfect_separation():
    y = np.array([0.0] * 500 + [1.0] * 500)
    assert 0.0 <= ev.ks(y, np.random.default_rng(3).random(1_000)) <= 1.0
    assert ev.ks(y, y) > 0.99


def test_brier_and_log_loss_hand_computed():
    y = np.array([1.0, 0.0])
    p = np.array([0.75, 0.25])
    assert abs(ev.brier(y, p) - 0.0625) < 1e-12  # ((0.25)^2 + (0.25)^2)/2
    expected = -(np.log(0.75) + np.log(0.75)) / 2
    assert abs(ev.log_loss(y, p) - expected) < 1e-12


def test_bootstrap_interval_contains_the_point_estimate():
    rng = np.random.default_rng(4)
    s = rng.random(4_000)
    y = (rng.random(4_000) < 0.2 + 0.4 * s).astype(float)
    out = ev.bootstrap_auc(y, s, n_boot=500, seed=1)
    assert out["lo"] < out["auc"] < out["hi"]
    assert out["n_boot"] == 500
    assert abs(out["gini"] - (2 * out["auc"] - 1)) < 1e-12


def test_bootstrap_interval_widens_with_fewer_samples():
    rng = np.random.default_rng(5)
    s = rng.random(8_000)
    y = (rng.random(8_000) < 0.2 + 0.4 * s).astype(float)
    wide = ev.bootstrap_auc(y[:800], s[:800], n_boot=500, seed=2)
    narrow = ev.bootstrap_auc(y, s, n_boot=500, seed=2)
    assert (wide["hi"] - wide["lo"]) > 2 * (narrow["hi"] - narrow["lo"])


def test_bootstrap_is_deterministic_for_a_fixed_seed():
    rng = np.random.default_rng(6)
    s = rng.random(2_000)
    y = (rng.random(2_000) < 0.3).astype(float)
    a = ev.bootstrap_auc(y, s, n_boot=200, seed=9)
    b = ev.bootstrap_auc(y, s, n_boot=200, seed=9)
    assert (a["lo"], a["hi"]) == (b["lo"], b["hi"])


def test_auc_difference_interval_detects_a_real_gap_and_ignores_a_fake_one():
    rng = np.random.default_rng(7)
    s_good = rng.random(6_000)
    y_good = (rng.random(6_000) < 0.05 + 0.8 * s_good).astype(float)
    s_bad = rng.random(6_000)
    y_bad = (rng.random(6_000) < 0.05 + 0.15 * s_bad).astype(float)

    real = ev.bootstrap_auc_difference(y_good, s_good, y_bad, s_bad, n_boot=400)
    assert real["excludes_zero"] and real["delta"] > 0

    half = len(y_good) // 2
    fake = ev.bootstrap_auc_difference(
        y_good[:half], s_good[:half], y_good[half:], s_good[half:], n_boot=400
    )
    assert not fake["excludes_zero"], "two halves of the same sample must not differ"


def test_calibration_is_perfect_on_perfectly_calibrated_input(calibrated_input):
    p, y = calibrated_input
    out = ev.calibration_slope_intercept(y, p)
    assert abs(out["slope"] - 1.0) < 0.05
    assert abs(out["intercept"]) < 0.05


def test_calibration_slope_falls_when_the_score_is_over_spread(calibrated_input):
    """Stretching the logit makes the model over-confident: slope must drop below 1."""
    p, y = calibrated_input
    stretched = 1 / (1 + np.exp(-1.8 * np.log(p / (1 - p))))
    assert ev.calibration_slope_intercept(y, stretched)["slope"] < 0.75


def test_calibration_intercept_rises_when_risk_is_under_predicted(calibrated_input):
    p, y = calibrated_input
    halved = p / 2
    assert ev.calibration_slope_intercept(y, halved)["intercept"] > 0.3


def test_reliability_curve_tracks_the_diagonal_when_calibrated(calibrated_input):
    p, y = calibrated_input
    bins = ev.reliability(y, p, bins=10)
    assert len(bins) == 10
    assert all(b["n"] > 0 for b in bins)
    deviations = [abs(b["mean_pred"] - b["observed"]) for b in bins]
    assert max(deviations) < 0.02, "a calibrated forecast must sit on the diagonal"
    # At 95% coverage roughly one bin in twenty is expected to fall outside its
    # own interval by chance, so require most of them rather than all of them.
    inside = sum(1 for b in bins if b["lo"] <= b["mean_pred"] <= b["hi"])
    assert inside >= 8, f"only {inside}/10 bins within their observed interval"


def test_brier_decomposition_reconstructs_the_brier_score(calibrated_input):
    p, y = calibrated_input
    d = ev.brier_decomposition(y, p, bins=10)
    reconstructed = d["reliability"] - d["resolution"] + d["uncertainty"] + d["binning_residual"]
    assert abs(reconstructed - d["brier"]) < 1e-12
    assert abs(d["binning_residual"]) < 0.005, "10 quantile bins should leave a tiny residual"
    assert d["reliability"] < 0.001, "a calibrated forecast has near-zero reliability penalty"


def test_recalibration_improves_the_calibration_slope(calibrated_input):
    """Platt scaling fitted on one half must fix a broken slope on the other."""
    p, y = calibrated_input
    broken = 1 / (1 + np.exp(-2.2 * np.log(p / (1 - p)) - 0.8))
    half = len(y) // 2
    before = ev.calibration_slope_intercept(y[half:], broken[half:])
    platt = ev.fit_platt(y[:half], broken[:half])
    after = ev.calibration_slope_intercept(y[half:], platt(broken[half:]))
    assert abs(after["slope"] - 1) < abs(before["slope"] - 1)
    assert abs(after["intercept"]) < abs(before["intercept"])
    assert ev.brier(y[half:], platt(broken[half:])) < ev.brier(y[half:], broken[half:])


def test_recalibration_cannot_change_the_ranking(calibrated_input):
    p, y = calibrated_input
    half = len(y) // 2
    platt = ev.fit_platt(y[:half], p[:half])
    assert abs(ev.auc(y[half:], platt(p[half:])) - ev.auc(y[half:], p[half:])) < 1e-9


def test_isotonic_also_recalibrates(calibrated_input):
    p, y = calibrated_input
    broken = np.clip(p * 0.4, 1e-6, 1 - 1e-6)
    half = len(y) // 2
    iso = ev.fit_isotonic(y[:half], broken[:half])
    fixed = iso(broken[half:])
    assert abs(np.mean(fixed) - np.mean(y[half:])) < abs(np.mean(broken[half:]) - np.mean(y[half:]))


def test_operating_points_are_monotone_in_reject_rate(fitted):
    idx = fitted["split"]["test"]
    ops = ev.operating_points(fitted["y"][idx], fitted["scores"]["hgb"][idx])
    assert [o["reject_rate"] for o in ops] == ev.REJECT_RATES
    recalls = [o["recall"] for o in ops]
    assert recalls == sorted(recalls), "declining more applications must catch more defaulters"
    thresholds = [o["threshold"] for o in ops]
    assert thresholds == sorted(thresholds, reverse=True)


def test_monthly_metrics_cover_every_cohort(fitted):
    rows = ev.monthly_metrics(fitted["months"], fitted["y"], fitted["scores"]["hgb"], n_boot=100)
    assert [r["month"] for r in rows] == sorted(set(fitted["months"].tolist()))
    assert all(r["n"] > 0 for r in rows)
    assert all(np.isfinite(r["auc"]) for r in rows)
