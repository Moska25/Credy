"""Shared fixtures.

The heavy fixture runs a genuine miniature version of the seed pipeline - a real
generation, a real temporal split, real fits - on 9,600 rows instead of 40,000.
That keeps the suite under about half a minute while still testing the code that
actually ships, rather than a mock of it.
"""

from __future__ import annotations

import numpy as np
import pytest

from app import generate as gen, models

SMALL_N = 9_600


@pytest.fixture(scope="session")
def small_df():
    return gen.generate(n=SMALL_N, seed=7)


@pytest.fixture(scope="session")
def fitted(small_df):
    """Temporal split, three fitted models, and scores for every row."""
    split = models.temporal_split(small_df)
    fits = models.fit_all(small_df, split["train"])
    scores = models.predict_all(fits, small_df)
    return {
        "df": small_df,
        "split": split,
        "models": fits,
        "scores": scores,
        "y": small_df["default"].to_numpy(dtype=float),
        "months": small_df["month"].to_numpy(),
    }


@pytest.fixture(scope="session")
def calibrated_input():
    """A perfectly calibrated (score, outcome) pair, by construction.

    Draw p uniformly, then draw y ~ Bernoulli(p). Any calibration metric applied
    to this must report slope 1 and intercept 0 up to sampling noise.
    """
    rng = np.random.default_rng(0)
    p = rng.uniform(0.01, 0.60, size=60_000)
    y = (rng.random(60_000) < p).astype(float)
    return p, y
