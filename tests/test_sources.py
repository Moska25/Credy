"""Adapter-layer tests.

The adapters exist to stop two specific silent corruptions: a missing column
reaching `models.design_matrix` as an anonymous KeyError, and an unresolved
loan being labelled good. Both are tested here against real column vocabularies
written into small fixtures, because neither public dataset is vendored.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app import generate as gen, models, sources
from app.sources import home_credit, lending_club


# ---------------------------------------------------------------------------
# CRD-8.1  schema and registry
# ---------------------------------------------------------------------------
def test_synthetic_source_matches_the_generator_and_feeds_the_model():
    df = sources.load("synthetic", n=600, seed=3)
    for col in sources.REQUIRED_COLUMNS:
        assert col in df.columns, col
    # The real contract: whatever load() returns must go straight into the
    # modelling pipeline without a shim.
    x = models.design_matrix(df)
    assert x.shape == (len(df), len(models.FEATURE_NAMES))
    assert df.attrs["source"]["name"] == "synthetic"
    assert df.attrs["source"]["rows"] == len(df)


def test_synthetic_source_reports_full_coverage():
    df = sources.load("synthetic", n=600, seed=3)
    cov = df.attrs["source"]["coverage"]
    assert cov["age"] == 1.0 and cov["region"] == 1.0 and cov["channel"] == 1.0
    # income and employment_tenure carry deliberate missingness in the DGP.
    assert 0.5 < cov["income"] < 1.0


def test_missing_column_raises_a_named_schema_error_not_a_keyerror():
    df = gen.generate(n=200, seed=1).drop(columns=["debt_ratio"])
    with pytest.raises(sources.SchemaError) as e:
        sources.check(df, "broken")
    msg = str(e.value)
    assert "debt_ratio" in msg and "broken" in msg
    # And it must fail here rather than deep inside the design matrix.
    with pytest.raises(KeyError):
        models.design_matrix(df)


def test_unresolved_label_is_rejected():
    df = gen.generate(n=200, seed=1)
    df.loc[df.index[:5], "default"] = 2
    with pytest.raises(sources.SchemaError, match="outside"):
        sources.check(df, "broken")


def test_non_positive_month_is_rejected():
    df = gen.generate(n=200, seed=1)
    df.loc[df.index[0], "month"] = 0
    with pytest.raises(sources.SchemaError, match="month"):
        sources.check(df, "broken")


def test_unmapped_categorical_level_is_rejected_because_one_hot_hides_it():
    """An unmapped level encodes as an all-zero row, so it must fail loudly."""
    df = gen.generate(n=200, seed=1)
    df.loc[df.index[0], "channel"] = "telesales"
    with pytest.raises(sources.SchemaError, match="telesales"):
        sources.check(df, "broken")
    # The reason it matters: design_matrix does not complain, it just zeroes.
    row = models.design_matrix(df)[0]
    channel_cols = [i for i, n in enumerate(models.FEATURE_NAMES) if n.startswith("channel=")]
    assert row[channel_cols].sum() == 0.0


def test_unknown_source_name_is_rejected():
    with pytest.raises(sources.SchemaError, match="unknown source"):
        sources.load("equifax")


# ---------------------------------------------------------------------------
# CRD-8.2  Home Credit
# ---------------------------------------------------------------------------
def _home_credit_fixture(path, with_date=True):
    rows = {
        "SK_ID_CURR": [100001, 100002, 100003, 100004],
        "TARGET": [0, 1, 0, 0],
        "DAYS_BIRTH": [-14600, -9125, -20075, -12775],          # 40, 25, 55, 35 years
        "AMT_INCOME_TOTAL": [180000.0, 90000.0, 250000.0, 135000.0],
        "NAME_INCOME_TYPE": ["Working", "Commercial associate", "Pensioner", "Unemployed"],
        "DAYS_EMPLOYED": [-2190, -365, 365243, 365243],          # 6y, 1y, sentinel, sentinel
        "AMT_ANNUITY": [24000.0, 13500.0, 20000.0, 9000.0],
        "AMT_CREDIT": [480000.0, 270000.0, 300000.0, 108000.0],
        "NAME_CONTRACT_TYPE": ["Cash loans", "Cash loans", "Revolving loans", "Cash loans"],
    }
    if with_date:
        rows["APPLICATION_DATE"] = ["2017-03-14", "2017-03-30", "2017-05-02", "2017-07-19"]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_home_credit_maps_onto_the_schema_and_derives_a_cohort(tmp_path):
    path = _home_credit_fixture(tmp_path / "application_train.csv")
    df = sources.load("home_credit", path=str(path), date_column="APPLICATION_DATE")

    assert list(df["month"]) == [1, 1, 3, 5]          # Mar, Mar, May, Jul 2017
    assert df["age"].round().tolist() == [40.0, 25.0, 55.0, 35.0]
    assert df["employment_type"].tolist() == ["salaried", "salaried", "unemployed", "unemployed"]
    # The 365243 sentinel must never survive as tenure.
    assert df["employment_tenure"].max() < 100
    assert df.loc[2, "employment_tenure"] == 0.0
    # Revolving credit has no term; it is left null rather than guessed.
    assert np.isnan(df.loc[2, "term_months"])
    assert df.attrs["source"]["coverage"]["region"] == 0.0
    assert df.attrs["source"]["coverage"]["age"] == 1.0


def test_home_credit_refuses_to_invent_a_time_axis(tmp_path):
    """The public file is anonymised and has no application date at all."""
    path = _home_credit_fixture(tmp_path / "application_train.csv", with_date=False)
    with pytest.raises(sources.SchemaError) as e:
        sources.load("home_credit", path=str(path))
    assert "no application date" in str(e.value)
    assert "fabricate" in str(e.value)


def test_home_credit_rejects_a_file_that_is_not_home_credit(tmp_path):
    path = tmp_path / "other.csv"
    pd.DataFrame({"a": [1], "b": [2]}).to_csv(path, index=False)
    with pytest.raises(sources.SchemaError, match="does not look like"):
        sources.load("home_credit", path=str(path), date_column="a")


# ---------------------------------------------------------------------------
# CRD-8.3  Lending Club and the performance window
# ---------------------------------------------------------------------------
def _lending_club_fixture(path):
    #  A: old, resolved bad          -> kept, default 1
    #  B: old, resolved good         -> kept, default 0
    #  C: recent, still Current      -> immature, excluded (NOT labelled good)
    #  D: matured, still Current     -> no terminal status, excluded
    #  E: recent, already charged off-> resolved, kept even though immature
    pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "issue_d": ["Jan-2015", "Feb-2015", "Nov-2018", "Jan-2015", "Oct-2018"],
            "term": [" 36 months", " 36 months", " 36 months", " 36 months", " 60 months"],
            "loan_amnt": [10000, 8000, 12000, 5000, 20000],
            "annual_inc": [60000, 45000, 90000, 30000, 120000],
            "dti": [18.4, 22.1, 9.7, 31.0, 14.2],
            "emp_length": ["10+ years", "3 years", "1 year", "5 years", "8 years"],
            "delinq_2yrs": [0, 1, 0, 2, 0],
            "loan_status": ["Charged Off", "Fully Paid", "Current", "Current", "Charged Off"],
        }
    ).to_csv(path, index=False)
    return path


def test_lending_club_excludes_immature_loans_instead_of_labelling_them_good(tmp_path):
    path = _lending_club_fixture(tmp_path / "accepted.csv")
    df = sources.load("lending_club", path=str(path), as_of="2019-01-01")

    kept = sorted(df["applicant_id"].tolist())
    assert kept == [1, 2, 5], "only resolved outcomes may become labels"
    assert 3 not in kept, "a Current loan issued two months ago is not a good loan"
    assert 4 not in kept, "a matured loan with no terminal status carries no usable label"

    report = df.attrs["source"]
    assert report["excluded"] == 2
    assert any("immature" in n for n in report["notes"])
    assert any("never labelled good" in n for n in report["notes"])


def test_lending_club_labels_and_units_are_right(tmp_path):
    path = _lending_club_fixture(tmp_path / "accepted.csv")
    df = sources.load("lending_club", path=str(path), as_of="2019-01-01").set_index("applicant_id")

    assert df.loc[1, "default"] == 1 and df.loc[2, "default"] == 0
    # dti is a percent in the file and a ratio in the schema.
    assert df.loc[1, "debt_ratio"] == pytest.approx(0.184)
    assert df.loc[1, "term_months"] == 36 and df.loc[5, "term_months"] == 60
    # Cohorts are numbered from the earliest issue month kept, not from the file.
    assert df.loc[1, "month"] == 1 and df.loc[2, "month"] == 2
    assert df.loc[5, "month"] == 46          # Jan-2015 to Oct-2018
    assert df["age"].isna().all(), "this extract carries no applicant age"
    assert (df["employment_type"] == sources.UNKNOWN).all()


def test_lending_club_rejects_a_file_that_is_not_lending_club(tmp_path):
    path = tmp_path / "other.csv"
    pd.DataFrame({"a": [1], "b": [2]}).to_csv(path, index=False)
    with pytest.raises(sources.SchemaError, match="does not look like"):
        sources.load("lending_club", path=str(path))
