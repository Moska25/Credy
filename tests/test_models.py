"""Splits and models. The leakage test is the important one here."""

from __future__ import annotations

import numpy as np

from app import evaluate as ev, generate as gen, models


def test_temporal_split_has_no_leakage(small_df):
    split = models.temporal_split(small_df)
    months = small_df["month"].to_numpy()
    train_ids = set(small_df["applicant_id"].to_numpy()[split["train"]].tolist())
    test_ids = set(small_df["applicant_id"].to_numpy()[split["test"]].tolist())
    val_ids = set(small_df["applicant_id"].to_numpy()[split["validation"]].tolist())

    assert not (train_ids & test_ids), "no test row may appear in training"
    assert not (train_ids & val_ids)
    assert not (val_ids & test_ids)
    assert months[split["train"]].max() < months[split["validation"]].min()
    assert months[split["validation"]].max() < months[split["test"]].min()
    assert len(train_ids) + len(val_ids) + len(test_ids) == len(small_df)


def test_temporal_split_windows_match_the_declared_months(small_df):
    split = models.temporal_split(small_df)
    months = small_df["month"].to_numpy()
    assert months[split["train"]].min() == gen.TRAIN_MONTHS[0]
    assert months[split["train"]].max() == gen.TRAIN_MONTHS[1]
    assert months[split["test"]].min() == gen.TEST_MONTHS[0]
    assert months[split["test"]].max() == gen.TEST_MONTHS[1]


def test_random_split_matches_temporal_sizes_but_mixes_the_months(small_df):
    tsplit = models.temporal_split(small_df)
    sizes = {k: len(v) for k, v in tsplit.items()}
    rsplit = models.random_split(small_df, sizes)
    assert {k: len(v) for k, v in rsplit.items()} == sizes
    months = small_df["month"].to_numpy()
    # This is the whole point of the comparison: late months DO leak into training.
    assert months[rsplit["train"]].max() >= gen.TEST_MONTHS[0]
    assert len(set(rsplit["train"].tolist()) & set(rsplit["test"].tolist())) == 0


def test_random_split_is_deterministic(small_df):
    sizes = {k: len(v) for k, v in models.temporal_split(small_df).items()}
    a = models.random_split(small_df, sizes)
    b = models.random_split(small_df, sizes)
    assert np.array_equal(a["train"], b["train"])


def test_design_matrix_shape_and_missing_indicators(small_df):
    X = models.design_matrix(small_df)
    assert X.shape == (len(small_df), len(models.FEATURE_NAMES))
    i = models.FEATURE_NAMES.index("missing_income")
    assert np.array_equal(X[:, i].astype(bool), small_df["income"].isna().to_numpy())
    # NaN is preserved for the tree model to consume natively.
    j = models.FEATURE_NAMES.index("z_log_income")
    assert np.isnan(X[:, j]).sum() == int(small_df["income"].isna().sum())


def test_scorecard_is_a_real_baseline_not_a_strawman(fitted):
    """A hand-built points table must beat coin-flipping by a clear margin."""
    idx = fitted["split"]["test"]
    a = ev.auc(fitted["y"][idx], fitted["scores"]["scorecard"][idx])
    assert a > 0.60, f"scorecard AUC {a:.3f} is too weak to be an honest baseline"


def test_scorecard_points_penalise_the_documented_risk_drivers(small_df):
    """Same applicant, worse debt ratio, must score more risk points."""
    base = small_df.head(1).copy()
    base.loc[:, "debt_ratio"] = 0.10
    worse = base.copy()
    worse.loc[:, "debt_ratio"] = 0.80
    assert models.scorecard_points(worse)[0] > models.scorecard_points(base)[0]

    missing = base.copy()
    missing.loc[:, "income"] = np.nan
    assert models.scorecard_points(missing)[0] > models.scorecard_points(base)[0]


def test_all_three_models_produce_valid_probabilities(fitted):
    for name, s in fitted["scores"].items():
        assert s.shape == (len(fitted["df"]),), name
        assert np.isfinite(s).all(), name
        assert ((s > 0) & (s < 1)).all(), name


def test_learned_models_beat_the_scorecard_on_the_test_window(fitted):
    idx = fitted["split"]["test"]
    base = ev.auc(fitted["y"][idx], fitted["scores"]["scorecard"][idx])
    hgb = ev.auc(fitted["y"][idx], fitted["scores"]["hgb"][idx])
    assert hgb > base


def test_random_split_overstates_performance(small_df):
    """The headline claim, asserted rather than asserted-in-prose."""
    y = small_df["default"].to_numpy(dtype=float)
    X = models.design_matrix(small_df)
    tsplit = models.temporal_split(small_df)
    rsplit = models.random_split(small_df, {k: len(v) for k, v in tsplit.items()})

    temporal = models.fit_hgb(X[tsplit["train"]], y[tsplit["train"]]).predict_proba(X)[:, 1]
    random_ = models.fit_hgb(X[rsplit["train"]], y[rsplit["train"]]).predict_proba(X)[:, 1]
    a_temporal = ev.auc(y[tsplit["test"]], temporal[tsplit["test"]])
    a_random = ev.auc(y[rsplit["test"]], random_[rsplit["test"]])
    assert a_random > a_temporal, (
        f"random split {a_random:.4f} should overstate temporal {a_temporal:.4f}"
    )


def test_logistic_coefficients_recover_the_uncorrelated_true_effects(fitted):
    """Signs and rough magnitudes on features that are not collinear."""
    est = models.logistic_coefficients(fitted["models"]["logistic"])
    checks = {
        "debt_ratio": gen.COEF["debt_ratio"],
        "prior_delinquencies": gen.COEF["prior_delinquencies"],
        "z_credit_history": gen.COEF["z_credit_history"],
        "z_age": gen.COEF["z_age"],
    }
    for name, truth in checks.items():
        assert np.sign(est[name]) == np.sign(truth), f"{name} recovered with the wrong sign"
        assert abs(est[name] - truth) < 0.6 * abs(truth) + 0.15, f"{name} off by too much"
