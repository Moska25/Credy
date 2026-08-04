"""FastAPI routes. Thin on purpose: read precomputed artifacts, format, render.

No model is fitted here and no metric is computed here beyond arithmetic on the
precomputed policy grid, which is a handful of multiplications. That is what
keeps every page deterministic and fast.
"""

from __future__ import annotations

import math
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import charts, db, drift, generate as gen, models, policy

BASE_DIR = Path(__file__).resolve().parent

PROJECT_NAME = "Credy"
PROJECT_TAGLINE = "Credit risk and model stability lab"
NAV = [
    ("/", "Overview"),
    ("/performance", "Performance"),
    ("/calibration", "Calibration"),
    ("/drift", "Drift"),
    ("/subgroups", "Subgroups"),
    ("/policy", "Policy"),
    ("/model-card", "Model card"),
    ("/data", "Data"),
]

app = FastAPI(title=PROJECT_NAME, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_ART: dict = {}


def artifacts() -> dict:
    """Load every artifact once, on first use."""
    global _ART
    if not _ART:
        conn = db.connect()
        try:
            loaded = db.all_artifacts(conn)
        finally:
            conn.close()
        if not loaded:
            raise RuntimeError(
                "Credy is not seeded. Run:  ./.venv/bin/python -m app.seed   (or ./run.sh)"
            )
        _ART = loaded
    return _ART


# ---------------------------------------------------------------------------
# formatting helpers exposed to templates
# ---------------------------------------------------------------------------
def _bad(x) -> bool:
    return x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def fnum(x, places: int = 3) -> str:
    return "n/a" if _bad(x) else f"{x:,.{places}f}"


def fpct(x, places: int = 1) -> str:
    return "n/a" if _bad(x) else f"{x * 100:.{places}f}%"


def fsigned(x, places: int = 3) -> str:
    return "n/a" if _bad(x) else f"{x:+,.{places}f}"


def fmoney(x, places: int = 1) -> str:
    if _bad(x):
        return "n/a"
    sign = "-" if x < 0 else ""
    v = abs(x)
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if v >= cut:
            return f"{sign}{v / cut:,.{places}f}{suffix}"
    return f"{sign}{v:,.0f}"


def fci(d: dict, key: str = "auc", places: int = 3) -> str:
    if _bad(d.get(key)):
        return "n/a"
    lo, hi = d.get("lo"), d.get("hi")
    if _bad(lo) or _bad(hi):
        return fnum(d[key], places)
    return f"{d[key]:.{places}f}  [{lo:.{places}f}, {hi:.{places}f}]"


templates.env.filters.update(
    {"fnum": fnum, "fpct": fpct, "fsigned": fsigned, "fmoney": fmoney}
)
templates.env.globals.update(
    {
        "line_chart": charts.line_chart,
        "series": charts.series,
        "fci": fci,
        "fnum": fnum,
        "fpct": fpct,
        "fmoney": fmoney,
        "fsigned": fsigned,
        "psi_band": drift.band,
        "BAND_LABEL": drift.BAND_LABEL,
        "BAND_PILL": drift.BAND_PILL,
        "MODEL_LABELS": models.MODEL_LABELS,
        "isfinite": lambda x: not _bad(x),
        # JSON object keys come back as strings; templates index by int month.
        "mget": lambda d, k, default=None: d.get(str(k), d.get(k, default)),
    }
)


def page(request: Request, template: str, active: str, **ctx) -> HTMLResponse:
    art = artifacts()
    meta = art["meta"]
    base = {
        "request": request,
        "project_name": PROJECT_NAME,
        "project_tagline": PROJECT_TAGLINE,
        "nav": NAV,
        "active": active,
        "footer_note": (
            f"Synthetic data, {meta['rows']:,} applicants over {meta['months']} months. "
            f"Seeded once, read-only at request time."
        ),
        "meta": meta,
        "art": art,
    }
    base.update(ctx)
    return templates.TemplateResponse(request, template, base)


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    art = artifacts()
    champ = next(c for c in art["comparison"] if c["model"] == art["meta"]["champion"])
    alerts = art["drift"]["alerts"]
    monthly = art["performance"]["monthly"]
    return page(
        request,
        "index.html",
        "/",
        champ=champ,
        alerts=alerts,
        high_alerts=[a for a in alerts if a["severity"] == "high"],
        first_alert_month=min((a["month"] for a in alerts), default=None),
        verification=art["drift"]["verification"],
        monthly=monthly,
        score_psi=art["drift"]["score"],
        decay=art["performance"]["decay"],
        stale=art["policy"]["stale"],
    )


@app.get("/performance", response_class=HTMLResponse)
def performance(request: Request):
    art = artifacts()
    return page(
        request,
        "performance.html",
        "/performance",
        comparison=art["comparison"],
        per_model=art["performance"]["per_model"],
        monthly=art["performance"]["monthly"],
        decay=art["performance"]["decay"],
        bad_rate=art["bad_rate_by_month"],
    )


@app.get("/calibration", response_class=HTMLResponse)
def calibration(request: Request):
    art = artifacts()
    cal = art["calibration"]
    diag_max = max(
        (b["mean_pred"] for v in cal["variants"].values() for b in v["curve"]), default=1.0
    )
    return page(request, "calibration.html", "/calibration", cal=cal, diag_max=diag_max)


@app.get("/drift", response_class=HTMLResponse)
def drift_page(request: Request):
    art = artifacts()
    d = art["drift"]
    # Highlight the two features that moved most, chosen from the data rather
    # than hard-coded, so the chart stays correct if the DGP changes.
    ranked = sorted(d["feature"]["psi"].items(), key=lambda kv: -max(kv[1].values()))[:2]
    psi_lines = [
        charts.series(
            [{"month": int(m), "psi": v} for m, v in by_month.items()],
            "month",
            "psi",
            f"{feat} PSI",
            dots=True,
        )
        for feat, by_month in ranked
    ]
    return page(
        request,
        "drift.html",
        "/drift",
        d=d,
        features=gen.FEATURES_ALL,
        monitored_from=gen.VAL_MONTHS[0],
        psi_lines=psi_lines,
    )


@app.get("/subgroups", response_class=HTMLResponse)
def subgroups_page(request: Request):
    art = artifacts()
    sg = art["subgroups"]
    n_intervals = sum(
        1 for block in sg["analysis"] for r in block["levels"] if not r["too_small"]
    )
    return page(request, "subgroups.html", "/subgroups", sg=sg, n_intervals=n_intervals)


@app.get("/policy", response_class=HTMLResponse)
def policy_page(
    request: Request,
    threshold: float | None = None,
    lgd: float = policy.DEFAULTS["lgd"],
    margin: float = policy.DEFAULTS["margin"],
    fr_cost: float = policy.DEFAULTS["fr_cost"],
    preset: str = "",
):
    art = artifacts()
    p = art["policy"]
    if preset in p["presets"]:
        threshold = p["presets"][preset]
    if threshold is None:
        threshold = p["presets"]["balanced"]

    # Clamp inputs: this is a user-facing form, so validate at the boundary.
    threshold = min(max(float(threshold), 0.005), 0.60)
    econ = {
        "lgd": min(max(float(lgd), 0.0), 1.0),
        "margin": min(max(float(margin), 0.0), 1.0),
        "fr_cost": min(max(float(fr_cost), 0.0), 5000.0),
    }

    test_curve = policy.curve(p["test_grid"], **econ)
    ref_curve = policy.curve(p["reference_grid"], **econ)
    nearest = lambda curve: min(curve, key=lambda r: abs(r["threshold"] - threshold))
    chosen = nearest(test_curve)
    chosen_ref = nearest(ref_curve)
    best_test = max(test_curve, key=lambda r: r["profit"])
    best_ref = max(ref_curve, key=lambda r: r["profit"])
    stale = policy.stale_threshold_cost(p["reference_grid"], p["test_grid"], **econ)

    preset_rows = []
    for name, thr in p["presets"].items():
        row = min(test_curve, key=lambda r: abs(r["threshold"] - thr))
        preset_rows.append(
            {
                "name": name,
                "target_rate": p["preset_rates"][name],
                "threshold": thr,
                **{k: row[k] for k in ("approval_rate", "approved_bad_rate", "expected_loss", "profit")},
            }
        )

    return page(
        request,
        "policy.html",
        "/policy",
        p=p,
        econ=econ,
        threshold=threshold,
        chosen=chosen,
        chosen_ref=chosen_ref,
        best_test=best_test,
        best_ref=best_ref,
        stale=stale,
        test_curve=test_curve,
        ref_curve=ref_curve,
        preset_rows=preset_rows,
        active_preset=preset,
    )


@app.get("/model-card", response_class=HTMLResponse)
def model_card(request: Request):
    art = artifacts()
    return page(
        request,
        "model_card.html",
        "/model-card",
        per_model=art["performance"]["per_model"],
        cal=art["calibration"],
        truth=art["truth"],
        coefficients=art["coefficients"],
        alerts=art["drift"]["alerts"],
        sg=art["subgroups"],
        stale=art["policy"]["stale"],
    )


@app.get("/data", response_class=HTMLResponse)
def data_page(request: Request):
    art = artifacts()
    conn = db.connect()
    try:
        sample = [
            dict(r)
            for r in conn.execute(
                'SELECT applicant_id, month, age, income, employment_type, employment_tenure, '
                'debt_ratio, credit_history_years, prior_delinquencies, loan_amount, term_months, '
                'region, channel, true_pd, "default" FROM applicants '
                "WHERE applicant_id % 3571 = 0 ORDER BY applicant_id LIMIT 12"
            )
        ]
        counts = [
            dict(r)
            for r in conn.execute(
                'SELECT month, COUNT(*) AS n, AVG("default") AS bad_rate, '
                "AVG(COALESCE(income, 0) > 0) AS income_present "
                "FROM applicants GROUP BY month ORDER BY month"
            )
        ]
    finally:
        conn.close()
    return page(
        request,
        "data.html",
        "/data",
        dictionary=gen.DATA_DICTIONARY,
        sample=sample,
        counts=counts,
        truth=art["truth"],
        coefficients=art["coefficients"],
        bad_rate=art["bad_rate_by_month"],
    )
