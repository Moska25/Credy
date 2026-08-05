"""Hand-rolled inline SVG charts.

No chart library and no CDN: the pages must work with the machine offline, and
a few hundred lines of SVG generation is cheaper to reason about than a
dependency. Every chart gets axis labels with units, because a credit risk
number without its unit is a trap.

`line_chart` covers everything the site needs - AUC over time with a bootstrap
band, PSI over time, reliability curves, profit against threshold - so there is
one implementation to get right rather than five.
"""

from __future__ import annotations

import json
import math
from html import escape

from markupsafe import Markup

W, H = 760, 300
PAD = {"l": 56, "r": 16, "t": 16, "b": 46}
# Fallback series cycle for charts that do not name their colours. Chrome
# first, then ramp stops - never --pass/--warn/--fail, so a series can never
# accidentally pick up a colour that means a verdict elsewhere on the site.
PALETTE = ["var(--accent)", "var(--info)", "var(--heat-2)", "var(--heat-4)", "var(--heat-1)"]

# The one sequential heat ramp. Every risk and drift magnitude in the app -
# heatmap cells, alert severity, magnitude-bearing metric values, risk series -
# is encoded with these five stops and nothing else. Defined in app.css as
# --heat-0 .. --heat-4; referenced here by variable so SVG and CSS cannot drift
# apart.
HEAT = [f"var(--heat-{i})" for i in range(5)]

# Display cut-points for the PSI ramp. The upper two are the 0.10 / 0.25
# industry conventions; the lower two exist because a three-band step function
# at 0.10 hides everything happening underneath it, which on this population is
# most of the story.
PSI_HEAT_STOPS = (0.02, 0.05, 0.10, 0.25)


def heat_level(value: float | None, stops: tuple[float, ...] = PSI_HEAT_STOPS) -> int:
    """Map a magnitude onto a ramp stop index (0 = coldest).

    Presentation only: this chooses a colour, never a verdict. The stable /
    watch / shifted verdict stays in `drift.band`, which uses the conventional
    thresholds alone.
    """
    if not _ok(value):
        return 0
    return sum(1 for s in stops if value > s)


def _nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1.0
    step = (hi - lo) / (count - 1)
    return [lo + i * step for i in range(count)]


def _fmt(value: float, places: int) -> str:
    return f"{value:,.{places}f}"


def line_chart(
    series: list[dict],
    x_label: str,
    y_label: str,
    y_places: int = 2,
    x_places: int = 0,
    y_min: float | None = None,
    y_max: float | None = None,
    x_ticks: list[float] | None = None,
    height: int = H,
    ref_line: float | None = None,
    ref_label: str = "",
    v_line: float | None = None,
    v_label: str = "",
    diag_ref: bool = False,
    diag_label: str = "",
    legend: bool = True,
) -> Markup:
    """Multi-series line chart.

    series item: {name, points: [(x, y), ...], color?, dash?, band?: [(x, lo, hi)],
                  dots?: bool}
    """
    xs, ys = [], []
    for s in series:
        for x, y in s["points"]:
            xs.append(x)
            ys.append(y)
        for x, lo, hi in s.get("band", []):
            xs.append(x)
            ys.extend([lo, hi])
    if not xs:
        return Markup('<div class="empty">No data for this chart.</div>')

    x0, x1 = min(xs), max(xs)
    if x1 == x0:
        x1 = x0 + 1
    lo_y = min(ys) if y_min is None else y_min
    hi_y = max(ys) if y_max is None else y_max
    if ref_line is not None:
        lo_y, hi_y = min(lo_y, ref_line), max(hi_y, ref_line)
    if hi_y == lo_y:
        lo_y, hi_y = lo_y - 0.5, hi_y + 0.5
    span = hi_y - lo_y
    if y_min is None:
        lo_y -= span * 0.08
    if y_max is None:
        hi_y += span * 0.08

    # Size the left gutter to the widest y tick label instead of assuming one.
    # Profit in currency units runs to eight characters ("1,204,650") and a
    # fixed 56px pad clipped it to ",204,650" - a chart that misreports its own
    # axis is worse than no chart.
    y_ticks = _nice_ticks(lo_y, hi_y)
    label_w = max(len(_fmt(t, y_places)) for t in y_ticks) * 6.3
    pad_l = max(PAD["l"], 22 + label_w + 8)

    plot_w = W - pad_l - PAD["r"]
    plot_h = height - PAD["t"] - PAD["b"]
    sx = lambda x: pad_l + (x - x0) / (x1 - x0) * plot_w
    sy = lambda y: PAD["t"] + (hi_y - y) / (hi_y - lo_y) * plot_h

    out = [
        f'<svg viewBox="0 0 {W} {height}" width="{W}" height="{height}" '
        f'role="img" aria-label="{escape(y_label)} against {escape(x_label)}" '
        'preserveAspectRatio="xMidYMid meet" font-family="ui-monospace, monospace">'
    ]

    # Plotting well: a faint grid behind the data so the figure reads as an
    # instrument rather than a decoration.
    out.append(
        f'<rect x="{pad_l}" y="{PAD["t"]}" width="{plot_w}" height="{plot_h}" '
        'fill="var(--grid-bg)"/>'
    )

    # grid + y axis
    for t in y_ticks:
        y = sy(t)
        out.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            'stroke="var(--grid)" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{pad_l - 8}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10.5" '
            f'fill="var(--text-faint)">{escape(_fmt(t, y_places))}</text>'
        )

    # x axis ticks
    ticks = x_ticks if x_ticks is not None else _nice_ticks(x0, x1, 6)
    for t in ticks:
        x = sx(t)
        out.append(
            f'<line x1="{x:.1f}" y1="{PAD["t"]}" x2="{x:.1f}" y2="{PAD["t"] + plot_h}" '
            'stroke="var(--grid)" stroke-width="1"/>'
        )
        out.append(
            f'<line x1="{x:.1f}" y1="{PAD["t"] + plot_h}" x2="{x:.1f}" y2="{PAD["t"] + plot_h + 4}" '
            'stroke="var(--border-strong)" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{x:.1f}" y="{PAD["t"] + plot_h + 17}" text-anchor="middle" font-size="10.5" '
            f'fill="var(--text-faint)">{escape(_fmt(t, x_places))}</text>'
        )
    out.append(
        f'<line x1="{pad_l}" y1="{PAD["t"] + plot_h}" x2="{pad_l + plot_w}" '
        f'y2="{PAD["t"] + plot_h}" stroke="var(--border-strong)" stroke-width="1"/>'
    )

    if ref_line is not None:
        y = sy(ref_line)
        out.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            'stroke="var(--text-faint)" stroke-width="1" stroke-dasharray="5 4"/>'
        )
        if ref_label:
            out.append(
                f'<text x="{pad_l + plot_w - 4}" y="{y - 5:.1f}" text-anchor="end" font-size="10" '
                f'fill="var(--text-faint)">{escape(ref_label)}</text>'
            )

    if diag_ref:
        # y = x, clipped to whatever both axes actually cover. Drawn by the
        # chart rather than passed in as a fake two-point series so it can be
        # labelled along its own angle and kept out of the legend.
        d0, d1 = max(x0, lo_y), min(x1, hi_y)
        if d1 > d0:
            ax, ay, bx, by = sx(d0), sy(d0), sx(d1), sy(d1)
            # Everything above the line is a bin where more applicants defaulted
            # than the model expected; wash it so the direction of the error is
            # readable without counting points.
            out.append(
                f'<polygon points="{ax:.1f},{ay:.1f} {bx:.1f},{by:.1f} {bx:.1f},{PAD["t"]} '
                f'{ax:.1f},{PAD["t"]}" fill="var(--heat-4)" fill-opacity="0.07" stroke="none"/>'
            )
            out.append(
                f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                'stroke="var(--text-muted)" stroke-width="1.5" stroke-dasharray="6 4"/>'
            )
            if diag_label:
                mx, my = (ax + bx) / 2, (ay + by) / 2
                angle = math.degrees(math.atan2(by - ay, bx - ax))
                out.append(
                    f'<text x="{mx:.1f}" y="{my - 7:.1f}" text-anchor="middle" font-size="10.5" '
                    f'fill="var(--text-muted)" transform="rotate({angle:.2f} {mx:.1f} {my:.1f})">'
                    f"{escape(diag_label)}</text>"
                )

    if v_line is not None and x0 <= v_line <= x1:
        x = sx(v_line)
        out.append(
            f'<line x1="{x:.1f}" y1="{PAD["t"]}" x2="{x:.1f}" y2="{PAD["t"] + plot_h}" '
            'stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="4 4"/>'
        )
        if v_label:
            anchor = "end" if x > pad_l + plot_w * 0.6 else "start"
            dx = -6 if anchor == "end" else 6
            out.append(
                f'<text x="{x + dx:.1f}" y="{PAD["t"] + 12}" text-anchor="{anchor}" font-size="10" '
                f'fill="var(--accent)">{escape(v_label)}</text>'
            )

    for i, s in enumerate(series):
        colour = s.get("color", PALETTE[i % len(PALETTE)])
        band = s.get("band")
        if band:
            top = " ".join(f"{sx(x):.1f},{sy(hi):.1f}" for x, _lo, hi in band)
            bottom = " ".join(f"{sx(x):.1f},{sy(lo):.1f}" for x, lo, _hi in reversed(band))
            out.append(
                f'<polygon points="{top} {bottom}" fill="{colour}" fill-opacity="0.14" stroke="none"/>'
            )
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in s["points"])
        dash = ' stroke-dasharray="5 4"' if s.get("dash") else ""
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"{dash}/>'
        )
        if s.get("dots"):
            for x, y in s["points"]:
                out.append(
                    f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.6" fill="{colour}" '
                    'stroke="var(--surface)" stroke-width="1"/>'
                )

    out.append(
        f'<text x="{pad_l + plot_w / 2:.0f}" y="{height - 8}" text-anchor="middle" '
        f'font-size="11" fill="var(--text-muted)">{escape(x_label)}</text>'
    )
    out.append(
        f'<text x="14" y="{PAD["t"] + plot_h / 2:.0f}" text-anchor="middle" font-size="11" '
        f'fill="var(--text-muted)" transform="rotate(-90 14 {PAD["t"] + plot_h / 2:.0f})">'
        f"{escape(y_label)}</text>"
    )

    # The readout layer. Everything above is the chart; this is the instrument.
    # It ships inert: an empty crosshair group plus the sample geometry as a
    # data attribute. `static/readout.js` moves it. With JavaScript off the
    # chart is exactly what it was before, which is why the geometry lives in
    # the markup rather than being recomputed in the browser.
    named = [s for s in series if s.get("name") and s["points"]]
    readout = {
        "x": [round(sx(p[0]), 2) for p in named[0]["points"]] if named else [],
        "xv": [p[0] for p in named[0]["points"]] if named else [],
        "xp": x_places,
        "yp": y_places,
        "top": PAD["t"],
        "bottom": PAD["t"] + plot_h,
        "series": [
            {
                "name": s["name"],
                "color": s.get("color", PALETTE[i % len(PALETTE)]),
                "y": [round(sy(p[1]), 2) for p in s["points"]],
                "v": [p[1] for p in s["points"]],
            }
            for i, s in enumerate(series)
            if s.get("name") and s["points"]
        ],
    }
    if readout["series"]:
        out.append(
            '<g class="ro" aria-hidden="true" style="display:none">'
            f'<line class="ro-x" y1="{PAD["t"]}" y2="{PAD["t"] + plot_h}" '
            'stroke="var(--text-muted)" stroke-width="1" stroke-dasharray="3 3"/>'
            "</g>"
        )
        out.append(
            f'<rect class="ro-hit" x="{pad_l}" y="{PAD["t"]}" width="{plot_w}" '
            f'height="{plot_h}" fill="transparent"/>'
        )
    out.append("</svg>")

    attrs = ""
    if readout["series"]:
        # `sort_keys` keeps the attribute byte-identical between builds, which
        # matters because the tests compare rendered output.
        attrs = (
            ' data-readout="'
            + escape(json.dumps(readout, sort_keys=True, separators=(",", ":")), quote=True)
            + '" tabindex="0" role="img"'
            f' aria-label="{escape(y_label)} against {escape(x_label)}."'
        )
    html = [f'<div class="chart"{attrs}>', "".join(out)]
    if readout["series"]:
        html.append('<div class="ro-panel" hidden></div>')
    if legend and len(series) > 0:
        items = "".join(
            f'<span style="color:{s.get("color", PALETTE[i % len(PALETTE)])}"><i></i>'
            f'<span style="color:var(--text-muted)">{escape(s["name"])}</span></span>'
            for i, s in enumerate(series)
            if s.get("name")
        )
        if items:
            html.append(f'<div class="chart-legend">{items}</div>')
    html.append("</div>")
    return Markup("".join(html))


def interval_chart(
    rows: list[dict],
    x_label: str,
    x_places: int = 3,
    caption: str = "",
    width: int = W,
    x_min: float | None = None,
    x_max: float | None = None,
) -> Markup:
    """Point estimates with their confidence intervals on one shared axis.

    Built for the temporal-versus-random comparison, where the finding is not
    either number on its own but the fact that the two intervals do not touch.
    A line chart cannot show that; two whiskers against one axis can.

    row item: {label, value, lo, hi, sub?, level?}  - `level` indexes the heat ramp.
    """
    usable = [r for r in rows if _ok(r.get("value")) and _ok(r.get("lo")) and _ok(r.get("hi"))]
    if not usable:
        return Markup('<div class="empty">No interval estimates available.</div>')

    pad_l, pad_r, head, lane_h, axis_h = 18, 18, 32, 82, 42
    height = head + lane_h * len(usable) + axis_h
    plot_w = width - pad_l - pad_r

    if x_min is not None and x_max is not None:
        # A shared domain, passed in when several of these are read as small
        # multiples. Without it each panel auto-scales to its own data and the
        # panels stop being comparable, which is the only reason to draw them
        # side by side.
        x0, x1 = x_min, x_max
    else:
        lo_x = min(r["lo"] for r in usable)
        hi_x = max(r["hi"] for r in usable)
        margin = max((hi_x - lo_x) * 0.22, 0.004)
        x0, x1 = lo_x - margin, hi_x + margin
    sx = lambda x: pad_l + (x - x0) / (x1 - x0) * plot_w

    out = [
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
        f'aria-label="{escape(x_label)}, point estimate and 95 percent interval per split" '
        'preserveAspectRatio="xMidYMid meet" font-family="ui-monospace, monospace">'
    ]
    grid_top, grid_bot = head, head + lane_h * len(usable)
    out.append(
        f'<rect x="{pad_l}" y="{grid_top}" width="{plot_w}" height="{grid_bot - grid_top}" '
        'fill="var(--grid-bg)"/>'
    )
    for t in _nice_ticks(x0, x1, 6):
        x = sx(t)
        out.append(
            f'<line x1="{x:.1f}" y1="{grid_top}" x2="{x:.1f}" y2="{grid_bot}" '
            'stroke="var(--grid)" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{x:.1f}" y="{grid_bot + 16}" text-anchor="middle" font-size="10.5" '
            f'fill="var(--text-faint)">{escape(_fmt(t, x_places))}</text>'
        )

    # The gap itself is the finding, so draw it: the span between the top of the
    # lower interval and the bottom of the upper one, when they do not touch.
    if len(usable) == 2:
        lower, upper = sorted(usable, key=lambda r: r["value"])
        if lower["hi"] < upper["lo"]:
            gx0, gx1 = sx(lower["hi"]), sx(upper["lo"])
            out.append(
                f'<rect x="{gx0:.1f}" y="{grid_top}" width="{gx1 - gx0:.1f}" '
                f'height="{grid_bot - grid_top}" fill="var(--heat-4)" fill-opacity="0.11"/>'
            )
            for gx in (gx0, gx1):
                out.append(
                    f'<line x1="{gx:.1f}" y1="{grid_top}" x2="{gx:.1f}" y2="{grid_bot}" '
                    'stroke="var(--heat-4)" stroke-width="1" stroke-dasharray="3 3"/>'
                )
            out.append(
                f'<text x="{(gx0 + gx1) / 2:.1f}" y="{grid_top - 19}" text-anchor="middle" '
                f'font-size="10.5" font-weight="600" fill="var(--heat-4)">no overlap</text>'
            )
            out.append(
                f'<text x="{(gx0 + gx1) / 2:.1f}" y="{grid_top - 6}" text-anchor="middle" '
                f'font-size="10.5" fill="var(--heat-4)">'
                f'{escape(_fmt(upper["lo"] - lower["hi"], x_places))} AUC of clear air</text>'
            )

    for i, r in enumerate(usable):
        colour = HEAT[min(max(int(r.get("level", 2)), 0), 4)]
        top = head + lane_h * i
        ty, wy = top + 22, top + 64
        out.append(
            f'<text x="{pad_l + 2}" y="{ty}" font-size="12.5" font-weight="600" '
            f'fill="var(--text)">{escape(r["label"])}</text>'
        )
        out.append(
            f'<text x="{width - pad_r - 2}" y="{ty}" text-anchor="end" font-size="13" '
            f'fill="{colour}">{escape(_fmt(r["value"], x_places))} '
            f'[{escape(_fmt(r["lo"], x_places))}, {escape(_fmt(r["hi"], x_places))}]</text>'
        )
        a, b, v = sx(r["lo"]), sx(r["hi"]), sx(r["value"])
        out.append(
            f'<line x1="{a:.1f}" y1="{wy}" x2="{b:.1f}" y2="{wy}" stroke="{colour}" '
            'stroke-width="3" stroke-linecap="butt"/>'
        )
        for cap in (a, b):
            out.append(
                f'<line x1="{cap:.1f}" y1="{wy - 9}" x2="{cap:.1f}" y2="{wy + 9}" '
                f'stroke="{colour}" stroke-width="2"/>'
            )
        out.append(
            f'<circle cx="{v:.1f}" cy="{wy}" r="6" fill="{colour}" '
            'stroke="var(--surface)" stroke-width="2"/>'
        )
        if r.get("sub"):
            out.append(
                f'<text x="{pad_l + 2}" y="{ty + 18}" font-size="11" '
                f'fill="var(--text-muted)">{escape(r["sub"])}</text>'
            )

    out.append(
        f'<text x="{pad_l + plot_w / 2:.0f}" y="{height - 7}" text-anchor="middle" '
        f'font-size="11" fill="var(--text-muted)">{escape(x_label)}</text>'
    )
    out.append("</svg>")
    html = ['<div class="chart">', "".join(out)]
    if caption:
        html.append(f'<p class="small faint" style="margin-top:8px">{escape(caption)}</p>')
    html.append("</div>")
    return Markup("".join(html))


def _ok(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def series(rows: list[dict], x_key: str, y_key: str, name: str = "", band=None, **kw) -> dict:
    """Build a chart series from a list of metric dicts, dropping NaN points."""
    out = {
        "name": name,
        "points": [(r[x_key], r[y_key]) for r in rows if _ok(r.get(y_key))],
        **kw,
    }
    if band:
        out["band"] = [
            (r[x_key], r[band[0]], r[band[1]])
            for r in rows
            if _ok(r.get(band[0])) and _ok(r.get(band[1]))
        ]
    return out
