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

from html import escape

from markupsafe import Markup

W, H = 760, 300
PAD = {"l": 56, "r": 16, "t": 16, "b": 46}
PALETTE = ["var(--accent)", "var(--info)", "var(--warn)", "var(--pass)", "var(--fail)"]


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

    plot_w = W - PAD["l"] - PAD["r"]
    plot_h = height - PAD["t"] - PAD["b"]
    sx = lambda x: PAD["l"] + (x - x0) / (x1 - x0) * plot_w
    sy = lambda y: PAD["t"] + (hi_y - y) / (hi_y - lo_y) * plot_h

    out = [
        f'<svg viewBox="0 0 {W} {height}" width="{W}" height="{height}" '
        f'role="img" aria-label="{escape(y_label)} against {escape(x_label)}" '
        'preserveAspectRatio="xMidYMid meet" font-family="ui-monospace, monospace">'
    ]

    # grid + y axis
    for t in _nice_ticks(lo_y, hi_y):
        y = sy(t)
        out.append(
            f'<line x1="{PAD["l"]}" y1="{y:.1f}" x2="{PAD["l"] + plot_w}" y2="{y:.1f}" '
            'stroke="var(--border)" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{PAD["l"] - 8}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10.5" '
            f'fill="var(--text-faint)">{escape(_fmt(t, y_places))}</text>'
        )

    # x axis ticks
    ticks = x_ticks if x_ticks is not None else _nice_ticks(x0, x1, 6)
    for t in ticks:
        x = sx(t)
        out.append(
            f'<line x1="{x:.1f}" y1="{PAD["t"] + plot_h}" x2="{x:.1f}" y2="{PAD["t"] + plot_h + 4}" '
            'stroke="var(--border-strong)" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{x:.1f}" y="{PAD["t"] + plot_h + 17}" text-anchor="middle" font-size="10.5" '
            f'fill="var(--text-faint)">{escape(_fmt(t, x_places))}</text>'
        )
    out.append(
        f'<line x1="{PAD["l"]}" y1="{PAD["t"] + plot_h}" x2="{PAD["l"] + plot_w}" '
        f'y2="{PAD["t"] + plot_h}" stroke="var(--border-strong)" stroke-width="1"/>'
    )

    if ref_line is not None:
        y = sy(ref_line)
        out.append(
            f'<line x1="{PAD["l"]}" y1="{y:.1f}" x2="{PAD["l"] + plot_w}" y2="{y:.1f}" '
            'stroke="var(--text-faint)" stroke-width="1" stroke-dasharray="5 4"/>'
        )
        if ref_label:
            out.append(
                f'<text x="{PAD["l"] + plot_w - 4}" y="{y - 5:.1f}" text-anchor="end" font-size="10" '
                f'fill="var(--text-faint)">{escape(ref_label)}</text>'
            )

    if v_line is not None and x0 <= v_line <= x1:
        x = sx(v_line)
        out.append(
            f'<line x1="{x:.1f}" y1="{PAD["t"]}" x2="{x:.1f}" y2="{PAD["t"] + plot_h}" '
            'stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="4 4"/>'
        )
        if v_label:
            anchor = "end" if x > PAD["l"] + plot_w * 0.6 else "start"
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
        f'<text x="{PAD["l"] + plot_w / 2:.0f}" y="{height - 8}" text-anchor="middle" '
        f'font-size="11" fill="var(--text-muted)">{escape(x_label)}</text>'
    )
    out.append(
        f'<text x="14" y="{PAD["t"] + plot_h / 2:.0f}" text-anchor="middle" font-size="11" '
        f'fill="var(--text-muted)" transform="rotate(-90 14 {PAD["t"] + plot_h / 2:.0f})">'
        f"{escape(y_label)}</text>"
    )
    out.append("</svg>")

    html = ['<div class="chart">', "".join(out)]
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
