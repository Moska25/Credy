# Credy — roadmap

## Status

Phases 1-8 and 13-15 are built and working. `./run.sh` creates the venv, seeds the SQLite database in 11-19 seconds
(machine-load dependent) and serves eight pages on port 8014; all eight return HTTP 200 with no exceptions in the
server log. The suite is **117 tests, green**, running in 6-12 seconds
(`./.venv/bin/python -m pytest -q`). Headline results currently produced by the code: gradient
boosting scores AUC 0.716 [0.702, 0.728] on the temporal test window against 0.764 [0.750, 0.779]
under a naive random split, an overstatement of +0.048 with disjoint intervals. All four injected
drifts are detected (lags of 6, 1, 7 and 0 months); the same rules produce 39 alerts on the drifted
cohort against 2 on a stationary control cohort, none of the latter from a drift-specific rule.
Score PSI never exceeds 0.047 and never fires, which is reported as a finding rather than tuned away.
Phase 13 gave the app its "risk console" identity: one sequential heat ramp (`--heat-0..4` in
`app/static/app.css`) carries every risk and drift magnitude, charts sit in a faint plotting grid,
the alert stack rail heads `/` and `/drift`, and the temporal-versus-random comparison is drawn as
two bootstrap intervals with the clear air between them shaded. Phase 14 captured six screenshots
into `docs/screenshots/` and linked them from the README. Presentation only: no computed number
changed, and `document.documentElement.scrollWidth === clientWidth` still holds at 375px on all
eight routes. A later pass took the density up: metric tiles are one hairline-divided instrument
strip rather than four boxes, alerts are a ruled log rather than a deck of cards, prose is capped
to a readable measure, and `--text-faint` is overridden to `#7b8391` because base.css ships a value
that fails WCAG AA on every surface it carries text on. Phase 8 added `app/sources/`, so the same
pipeline can run against Home Credit and Lending Club; no real dataset is vendored. Phase 15
added the showcase floor: a skip link and landmarks, an offline SVG favicon, a footer strip of
the build's own run metadata, a keyboard-operable value readout on every line chart, an
orientation panel on `/` carrying one computed figure per page, a sticky contents strip on the
three long pages, and `tests/test_ui.py`, which audits the rendered HTML of all eight routes for
dashes, landmarks, accessible names, remote assets and layout monotony. That file paid for itself
on the first run by catching 564px of horizontal scroll on `/drift` at 375px: `.sr-only` used
`position: absolute`, and an out-of-flow element is not clipped by `.table-wrap`, so two hidden
"month" labels sat at x=900 inside the heatmap. Every element still measured as contained, which
is why a visual check had missed it.

## How to pick up a task

1. Read this file and `MOSKA_MAIN/shared/CONVENTIONS.md` before writing any code.
2. Work only the task ids you were assigned. Do not "helpfully" do neighbouring tasks, and check
   `## Deliberately out of scope` before adding anything that is not listed here.
3. Business logic goes in an importable module under `app/`, never in a route handler. Routes stay
   thin. Nothing may fit a model inside a request.
4. Before reporting: run `./run.sh` and click through every nav route, and run
   `./.venv/bin/python -m pytest -q`. Both must be clean. Re-seed with
   `./.venv/bin/python -m app.seed --force` after any change to `app/generate.py`,
   `app/models.py`, `app/evaluate.py`, `app/drift.py`, `app/subgroups.py`, `app/policy.py` or
   `app/seed.py`, the web app reads precomputed artifacts and will otherwise show stale numbers.
5. Every number rendered in the UI must be computed by the code. Never hard-code a result into a
   template, and never state a comparison in prose that the code does not compute.
6. **Never run a git command.** Not `add`, not `commit`, not `push`, not `branch`. Leave the
   working tree dirty; the repository owner commits.

## Phase 1 — Data generation

- [x] **CRD-1.1** Write the data-generating process with documented true coefficients.
      Files: `app/generate.py`
      Done when: `generate(n, seed)` returns a frame of 40,000 applicants over 24 monthly cohorts
      with correlated features, and `dgp_truth()` serialises every true coefficient.
- [x] **CRD-1.2** Add four independently switchable drifts on a documented schedule.
      Files: `app/generate.py`, `tests/test_generate.py`
      Done when: each of `covariate_shift`, `prior_shift`, `concept_drift`, `quality_drift` can be
      toggled alone, and a test asserts the effect is present when on and absent when off.
- [x] **CRD-1.3** Make missingness informative and let one field's missing rate drift.
      Files: `app/generate.py`
      Done when: applicants with missing income default more than those without, and
      `employment_tenure` missingness steps from 3% to 30% from month 22.
- [x] **CRD-1.4** Write the true parameters to `data/dgp_truth.json` at seed time.
      Files: `app/seed.py`, `app/generate.py`
      Done when: the file exists after seeding and contains the per-month drift schedule.

## Phase 2 — Modelling

- [x] **CRD-2.1** Build a transparent points scorecard baseline.
      Files: `app/models.py`, `tests/test_models.py`
      Done when: `Scorecard` reaches AUC > 0.60 on the temporal test window with hand-set bands and
      no fitting beyond the points-to-probability map.
- [x] **CRD-2.2** Add logistic regression and `HistGradientBoostingClassifier`.
      Files: `app/models.py`
      Done when: `fit_all` returns all three and `predict_all` returns probabilities in (0, 1).
- [x] **CRD-2.3** Implement the strictly temporal split and the naive random split.
      Files: `app/models.py`, `tests/test_models.py`
      Done when: a test asserts no applicant id is shared across temporal windows and that month
      ranges are strictly ordered, and that the random split has identical window sizes.
- [x] **CRD-2.4** Make the temporal-versus-random comparison a first-class artifact.
      Files: `app/seed.py`, `app/templates/index.html`, `app/templates/performance.html`
      Done when: the overview leads with both AUCs, the overstatement and whether the intervals
      overlap, all computed at seed time.

## Phase 3 — Evaluation

- [x] **CRD-3.1** Implement AUC, Gini, KS, log loss and Brier.
      Files: `app/evaluate.py`, `tests/test_evaluate.py`
      Done when: `auc` matches `sklearn.roc_auc_score` to 1e-10 including heavily tied scores.
- [x] **CRD-3.2** Implement a vectorised percentile bootstrap for AUC and Gini.
      Files: `app/evaluate.py`, `tests/test_evaluate.py`
      Done when: 500 resamples over the test window complete in well under a second, the interval
      contains the point estimate, and it widens when the sample shrinks.
- [x] **CRD-3.3** Implement calibration slope/intercept, reliability curves and Brier decomposition.
      Files: `app/evaluate.py`, `tests/test_evaluate.py`
      Done when: perfectly calibrated synthetic input gives slope within 0.05 of 1 and intercept
      within 0.05 of 0, and the decomposition reconstructs the Brier score exactly.
- [x] **CRD-3.4** Add Platt and isotonic recalibration fitted on the validation window.
      Files: `app/evaluate.py`, `app/seed.py`
      Done when: a test shows recalibration moves slope and intercept toward perfect and lowers
      Brier, while leaving AUC unchanged to 1e-9.
- [x] **CRD-3.5** Add month-by-month metrics and a bootstrap interval on the AUC difference.
      Files: `app/evaluate.py`, `app/templates/performance.html`
      Done when: `/performance` shows the per-cohort AUC with a CI band and states plainly what
      the difference interval does and does not prove.

## Phase 4 — Drift monitoring

- [x] **CRD-4.1** Implement PSI and Jensen-Shannon divergence with conventional bands.
      Files: `app/drift.py`, `tests/test_drift.py`
      Done when: PSI is ~0 for identical distributions, monotone in shift size, and crosses 0.25
      for a one-sigma shift; JSD is 1 bit for disjoint distributions.
- [x] **CRD-4.2** Build the feature × month PSI table, score drift and missingness monitoring.
      Files: `app/drift.py`, `app/templates/drift.html`
      Done when: `/drift` renders a PSI heatmap using the shared `.matrix` classes with every cell
      banded, plus score PSI and per-feature missing rates.
- [x] **CRD-4.3** Implement the alert rules with month, trigger value and recommended action.
      Files: `app/drift.py`, `tests/test_drift.py`
      Done when: every alert carries a finite value and threshold, a message and an action, and no
      alert fires on the training reference window.
- [x] **CRD-4.4** Verify the alerts against the injected drift.
      Files: `app/drift.py`, `app/templates/drift.html`, `app/templates/index.html`
      Done when: `verify_against_truth` returns one row per injected drift with the first detected
      month and the lag, and a test asserts at least 3 of 4 are caught.
- [x] **CRD-4.5** Run the same alert stack against a stationary control cohort.
      Files: `app/seed.py`, `app/templates/drift.html`
      Done when: `/drift` shows a per-rule table of alerts on the drifted cohort against false
      alarms on a no-drift population of the same size.

## Phase 5 — Subgroups and policy

- [x] **CRD-5.1** Add subgroup performance and calibration with intervals and cohort sizes.
      Files: `app/subgroups.py`, `tests/test_policy.py`
      Done when: cohorts below `MIN_GROUP` or with fewer than 15 defaults report no AUC at all, and
      the page states the diagnostic-not-audit caveat.
- [x] **CRD-5.2** Build the threshold-economics grid and the profit formula.
      Files: `app/policy.py`, `tests/test_policy.py`
      Done when: `outcomes` and `apply_economics` agree exactly, and expected loss, revenue,
      opportunity cost and profit each match a hand-computed four-applicant worked example.
- [x] **CRD-5.3** Add conservative/balanced/growth presets defined by target approval rate.
      Files: `app/policy.py`
      Done when: each preset hits its target approval rate on the reference cohort to within 1pp.
- [x] **CRD-5.4** Quantify the cost of a stale threshold.
      Files: `app/policy.py`, `app/templates/policy.html`
      Done when: `stale_threshold_cost` reports the threshold move and the profit gap, and a test
      asserts the optimum tightens and the gap is positive on a deteriorating population.

## Phase 6 — Web app

- [x] **CRD-6.1** Build the eight pages on the shared layout and design system.
      Files: `app/main.py`, `app/templates/*.html`, `app/static/app.css`
      Done when: every nav route returns 200, opens with an `h1` and a `.lede`, and carries a
      `.note-warn` labelling the data as synthetic.
- [x] **CRD-6.2** Hand-roll the SVG chart module.
      Files: `app/charts.py`, `tests/test_app.py`
      Done when: `line_chart` renders axis labels with units, supports confidence bands, reference
      lines and vertical markers, and returns a real empty state for an empty series.
- [x] **CRD-6.3** Make the policy simulator interactive without refitting anything.
      Files: `app/main.py`, `app/templates/policy.html`, `app/policy.py`
      Done when: threshold, LGD, margin and false-decline cost are GET parameters applied to the
      precomputed grid, out-of-range input is clamped, and no model is fitted per request.
- [x] **CRD-6.4** Hold the layout at 375px with no horizontal page scroll.
      Files: `app/static/app.css`
      Done when: `document.body.scrollWidth <= window.innerWidth` at a 375px viewport on all eight
      routes, wide tables scroll inside `.table-wrap` and charts scroll inside `.chart`.

## Phase 7 — Persistence and tests

- [x] **CRD-7.1** Persist applicants, predictions and artifacts to SQLite with plain SQL.
      Files: `app/db.py`, `tests/test_app.py`
      Done when: NULLs survive the round trip and `put` upserts rather than duplicating.
- [x] **CRD-7.2** Make seeding idempotent and deterministic.
      Files: `app/seed.py`, `app/db.py`
      Done when: a second `python -m app.seed` is a no-op, `--force` rebuilds, and two builds from
      the same seed produce identical data.
- [x] **CRD-7.3** Write the test suite.
      Files: `tests/*.py`
      Done when: at least 25 real assertions on real logic pass; currently 88.

## Phase 8 — Real dataset adapter (done)

- [x] **CRD-8.1** Define a source-agnostic applicant schema and an adapter protocol.
      Files: `app/sources/__init__.py`, `tests/test_sources.py`
      Done when: `load(source_name) -> DataFrame` returns the same columns as `generate()` for at
      least the synthetic source, and a schema check rejects a frame missing any required column
      with a named error rather than a KeyError deep in `models.design_matrix`.
      The registry is a dict of name to callable, not an ABC. `check` also rejects a non-positive
      cohort index, a label outside {0, 1} and an unmapped categorical level; the last one matters
      most because one-hot encoding an unknown level yields an all-zero row, so the applicant
      silently becomes the reference level instead of failing. `load` stamps provenance and
      per-column coverage onto `df.attrs["source"]`, and adapters fill what a source genuinely
      lacks with null or the explicit level `unknown` rather than inventing it.
- [x] **CRD-8.2** Add a Home Credit Default Risk adapter.
      Files: `app/sources/home_credit.py`, `README.md`
      Done when: given a local CSV path, `load("home_credit")` maps its columns onto the schema,
      derives a monthly cohort from the application date, and the README documents where to obtain
      the file and that it is not vendored into the repository.
      **Partially satisfiable, and the shortfall is in the dataset, not the code.** The public
      Kaggle `application_train.csv` is anonymised: every time field is a negative day offset
      relative to the application, so the file contains no application date and no cohort can be
      derived from it. The adapter takes `date_column` for a dated extract and raises a named
      `SchemaError` otherwise; it will not fabricate a time axis by sorting on `SK_ID_CURR`,
      because the temporal ordering is the thing this project measures. Everything else lands:
      the `DAYS_EMPLOYED == 365243` not-employed sentinel is mapped rather than fed in as a
      thousand years of tenure, `NAME_INCOME_TYPE` is mapped exhaustively onto `employment_type`,
      revolving credit gets a null term instead of a guessed one, and README documents the
      download and the non-vendoring.
- [x] **CRD-8.3** Add a Lending Club adapter with an explicit performance window.
      Files: `app/sources/lending_club.py`, `tests/test_sources.py`
      Done when: loans that have not yet had time to default are excluded by a documented rule
      rather than silently labelled good, and the count excluded is reported at load time.
      The rule: keep a loan only if its outcome is already resolved (Fully Paid, Charged Off,
      Default). Anything unresolved is excluded, split in the report into immature loans (issued
      too recently to have completed their term) and matured loans with no terminal status.
      `as_of` defaults to the latest issue date plus the longest term, so a run is reproducible
      from the file rather than from today's clock. `dti` is converted from percent to ratio.
- [x] **CRD-8.4** Make the drift verification table degrade honestly on real data.
      Files: `app/drift.py`, `app/templates/drift.html`, `app/templates/index.html`,
      `app/seed.py`, `tests/test_drift.py`
      Done when: with no known ground truth, `verify_against_truth` returns an explicit
      "unverifiable" state and the page says so instead of rendering an empty table.
      It now returns `{"verifiable", "reason", "rows"}`; both `/` and `/drift` render the reason
      under "This table is withheld, not empty" when the source has no known schedule. Verified
      by rendering both routes with the flag forced false.

## Phase 9 — Survival and lifetime PD

- [ ] **CRD-9.1** Add a time-to-default column to the generator.
      Files: `app/generate.py`, `tests/test_generate.py`
      Done when: each defaulting application carries a month-of-default within its term, and a test
      asserts default months never exceed the loan term.
- [ ] **CRD-9.2** Implement discrete-time hazard estimation.
      Files: `app/survival.py`, `tests/test_survival.py`
      Done when: `hazard_curve(df)` returns a per-period hazard whose cumulative incidence matches
      the observed default rate on the training months to within 1 percentage point.
- [ ] **CRD-9.3** Add a lifetime-PD page showing vintage curves by cohort.
      Files: `app/main.py`, `app/templates/survival.html`, `app/charts.py`
      Done when: `/survival` returns 200 and plots cumulative default by months-on-book with one
      line per origination quarter.

## Phase 10 — Reject inference

- [ ] **CRD-10.1** Simulate a declined population with unobserved outcomes.
      Files: `app/policy.py`, `tests/test_policy.py`
      Done when: `apply_policy(df, threshold)` returns a frame where declined rows have their
      `default` masked to NaN, leaving the true value available separately for scoring.
- [ ] **CRD-10.2** Implement parcelling and augmentation reject-inference methods.
      Files: `app/reject_inference.py`, `tests/test_reject_inference.py`
      Done when: refitting on the approved-only population is measurably more biased against the
      known truth than refitting with either inference method, and the test asserts the direction.
- [ ] **CRD-10.3** Show the approved-only bias on the site.
      Files: `app/templates/policy.html`, `app/seed.py`
      Done when: `/policy` shows the bad rate a naive approved-only refit would predict against the
      true population bad rate, both computed at seed time.

## Phase 11 — Champion/challenger monitoring

- [ ] **CRD-11.1** Persist multiple model versions with their fit windows.
      Files: `app/db.py`, `app/seed.py`
      Done when: the `predictions` table carries a version tag and the artifacts record which
      months each version was fitted on.
- [ ] **CRD-11.2** Add a challenger refitted on a rolling recent window.
      Files: `app/models.py`, `app/seed.py`
      Done when: a challenger fitted on months 7-18 is scored on months 19-24 alongside the
      champion fitted on 1-12, with bootstrap intervals on the difference.
- [ ] **CRD-11.3** Add a promotion rule and show when it would have triggered.
      Files: `app/drift.py`, `app/templates/drift.html`
      Done when: a documented rule (challenger AUC interval strictly above champion's for two
      consecutive months) is evaluated per month and the triggering month is displayed.

## Phase 12 — Explanations

- [ ] **CRD-12.1** Add SHAP values for the gradient boosting champion.
      Files: `app/explain.py`, `requirements.txt`, `tests/test_explain.py`
      Done when: mean absolute SHAP per feature is computed at seed time on a fixed sample and a
      test asserts the ranking is stable across two runs with the same seed.
- [ ] **CRD-12.2** Add per-application reason codes.
      Files: `app/explain.py`, `app/main.py`, `app/templates/applicant.html`
      Done when: `/applicant/{id}` returns 200 and lists the three features pushing the score up
      and the three pushing it down, with their contributions in logit units.
- [ ] **CRD-12.3** Show how feature attribution shifts with drift.
      Files: `app/templates/drift.html`, `app/seed.py`
      Done when: mean absolute SHAP per feature is compared between the training months and the
      test months, and the broker channel's rise is visible.

## Phase 13 — Visual identity: "risk console" (done)

Design spec: `MOSKA_MAIN/shared/UI_DIRECTION.md`, Credy section. Presentation only:
do not refit models, re-run the generator, or change any computed number.

- [x] **CRD-13.1** Define one sequential heat ramp and the plotting-grid treatment as CSS
      variables, and apply the ramp to every risk/drift magnitude in the app.
      Files: `app/static/app.css`, `app/charts.py`
      Done when: no magnitude anywhere is encoded with a colour outside the ramp.
      Landed as `--heat-0..4` (slate, teal, amber, orange, red; luminance rises monotonically)
      plus `--heat-fill-0..4` for backgrounds and `--grid` / `--grid-bg` for the plotting well.
      `charts.heat_level(value, stops)` maps a magnitude to a stop; `drift.band` still owns the
      stable/watch/shifted *verdict*, which is a different thing from a colour. `--pass` /
      `--fail` / `--warn` survive only on `.pill` state (detected/missed, within-interval), never
      on a magnitude.
- [x] **CRD-13.2** Build the alert stack rail and place it on / and /drift.
      Files: `app/templates/_alert_rail.html` (new macro), `index.html`, `drift.html`,
      `app/static/app.css`
      Done when: each firing alert names month, trigger, value and recommended action,
      and severity is legible without colour alone.
      One macro used by both pages: five alerts on `/` with a link to the rest, all 39 on
      `/drift`, which replaced the old alerts table. Severity is the word HIGH or MED in a mono
      chip with a distinct glyph, so it does not depend on hue.
- [x] **CRD-13.3** Restyle the PSI heatmap on the ramp with a legend naming the 0.10 and
      0.25 conventions as conventions, not laws.
      Files: `app/charts.py`, `app/templates/drift.html`, `app/static/app.css`
      Cells are shaded on a five-step ramp cut at 0.02 / 0.05 / 0.10 / 0.25, so the sub-0.10
      ramps that make up most of this page are visible instead of flattened into one band. The
      two conventional cut-points are marked on the legend and drawn as a rule along the top edge
      of any cell that crosses them.
- [x] **CRD-13.4** Draw and label the 45-degree reference on the calibration plot and overlay
      before/after recalibration.
      Files: `app/charts.py`, `app/templates/calibration.html`, `app/main.py`
      Done when: a reader can see at a glance which curve is better calibrated and why.
      `line_chart(diag_ref=True, diag_label=...)` draws y = x clipped to the axes, labels it
      along its own angle, and washes the half-plane above it as under-prediction. The three
      variants are ordered on the ramp: raw hottest, isotonic coldest.
- [x] **CRD-13.5** Promote the temporal-versus-random AUC comparison to the visual centrepiece
      of the overview.
      Files: `app/charts.py`, `app/templates/index.html`, `app/main.py`, `app/static/app.css`
      Done when: 0.716 [0.702, 0.728] against 0.764 [0.750, 0.779] reads as the page's main
      finding, with the disjoint intervals shown rather than described.
      New `charts.interval_chart` draws both estimates as whiskers on one AUC axis and shades
      the 0.022 of clear air between the intervals, captioned "no overlap".

## Phase 14 — Showcase assets (done)

- [x] **CRD-14.1** Capture screenshots into `docs/screenshots/`: hero (temporal vs random),
      PSI heatmap, calibration curves, policy simulator, plus one at 375px.
      Done when: five captioned PNGs exist, taken after Phase 13 lands.
      Six exist: the five listed plus `alert-stack.png`, since the rail is a Phase 13
      deliverable in its own right. All captured from the running app at 1280px, and
      `mobile-375.png` at a true 375px viewport.
- [x] **CRD-14.2** Link the hero image at the top of README.md.
      The hero sits under the opening paragraph with alt text stating both intervals; the other
      five are captioned under a new "Screenshots" section after the guided tour.

## Phase 15 — Showcase polish and accessibility (done)

The site is correct and it is now legible. This phase is about the difference between a
correct site and one a hiring manager remembers: the affordances a monitoring console is
expected to have, the accessibility floor a public artefact should meet, and the small
finishes whose absence a careful reader notices.

Presentation and plumbing only, with one exception (CRD-15.10). Do not refit models, do not
re-run the generator, do not change any computed number. Re-seed after CRD-15.10.

- [x] **CRD-15.1** Bring the page shell to a keyboard and screen-reader floor.
      Files: `app/templates/_layout.html`, `app/static/app.css`, `app/templates/drift.html`
      Done when: a visible skip link is the first focusable element on every page and jumps to
      `#content`; `<nav>` carries `aria-label="Primary"` and `<main>` carries `id="content"`;
      the PSI matrix uses `scope="col"` on its month headers and `scope="row"` on its feature
      headers; and tabbing from the address bar reaches the skip link, then the brand, then
      the nav, with a visible focus ring at every stop.
      Landed: skip link, `<main id="content">`, `aria-label="Primary"`, `aria-current`
      on the active nav item, and `scope` on both matrices.
- [x] **CRD-15.2** Give the app an identity in the browser chrome, fully offline.
      Files: `app/main.py`, `app/templates/_layout.html`, `app/static/mark.svg`
      Done when: `/favicon.ico` and `/static/mark.svg` both return 200 rather than a 404 in the
      server log, the tab shows the violet mark, and `<meta name="description">` and
      `<meta name="theme-color">` are present. No CDN, no binary asset checked in that is not
      hand-written SVG.
      Landed: `app/static/mark.svg` is the heat ramp stacked as four bars; `/favicon.ico`
      serves it so browsers stop logging a 404 on every page view.
- [x] **CRD-15.3** Replace the footer sentence with a run-metadata strip.
      Files: `app/templates/_layout.html`, `app/main.py`, `app/static/app.css`
      Done when: the footer renders seed version, row count, month count, data seed, champion,
      bootstrap replicate count and build seconds as a mono strip, every value read from the
      `meta` artifact and none of them hard-coded, and it wraps without overflow at 375px.
      Landed: `main.run_meta` builds the strip from the meta artifact; nothing in the
      footer is a literal.
- [x] **CRD-15.4** Add a value readout to every line chart.
      Files: `app/charts.py`, `app/static/app.css`, `app/templates/_layout.html`
      Done when: moving the pointer across any `line_chart` shows the x value and every series
      value at the nearest sample, the same readout is reachable with the keyboard (the chart is
      focusable, arrow keys step between samples), it degrades to a static chart with no script,
      and it adds no dependency and no network request. Charts are hand-rolled inline SVG, so the
      readout must be too.
      Landed: `charts.line_chart` serialises the sample geometry into `data-readout` and
      `static/readout.js` moves a crosshair over it. Pointer, arrow keys, Home, End and
      Escape all work; with the script blocked the chart is exactly what it was.
- [x] **CRD-15.5** Cap prose measure inside cards and give the spec lists a second column.
      Files: `app/static/app.css`
      Done when: no paragraph anywhere on the site exceeds about 92 characters per line at
      1280px, and `.kv` blocks use two columns above 1000px instead of leaving half the card
      empty.
      Landed: prose caps at 92ch inside cards too, and `.kv-2` gives the spec lists a
      second column above 1000px.
- [x] **CRD-15.6** Break the section-layout repetition on the long pages.
      Files: `app/templates/drift.html`, `app/templates/data.html`, `app/static/app.css`
      Done when: neither `/drift` nor `/data` renders more than two consecutive sections in the
      same layout family, counting "ruled head plus one card" as one family.
      Landed: `/drift`'s missing-data table became a matrix on the same ramp, and
      `/subgroups` collapsed four identical tables into one small-multiples section on a
      shared axis plus a single detail table. Longest run is now 2 on every page, asserted
      by `tests/test_ui.py`.
- [x] **CRD-15.7** Make the overview's closing block an orientation panel, not a menu.
      Files: `app/templates/index.html`, `app/main.py`, `app/static/app.css`
      Done when: each destination carries the headline figure a reader would go there for
      (computed, not written into the template), so the panel reads as a summary of the whole
      site rather than a list of links.
      Landed as `.tour`: six rows, each with the figure a reader would go there for,
      computed in `main.overview` from the artifacts.
- [x] **CRD-15.8** Add in-page section navigation to the three long pages.
      Files: `app/templates/_layout.html` (macro), `drift.html`, `data.html`, `model_card.html`
      Done when: each of those pages carries a sticky, single-line contents strip linking to its
      own `h2` anchors, every `h2` on those pages has a stable `id`, and the strip scrolls
      horizontally rather than wrapping at 375px.
      Landed as the `_toc.html` macro. Sticky wrapper outside, scroll container inside.
- [x] **CRD-15.9** Add a repeatable front-end audit instead of eyeballing it.
      Files: `tests/test_ui.py`
      Done when: pytest asserts, on the real rendered HTML of all eight routes, that there are
      zero em-dashes and en-dashes, that every page has exactly one `h1`, a skip link, a
      `note-warn`, and a `<main id="content">`, that every `img`/`svg` carries alt text or an
      accessible name, and that no template hard-codes a headline figure that the artifacts
      compute.
      Landed as `tests/test_ui.py`, 15 checks over the rendered HTML of all eight routes.
      It caught a real regression immediately: see the note under CRD-15.1.
- [x] **CRD-15.10** Route the seed pipeline through the Phase 8 adapter.
      Files: `app/seed.py`
      Done when: `seed.py` calls `sources.load("synthetic", ...)` rather than `generate()`
      directly, so the schema check runs in production rather than only in tests, seeding still
      completes in the same time, and every artifact is byte-identical to the previous build.

      Landed. Every artifact byte-identical to the previous build except `meta.built_seconds`,
      which is wall-clock.
## Deliberately out of scope

- **Docker, Postgres, Redis, Celery**, one command and a file on disk is the whole deployment.
- **Any Node build step, React, Tailwind, CDN assets**, the site must work fully offline.
- **An ORM or migrations**, three tables of plain SQL do not need SQLAlchemy or Alembic.
- **Live model training in the browser**, precomputing at seed time is what makes the pages fast
  and deterministic; every feature must respect that.
- **A real fairness audit**, needs real outcomes, a legally defined protected attribute and a
  review process, none of which a synthetic dataset or a website can stand in for.
- **Hyperparameter search**, the point is stability measurement, not squeezing 0.005 AUC, and a
  search would make the seed step slow and the results harder to reason about.
- **Deep learning models**, nothing here needs them, and they would obscure the drift analysis.
- **User accounts, saved scenarios, a database of runs**, nobody is logging in.

## Demo script (5 minutes)

1. `./run.sh`, open **http://127.0.0.1:8014/**. Read the three metric tiles: temporal test AUC,
   random-split test AUC, and the overstatement. Point out the intervals are disjoint.
2. Scroll to **"Did the detectors catch what we planted?"** on the same page. Four injected drifts,
   four detected, with the lag on each, then the note about the stationary control.
3. Go to **http://127.0.0.1:8014/drift** and scroll to the score-PSI tiles. Max score PSI 0.047,
   zero alerts, while the default rate nearly tripled. Then the false-alarm control table below.
4. Go to **http://127.0.0.1:8014/performance** and show the two month-by-month charts side by
   side: ranking sags, level comes apart. Different failures, different fixes.
5. Go to **http://127.0.0.1:8014/policy**, drag the threshold slider, then scroll to
   **"what a stale cut-off costs"**, the threshold move and the profit gap.
6. Finish on **http://127.0.0.1:8014/model-card**, limitations and ethical notes.

## Resume bullets

- Built a credit-risk model-stability lab that quantifies how much a naive random train/test split
  overstates performance: +0.048 AUC with disjoint 95% bootstrap intervals on a strictly temporal
  24-month validation. *(earned: CRD-2.3, CRD-2.4, CRD-3.2)*
- Implemented drift monitoring (PSI, Jensen-Shannon, calibration and missingness rules) and
  validated it against ground truth by injecting four known drifts and running the identical rules
  against a stationary control cohort: 4/4 detected, zero false alarms from any drift-specific
  rule. *(earned: CRD-4.1 through CRD-4.5)*
- Vectorised the AUC bootstrap with multinomial resampling weights, making 500-replicate intervals
  cheap enough to attach to every reported metric rather than only the headline; full seed pipeline
  runs in ~11 seconds. *(earned: CRD-3.2)*
- Built a source-agnostic adapter layer so the same drift pipeline runs against Home Credit and
  Lending Club, with a schema check that fails by name instead of dying as a KeyError inside the
  design matrix, and a performance-window rule that excludes immature loans rather than labelling
  them good. *(earned: CRD-8.1 through CRD-8.4)*
- **NOT YET EARNED** "Implemented reject inference and quantified approved-only refit bias."
  *(requires CRD-10.1 through CRD-10.3)*
