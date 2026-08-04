"""The generator: determinism, the drift switches, and that the injected drift
is actually present in the data rather than only in the docstring."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app import generate as gen


def test_generator_is_deterministic_under_a_fixed_seed():
    a = gen.generate(n=2_400, seed=7)
    b = gen.generate(n=2_400, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_a_different_seed_gives_different_data():
    a = gen.generate(n=2_400, seed=7)
    b = gen.generate(n=2_400, seed=8)
    assert not a["true_pd"].equals(b["true_pd"])
    # ...but the same shape and columns, so downstream code is seed-agnostic.
    assert a.shape == b.shape
    assert list(a.columns) == list(b.columns)


def test_every_month_is_populated_and_ids_are_unique(small_df):
    assert sorted(small_df["month"].unique().tolist()) == list(range(1, gen.N_MONTHS + 1))
    assert small_df["applicant_id"].is_unique
    counts = small_df["month"].value_counts()
    assert counts.max() - counts.min() <= 1


def test_covariate_shift_moves_income_down_only_when_enabled():
    on = gen.generate(n=9_600, seed=7, drift={**gen.DRIFT_ALL_OFF, "covariate_shift": True})
    off = gen.generate(n=9_600, seed=7, drift=gen.DRIFT_ALL_OFF)
    # Pool half-years rather than single months: a 400-row monthly median moves
    # several percent on noise alone, which would make this test flaky.
    half = lambda df, lo, hi: df.loc[df["month"].between(lo, hi), "income"].median()
    assert half(on, 19, 24) < half(on, 1, 6) * 0.85, "income should have slid down by month 24"
    ratio = half(off, 19, 24) / half(off, 1, 6)
    assert 0.97 < ratio < 1.03, f"no shift expected with the switch off, got {ratio:.3f}"


def test_prior_shift_raises_the_base_rate_only_when_enabled():
    on = gen.generate(n=19_200, seed=7, drift={**gen.DRIFT_ALL_OFF, "prior_shift": True})
    off = gen.generate(n=19_200, seed=7, drift=gen.DRIFT_ALL_OFF)
    assert on.loc[on["month"] >= 19, "default"].mean() > on.loc[on["month"] <= 12, "default"].mean()
    late, early = off.loc[off["month"] >= 19, "default"].mean(), off.loc[off["month"] <= 12, "default"].mean()
    assert abs(late - early) < 0.02, "base rate should be flat with prior shift off"


def test_concept_drift_flips_the_broker_coefficient():
    drift = {**gen.DRIFT_ALL_OFF, "concept_drift": True}
    early = gen.broker_coef(1, drift)
    late = gen.broker_coef(gen.N_MONTHS, drift)
    assert early < 0 < late, "the broker effect must genuinely change sign"
    assert gen.broker_coef(gen.CONCEPT_START - 1, drift) == early, "no movement before the start month"
    assert gen.broker_coef(1, gen.DRIFT_ALL_OFF) == gen.broker_coef(24, gen.DRIFT_ALL_OFF)


def test_concept_drift_shows_up_in_realised_broker_default_rates():
    df = gen.generate(n=19_200, seed=7, drift={**gen.DRIFT_ALL_OFF, "concept_drift": True})
    broker = df[df["channel"] == "broker"]
    other = df[df["channel"] != "broker"]
    early_lift = broker.loc[broker["month"] <= 12, "default"].mean() - other.loc[other["month"] <= 12, "default"].mean()
    late_lift = broker.loc[broker["month"] >= 22, "default"].mean() - other.loc[other["month"] >= 22, "default"].mean()
    assert early_lift < 0, "broker was the safer channel early on"
    assert late_lift > 0, "broker must become the riskier channel late in the window"


def test_quality_drift_spikes_tenure_missingness_in_the_last_quarter():
    df = gen.generate(n=9_600, seed=7, drift={**gen.DRIFT_ALL_OFF, "quality_drift": True})
    before = df.loc[df["month"] < gen.QUALITY_START, "employment_tenure"].isna().mean()
    after = df.loc[df["month"] >= gen.QUALITY_START, "employment_tenure"].isna().mean()
    assert before < 0.08
    assert after > 0.20
    clean = gen.generate(n=9_600, seed=7, drift=gen.DRIFT_ALL_OFF)
    assert clean.loc[clean["month"] >= gen.QUALITY_START, "employment_tenure"].isna().mean() < 0.08


def test_missingness_is_informative_not_random(small_df):
    """Applicants with no income figure default more, by construction."""
    missing = small_df.loc[small_df["income"].isna(), "default"].mean()
    present = small_df.loc[small_df["income"].notna(), "default"].mean()
    assert missing > present


def test_true_pd_is_a_probability_and_drives_the_label(small_df):
    assert small_df["true_pd"].between(0, 1).all()
    # The realised rate must track the mean true probability closely at this n.
    assert abs(small_df["default"].mean() - small_df["true_pd"].mean()) < 0.01


def test_credit_history_never_exceeds_adult_years(small_df):
    have = small_df.dropna(subset=["credit_history_years"])
    assert (have["credit_history_years"] <= have["age"] - 18).all()


def test_dgp_truth_records_the_switches_and_schedule():
    truth = gen.dgp_truth()
    assert truth["drift_switches"] == gen.DRIFT_ALL_ON
    schedule = truth["schedule"]
    assert schedule["concept_drift"]["coef_month_1"] < 0 < schedule["concept_drift"]["coef_month_24"]
    assert schedule["quality_drift"]["missing_rate_after"] > schedule["quality_drift"]["missing_rate_before"]
    assert truth["splits"]["train"] == list(gen.TRAIN_MONTHS) or truth["splits"]["train"] == gen.TRAIN_MONTHS
