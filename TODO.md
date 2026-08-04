# Credy — roadmap

## Status

Phases 1–7 are built and working. `./run.sh` creates the venv, seeds the SQLite database in 11-19 seconds
(machine-load dependent) and serves eight pages on port 8014; all eight return HTTP 200 with no exceptions in the
server log. The suite is **88 tests, green**, running in 6-12 seconds
(`./.venv/bin/python -m pytest -q`). Headline results currently produced by the code: gradient
boosting scores AUC 0.716 [0.702, 0.728] on the temporal test window against 0.764 [0.750, 0.779]
under a naive random split — an overstatement of +0.048 with disjoint intervals. All four injected
drifts are detected (lags of 6, 1, 7 and 0 months); the same rules produce 39 alerts on the drifted
cohort against 2 on a stationary control cohort, none of the latter from a drift-specific rule.
Score PSI never exceeds 0.047 and never fires, which is reported as a finding rather than tuned away.

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
   `app/seed.py` — the web app reads precomputed artifacts and will otherwise show stale numbers.
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

- [x] **CRD-4.1** Implement PSI and Jensen–Shannon divergence with conventional bands.
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

## Phase 8 — Real dataset adapter

- [ ] **CRD-8.1** Define a source-agnostic applicant schema and an adapter protocol.
      Files: `app/sources/__init__.py`, `tests/test_sources.py`
      Done when: `load(source_name) -> DataFrame` returns the same columns as `generate()` for at
      least the synthetic source, and a schema check rejects a frame missing any required column
      with a named error rather than a KeyError deep in `models.design_matrix`.
- [ ] **CRD-8.2** Add a Home Credit Default Risk adapter.
      Files: `app/sources/home_credit.py`, `README.md`
      Done when: given a local CSV path, `load("home_credit")` maps its columns onto the schema,
      derives a monthly cohort from the application date, and the README documents where to obtain
      the file and that it is not vendored into the repository.
- [ ] **CRD-8.3** Add a Lending Club adapter with an explicit performance window.
      Files: `app/sources/lending_club.py`
      Done when: loans that have not yet had time to default are excluded by a documented rule
      rather than silently labelled good, and the count excluded is reported at load time.
- [ ] **CRD-8.4** Make the drift verification table degrade honestly on real data.
      Files: `app/drift.py`, `app/templates/drift.html`
      Done when: with no known ground truth, `verify_against_truth` returns an explicit
      "unverifiable" state and the page says so instead of rendering an empty table.

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
      Done when: a challenger fitted on months 7–18 is scored on months 19–24 alongside the
      champion fitted on 1–12, with bootstrap intervals on the difference.
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

## Deliberately out of scope

- **Docker, Postgres, Redis, Celery** — one command and a file on disk is the whole deployment.
- **Any Node build step, React, Tailwind, CDN assets** — the site must work fully offline.
- **An ORM or migrations** — three tables of plain SQL do not need SQLAlchemy or Alembic.
- **Live model training in the browser** — precomputing at seed time is what makes the pages fast
  and deterministic; every feature must respect that.
- **A real fairness audit** — needs real outcomes, a legally defined protected attribute and a
  review process, none of which a synthetic dataset or a website can stand in for.
- **Hyperparameter search** — the point is stability measurement, not squeezing 0.005 AUC, and a
  search would make the seed step slow and the results harder to reason about.
- **Deep learning models** — nothing here needs them, and they would obscure the drift analysis.
- **User accounts, saved scenarios, a database of runs** — nobody is logging in.

## Demo script (5 minutes)

1. `./run.sh`, open **http://127.0.0.1:8014/**. Read the three metric tiles: temporal test AUC,
   random-split test AUC, and the overstatement. Point out the intervals are disjoint.
2. Scroll to **"Did the detectors catch what we planted?"** on the same page. Four injected drifts,
   four detected, with the lag on each — then the note about the stationary control.
3. Go to **http://127.0.0.1:8014/drift** and scroll to the score-PSI tiles. Max score PSI 0.047,
   zero alerts, while the default rate nearly tripled. Then the false-alarm control table below.
4. Go to **http://127.0.0.1:8014/performance** and show the two month-by-month charts side by
   side: ranking sags, level comes apart. Different failures, different fixes.
5. Go to **http://127.0.0.1:8014/policy**, drag the threshold slider, then scroll to
   **"what a stale cut-off costs"** — the threshold move and the profit gap.
6. Finish on **http://127.0.0.1:8014/model-card**, limitations and ethical notes.

## Resume bullets

- Built a credit-risk model-stability lab that quantifies how much a naive random train/test split
  overstates performance: +0.048 AUC with disjoint 95% bootstrap intervals on a strictly temporal
  24-month validation. *(earned: CRD-2.3, CRD-2.4, CRD-3.2)*
- Implemented drift monitoring (PSI, Jensen–Shannon, calibration and missingness rules) and
  validated it against ground truth by injecting four known drifts and running the identical rules
  against a stationary control cohort — 4/4 detected, zero false alarms from any drift-specific
  rule. *(earned: CRD-4.1 through CRD-4.5)*
- Vectorised the AUC bootstrap with multinomial resampling weights, making 500-replicate intervals
  cheap enough to attach to every reported metric rather than only the headline; full seed pipeline
  runs in ~11 seconds. *(earned: CRD-3.2)*
- **NOT YET EARNED** — "Validated the drift pipeline against real lending data (Home Credit,
  Lending Club) with a source-agnostic adapter layer." *(requires CRD-8.1 through CRD-8.4)*
- **NOT YET EARNED** — "Implemented reject inference and quantified approved-only refit bias."
  *(requires CRD-10.1 through CRD-10.3)*
