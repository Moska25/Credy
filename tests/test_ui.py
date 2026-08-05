"""Front-end audit, run against the real rendered HTML of every route.

These are the checks that used to be done by eye, which meant they were done
once and then quietly regressed. Each one encodes a rule the project actually
holds itself to, so a future change that breaks the rule fails here rather than
being noticed in a screenshot three weeks later.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import db

ROUTES = ["/", "/performance", "/calibration", "/drift", "/subgroups", "/policy",
          "/model-card", "/data"]

#: Layout families used to detect visual monotony. A page that renders the same
#: family three times in a row is a page a reader stops looking at.
FAMILIES = [
    ("metrics", 'class="grid grid-3 metrics"'),
    ("metrics", 'class="grid grid-4 metrics"'),
    ("rail", 'class="alert-rail"'),
    ("matrix", 'class="matrix"'),
    ("chart", 'class="chart"'),
    ("table", '<table class="data"'),
    ("tour", 'class="tour"'),
    ("formula", 'class="formula"'),
    ("kv", 'class="kv'),
    ("timeline", 'class="timeline"'),
]


@pytest.fixture(scope="module")
def client():
    conn = db.connect()
    try:
        seeded = bool(db.all_artifacts(conn))
    except Exception:
        seeded = False
    finally:
        conn.close()
    if not seeded:
        pytest.skip("database not seeded; run `python -m app.seed` first")
    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def pages(client):
    return {r: client.get(r).text for r in ROUTES}


def _sections(html: str) -> list[str]:
    body = html.split('id="content"', 1)[1]
    return re.findall(r'<section class="section"[^>]*>(.*?)</section>', body, re.S)


def _family(section: str) -> str:
    found = [name for name, needle in FAMILIES if needle in section]
    return "+".join(dict.fromkeys(found)) or "prose"


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------
def test_no_em_or_en_dashes_anywhere(pages):
    """The em-dash is the tell that a page was written by a language model.
    It is banned in rendered output; a hyphen or a full stop is always available."""
    for route, html in pages.items():
        for bad in ("—", "–", "&mdash;", "&ndash;"):
            assert bad not in html, f"{route} contains {bad!r}"


def test_no_placeholder_or_lorem_copy(pages):
    for route, html in pages.items():
        low = html.lower()
        for bad in ("lorem ipsum", "todo:", "fixme", "coming soon", "john doe", "jane doe"):
            assert bad not in low, f"{route} contains placeholder copy {bad!r}"


# ---------------------------------------------------------------------------
# document shell
# ---------------------------------------------------------------------------
def test_every_page_has_one_h1_and_a_lede(pages):
    for route, html in pages.items():
        assert html.count("<h1>") == 1, f"{route} has {html.count('<h1>')} h1 elements"
        assert 'class="lede"' in html, route


def test_every_page_is_keyboard_navigable(pages):
    """Skip link first, one main landmark, a labelled nav, and a current page."""
    for route, html in pages.items():
        assert '<a class="skip" href="#content">' in html, f"{route} has no skip link"
        assert html.index('class="skip"') < html.index("<header"), f"{route} skip link is not first"
        assert '<main class="container" id="content"' in html, route
        assert 'aria-label="Primary"' in html, route
        assert 'aria-current="page"' in html, f"{route} marks no nav item as current"


def test_every_page_declares_itself_to_the_browser(pages):
    for route, html in pages.items():
        assert '<meta name="description" content="A credit risk' in html, route
        assert '<link rel="icon" href="/static/mark.svg"' in html, route
        assert '<html lang="en">' in html, route


def test_static_assets_and_favicon_resolve(client):
    for path, kind in (
        ("/favicon.ico", "svg"),
        ("/static/mark.svg", "svg"),
        ("/static/readout.js", "javascript"),
        ("/static/app.css", "css"),
        ("/static/base.css", "css"),
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert kind in r.headers["content-type"], (path, r.headers["content-type"])


def test_nothing_is_loaded_from_the_network(pages):
    """The site must work with the machine offline. No CDN, no remote font."""
    for route, html in pages.items():
        for attr in ('src="http', "src='http", 'href="http://c', 'href="https'):
            assert attr not in html, f"{route} loads something remote: {attr}"
        assert "@import" not in html, route


# ---------------------------------------------------------------------------
# accessible names
# ---------------------------------------------------------------------------
def test_every_graphic_has_an_accessible_name(pages):
    for route, html in pages.items():
        for svg in re.findall(r"<svg[^>]*>", html):
            assert 'role="img"' in svg and "aria-label=" in svg, f"{route}: {svg[:90]}"
        for img in re.findall(r"<img[^>]*>", html):
            assert "alt=" in img, f"{route}: {img[:90]}"


def test_data_tables_label_their_axes(pages):
    """A heatmap without scope attributes is unreadable to a screen reader.

    The accessible name is an `aria-label` on the table rather than a
    `<caption>`, and the visually-hidden month prefixes are in flow rather than
    absolutely positioned. Both avoid the same trap: an out-of-flow element is
    not clipped by `.table-wrap`, so it lands at its static position inside a
    900px matrix and gives the page 564px of horizontal scroll at 375px."""
    html = pages["/drift"]
    assert html.count('class="matrix"') == 2, "expected the PSI and missingness matrices"
    assert html.count('<table class="matrix" aria-label') == 2, "matrices have no accessible name"
    assert html.count("<caption") == 0, "a positioned caption breaks the 375px layout"
    assert html.count('scope="col"') >= 2 * 24, "month headers are not column headers"
    assert html.count('scope="row"') >= 11, "feature headers are not row headers"


# ---------------------------------------------------------------------------
# layout discipline
# ---------------------------------------------------------------------------
def test_no_page_repeats_a_layout_family_three_times_in_a_row(pages):
    for route, html in pages.items():
        fams = [_family(s) for s in _sections(html)]
        run, longest, worst = 0, 0, ""
        prev = None
        for f in fams:
            run = run + 1 if f == prev else 1
            prev = f
            if run > longest:
                longest, worst = run, f
        assert longest <= 2, f"{route} repeats {worst!r} {longest} times in a row: {fams}"


def test_visually_hidden_text_is_never_taken_out_of_flow():
    """The 375px rule's sharpest edge, encoded so it cannot come back.

    `position: absolute` is the textbook recipe for a visually-hidden label, and
    it is wrong inside a horizontal scroll container: an out-of-flow element is
    clipped only by an ancestor in its containing-block chain, and `.table-wrap`
    is not positioned. Two of these inside a 900px-wide heatmap gave `/drift`
    564px of real horizontal page scroll while every `getBoundingClientRect()`
    still looked contained, which is why it survived a visual check.
    """
    from pathlib import Path

    css = (Path(__file__).parent.parent / "app" / "static" / "app.css").read_text()
    block = css.split(".sr-only {", 1)[1].split("}", 1)[0]
    assert "position: absolute" not in block, (
        ".sr-only must stay in flow or it escapes .table-wrap and scrolls the page"
    )
    assert "overflow: hidden" in block and "clip-path" in block


def test_long_pages_carry_in_page_navigation(pages):
    for route in ("/drift", "/data", "/model-card"):
        html = pages[route]
        assert 'class="toc"' in html, f"{route} has no contents strip"
        anchors = re.findall(r'<a href="#([a-z0-9-]+)">', html)
        assert len(anchors) >= 7, route
        for a in anchors:
            assert f'id="{a}"' in html, f"{route}: contents links to missing #{a}"


# ---------------------------------------------------------------------------
# honesty
# ---------------------------------------------------------------------------
def test_headline_figures_are_computed_not_typed_into_templates():
    """Every number on the site must come from the artifacts. A literal in a
    template survives a re-seed and starts lying the moment the data changes."""
    from pathlib import Path

    hard_coded = re.compile(r">\s*[+-]?0\.\d{3}\s*<")
    offenders = []
    for path in (Path(__file__).parent.parent / "app" / "templates").glob("*.html"):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "{{" in line or "{%" in line:
                continue
            if hard_coded.search(line):
                offenders.append(f"{path.name}:{i}  {line.strip()[:70]}")
    assert not offenders, "literal figures in templates: " + "; ".join(offenders)


def test_every_page_labels_its_data_as_synthetic(pages):
    for route, html in pages.items():
        assert "note-warn" in html, f"{route} lacks a synthetic-data warning"
        assert "ynthetic" in html or "generate.py" in html, route
