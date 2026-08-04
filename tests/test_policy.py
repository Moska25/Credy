"""Policy economics, checked against numbers computed by hand.

The arithmetic is the part of this repo most likely to be quietly wrong, and it
is the part a reader will trust most, so it gets worked examples.
"""

from __future__ import annotations

import numpy as np

from app import policy, subgroups


# A tiny book with an obvious answer.
#   applicant:   A     B     C     D
#   score:      0.02  0.05  0.20  0.40
#   default:     0     1     0     1
#   loan:       1000  2000  3000  4000
SCORES = np.array([0.02, 0.05, 0.20, 0.40])
Y = np.array([0.0, 1.0, 0.0, 1.0])
LOAN = np.array([1000.0, 2000.0, 3000.0, 4000.0])


def test_expected_loss_matches_a_hand_computation():
    """Threshold 0.10 approves A and B. B defaults on 2000 at lgd 0.5 -> 1000."""
    out = policy.outcomes(SCORES, Y, LOAN, threshold=0.10, lgd=0.5, margin=0.10, fr_cost=100.0)
    assert out["n_approved"] == 2
    assert out["approval_rate"] == 0.5
    assert out["n_approved_bad"] == 1
    assert out["principal_bad"] == 2000.0
    assert out["principal_good"] == 1000.0
    assert out["expected_loss"] == 1000.0  # 0.5 * 2000


def test_profit_matches_a_hand_computation():
    """revenue 0.10*1000 = 100; loss 0.5*2000 = 1000; C declined and good -> 100.
    profit = 100 - 1000 - 100 = -1000."""
    out = policy.outcomes(SCORES, Y, LOAN, threshold=0.10, lgd=0.5, margin=0.10, fr_cost=100.0)
    assert out["revenue"] == 100.0
    assert out["opportunity_cost"] == 100.0  # exactly one good applicant declined (C)
    assert out["n_rejected_good"] == 1
    assert out["profit"] == -1000.0


def test_approving_everyone_removes_the_opportunity_cost():
    out = policy.outcomes(SCORES, Y, LOAN, threshold=0.99, lgd=0.5, margin=0.10, fr_cost=100.0)
    assert out["n_approved"] == 4
    assert out["opportunity_cost"] == 0.0
    assert out["expected_loss"] == 0.5 * 6000.0
    assert out["revenue"] == 0.10 * 4000.0


def test_approving_nobody_books_no_loss_and_all_the_opportunity_cost():
    out = policy.outcomes(SCORES, Y, LOAN, threshold=0.001, lgd=0.5, margin=0.10, fr_cost=100.0)
    assert out["n_approved"] == 0
    assert out["expected_loss"] == 0.0
    assert out["revenue"] == 0.0
    assert out["opportunity_cost"] == 200.0  # two good applicants (A and C)
    assert out["profit"] == -200.0


def test_grid_row_and_direct_computation_agree():
    grid = policy.grid(SCORES, Y, LOAN, thresholds=[0.10])
    row = policy.apply_economics(grid[0], lgd=0.5, margin=0.10, fr_cost=100.0)
    direct = policy.outcomes(SCORES, Y, LOAN, 0.10, lgd=0.5, margin=0.10, fr_cost=100.0)
    for key in ("n_approved", "approval_rate", "principal_good", "principal_bad",
                "revenue", "expected_loss", "opportunity_cost", "profit"):
        assert row[key] == direct[key], key


def test_grid_approval_rate_is_monotone_in_the_threshold(fitted):
    idx = fitted["split"]["test"]
    rows = policy.grid(
        fitted["scores"]["hgb"][idx],
        fitted["y"][idx],
        fitted["df"]["loan_amount"].to_numpy(dtype=float)[idx],
    )
    rates = [r["approval_rate"] for r in rows]
    assert rates == sorted(rates), "a looser threshold can never approve fewer applications"
    assert rates[0] < rates[-1]
    assert all(0.0 <= r <= 1.0 for r in rates)


def test_stricter_thresholds_book_a_lower_bad_rate(fitted):
    idx = fitted["split"]["test"]
    rows = [
        r
        for r in policy.grid(
            fitted["scores"]["hgb"][idx],
            fitted["y"][idx],
            fitted["df"]["loan_amount"].to_numpy(dtype=float)[idx],
        )
        if r["n_approved"] > 200
    ]
    assert rows[0]["approved_bad_rate"] < rows[-1]["approved_bad_rate"]


def test_presets_are_ordered_and_hit_their_target_approval_rate():
    rng = np.random.default_rng(21)
    ref = rng.beta(2, 20, size=20_000)
    presets = policy.preset_thresholds(ref)
    assert presets["conservative"] < presets["balanced"] < presets["growth"]
    for name, rate in policy.PRESET_APPROVAL_RATES.items():
        achieved = float((ref < presets[name]).mean())
        assert abs(achieved - rate) < 0.01, f"{name}: {achieved:.3f} vs target {rate}"


def test_optimal_threshold_maximises_profit():
    rng = np.random.default_rng(22)
    n = 8_000
    s = rng.beta(2, 20, size=n)
    y = (rng.random(n) < s).astype(float)
    loan = rng.uniform(1_000, 20_000, size=n)
    grid = policy.grid(s, y, loan)
    best = policy.optimal(grid)
    profits = [r["profit"] for r in policy.curve(grid)]
    assert best["profit"] == max(profits)
    assert 0.0 < best["threshold"] < 0.6


def test_stale_threshold_costs_money_when_the_population_deteriorates():
    """Same model, worse cohort: the optimum tightens and holding the old one hurts."""
    rng = np.random.default_rng(23)
    n = 8_000
    s_ref = rng.beta(2, 25, size=n)
    y_ref = (rng.random(n) < s_ref).astype(float)
    s_late = rng.beta(2, 12, size=n)  # riskier population
    y_late = (rng.random(n) < s_late * 1.6).astype(float)
    loan = rng.uniform(1_000, 20_000, size=n)

    ref_grid = policy.grid(s_ref, y_ref, loan)
    late_grid = policy.grid(s_late, y_late, loan)
    stale = policy.stale_threshold_cost(ref_grid, late_grid)
    assert stale["fresh_threshold"] < stale["stale_threshold"], "the optimum must tighten"
    assert stale["profit_gap"] > 0, "keeping the old cut-off must cost money"
    assert stale["approval_rate_fresh"] < stale["approval_rate_stale"]


def test_economics_parameters_actually_move_the_answer():
    grid = policy.grid(SCORES, Y, LOAN, thresholds=policy.GRID)
    cheap = policy.optimal(grid, lgd=0.1, margin=0.20, fr_cost=10.0)
    brutal = policy.optimal(grid, lgd=0.95, margin=0.02, fr_cost=10.0)
    assert brutal["threshold"] <= cheap["threshold"]


def test_subgroup_intervals_widen_as_cohorts_shrink(fitted):
    """Same population, smaller slice: the interval must get wider."""
    from app import evaluate as ev

    idx = fitted["split"]["test"]
    y, s = fitted["y"][idx], fitted["scores"]["hgb"][idx]
    big = ev.bootstrap_auc(y, s, n_boot=400, seed=31)
    small = ev.bootstrap_auc(y[:400], s[:400], n_boot=400, seed=31)
    assert (small["hi"] - small["lo"]) > (big["hi"] - big["lo"])


def test_subgroup_analysis_reports_sizes_and_skips_tiny_cohorts(fitted):
    idx = fitted["split"]["test"]
    out = subgroups.analyse(fitted["df"].iloc[idx], fitted["scores"]["hgb"][idx], n_boot=200)
    assert [b["dimension"] for b in out] == ["age_band", "employment_type", "region", "channel"]
    for block in out:
        assert block["levels"], block["dimension"]
        assert abs(sum(r["share"] for r in block["levels"]) - 1.0) < 1e-9
        for r in block["levels"]:
            if r["too_small"]:
                assert not np.isfinite(r["auc"]), "tiny cohorts must not be given a number"
            else:
                assert r["n"] >= subgroups.MIN_GROUP


def test_age_band_covers_the_whole_range():
    assert subgroups.age_band(18) == "18-25"
    assert subgroups.age_band(40) == "36-50"
    assert subgroups.age_band(78) == "66+"
