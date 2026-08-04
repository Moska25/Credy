# Credy

A credit risk laboratory built around the question that actually decides whether a model was
worth building: not "what is my AUC" but "will this model still be accurate, calibrated and
profitable six months from now?"

## What it does

- Generates 40,000 loan applications across 24 monthly cohorts from an explicit, documented
  data-generating process, with four independently switchable forms of temporal drift injected
  on a known schedule.
- Fits three candidates under a **strictly temporal split** (train months 1&ndash;12, validate
  13&ndash;18, test 19&ndash;24) and re-fits the identical models under a naive **random split**,
  to quantify how much the shortcut inflates the result.
- Reports every headline number with a 95% percentile bootstrap interval, tracks calibration
  separately from ranking, and shows reliability before and after Platt and isotonic
  recalibration.
- Monitors PSI and Jensen&ndash;Shannon divergence per feature per month, score drift and
  missing-data rates, then fires alert rules that name the month, the trigger value and the
  recommended action &mdash; and scores those alerts against the drift that was planted.
- Turns a probability into money: an approval-threshold simulator with configurable loss given
  default, margin and cost of a false decline, and a demonstration that the cut-off set at
  deployment is the wrong one six months later.

## Why it exists, and why the data is synthetic

The subject here is **drift detection**, and you cannot claim a detector works unless you know
what it was supposed to detect. On a public lending dataset you can compute a PSI, but a quiet
month is uninterpretable: nobody knows whether the population was stable or the detector was
insensitive. Because this repository writes the data-generating process itself, the drift
schedule is known, so `/drift` ends with two tables that a real dataset cannot produce &mdash;
one scoring each detector against the drift it was meant to catch including how many months late
it was, and one counting how often the same rules false-alarm on a stationary control population
generated with every drift switch turned off.

That is the argument. The cost is stated plainly on the model card: the model is being tested on
a world simple enough to write down, and no result here transfers to a real portfolio.

## Run it

Python 3.12 (the default `python3` on this machine is a 3.15 alpha; do not use it).

```bash
./run.sh
# then open http://127.0.0.1:8014
```

`run.sh` creates `.venv` if missing, installs the pinned requirements, seeds the database
(idempotent &mdash; a second run is a no-op) and starts uvicorn on port 8014. Seeding takes 11-19 seconds
depending on machine load: generation, three model fits under two split strategies, ~40 bootstrap interval sets,
full monthly monitoring and a second stationary control run.

To rebuild from scratch: `./.venv/bin/python -m app.seed --force`.

## What to look at first

Five minutes, in order:

1. **http://127.0.0.1:8014/** &mdash; the headline. Temporal test AUC against random-split test
   AUC for the same model on the same rows, with disjoint confidence intervals. Then the
   verification table: four drifts injected, four detected, with the lag on each.
2. **http://127.0.0.1:8014/drift** &mdash; scroll to "the finding": score PSI, the monitor most
   credit teams actually run, never leaves the stable band while the default rate nearly triples.
   Below it, the false-alarm control table.
3. **http://127.0.0.1:8014/performance** &mdash; the month-by-month charts. AUC sags modestly;
   predicted versus observed level comes apart completely. Two different failures, one model.
4. **http://127.0.0.1:8014/policy** &mdash; drag the threshold. Then look at "what a stale cut-off
   costs": the profit-maximising threshold moves, and holding the old one costs real money.
5. **http://127.0.0.1:8014/model-card** &mdash; the limitations and ethical notes, which are the
   part of a model card that is usually missing.

## How it works

Everything expensive runs once, at seed time. The web app opens SQLite, reads precomputed JSON
artifacts and renders. No model is fitted inside a request, so every page is fast and byte-identical
on every reload.

```
app/generate.py   DGP + drift schedule ──┐
                                          ├──> app/seed.py ──> data/credy.db
app/models.py     3 models, 2 splits ─────┤                    ├── applicants   (40,000 rows)
app/evaluate.py   metrics + bootstrap ────┤                    ├── predictions  (160,000 rows)
app/drift.py      PSI / JS / alerts ──────┤                    └── artifacts    (key -> JSON)
app/subgroups.py  per-cohort diagnostics ─┤                             │
app/policy.py     threshold economics ────┘                             │
                                                                        v
app/charts.py     hand-rolled inline SVG  <────  app/main.py  (routes only, thin)
                                                      │
                                                      v
                                          8 pages, vanilla CSS, no JS framework
```

Business logic lives in importable modules with no FastAPI import anywhere near it, which is what
makes the test suite meaningful: the tests exercise the shipping code directly.

## Engineering notes

**The bootstrap is vectorised, and that decision shaped the project.** A naive implementation
resamples indices and calls `roc_auc_score` in a Python loop; at ~40 interval sets that is most of
a minute. Instead `evaluate._auc_weighted` draws multinomial weights over the rows (exactly the
with-replacement bootstrap), aggregates tied scores with `np.add.reduceat`, and evaluates all 500
replicates in a handful of array operations. Because intervals became nearly free, they went on
*every* number rather than just the headline &mdash; which is the actual point.

**Fixing the DGP calibration was iterative and empirical.** The first version produced a 16%
first-month default rate and a random-split overstatement of only +0.01 AUC. Both were wrong: the
base rate was implausible, and the headline comparison had no signal because the injected concept
drift was too small to damage ranking. The fix was to lower the true intercept, enlarge the broker
coefficient flip, and grow the broker share over time so the drifted subpopulation is large enough
to matter. Every constant in `generate.py` was chosen by measuring, not by guessing.

**The alert that fires is only half the evidence.** The first version of the drift page reported
39 alerts and called that a success. It is not: a rule that fires on everything is worthless. So
`seed._control_alerts` runs the whole monitoring stack a second time over a stationary population
of the same size with all four drift switches off. That immediately exposed that the `auc_floor`
rule false-alarms on a stationary cohort, because a fixed 0.70 floor sits close to this model's
genuine out-of-sample level. That is a badly chosen threshold, and it is now visible on the site
instead of hidden.

**Score PSI's blindness is a finding, not a bug to tune away.** The score-PSI alert rule exists,
is wired up, and never fires: the model cannot see the drift, so it keeps producing
same-looking scores. It was tempting to adjust the threshold until it lit up. Leaving it silent
and explaining why is the more useful result.

**Early stopping on the training months, not the validation months.** Gradient boosting stops on a
random 15% slice drawn from months 1&ndash;12 only. Using the validation window would have leaked
it into fitting and made the validation AUC meaningless as a selection signal.

**A `pd_gap` rule was added beyond the specified four.** Calibration *slope* is the wrong detector
for a prior-probability shift &mdash; a rising base rate moves the intercept, not the slope. The
predicted-versus-observed level gap catches it at month 14; the slope rule alone would have been
late and largely silent.

**The scorecard baseline is real.** Hand-set points bands with no fitting beyond a one-dimensional
points-to-probability map on the training months. It reaches AUC 0.694 against gradient boosting's
0.716 on the temporal test window &mdash; close enough that "just ship the scorecard" is a
defensible position, which is the honest state of most credit risk problems.

## Tests

```bash
./.venv/bin/python -m pytest -q      # 88 tests, 6-12 seconds
```

They cover: generator determinism under a fixed seed and divergence under a different one; each
drift switch producing its effect and *not* producing it when off; PSI returning ~0 for identical
distributions, staying under the watch band for two draws from the same distribution, and rising
monotonically with shift size; the injected income drift being detectable by the shipped PSI
function; temporal-split leakage (no applicant id shared across windows, month ranges strictly
ordered); AUC agreement with `sklearn.roc_auc_score` including heavy ties; bootstrap intervals
containing the point estimate, widening as the sample shrinks, and being reproducible; calibration
slope and intercept correct on synthetic perfectly-calibrated input and moving the right way when
the score is deliberately broken; Brier decomposition reconstructing the Brier score exactly;
recalibration improving slope, intercept and Brier while leaving AUC untouched; policy expected
loss, revenue, opportunity cost and profit against hand-computed worked examples; grid monotonicity;
presets hitting their target approval rates; the stale-threshold result; and every route returning
HTML that carries a synthetic-data warning.

Deliberately not covered: the exact numeric values on the rendered pages (they are asserted at the
module level instead), browser rendering, and any property of `HistGradientBoostingClassifier`
itself. The heavier fixtures run the real pipeline on 9,600 rows rather than mocking it.

## Limitations

- **The data is synthetic and the model is being tested on a world that was written down.** Real
  applicant data contains structure no generator thought of.
- **Outcomes are observed for declined applications too.** A real portfolio only sees what it
  approved, which biases every refit. No reject inference is implemented.
- **Default is a binary flag with no time-to-event**, so no survival model, no lifetime PD, no
  vintage curves.
- **The economics are one-period.** No funding cost, no operational cost, no recovery curve, no
  prepayment; loss given default is a constant rather than a distribution.
- **The champion was selected on the validation window and its test numbers are then reported**,
  which is mildly optimistic and is not corrected for.
- **Bootstrap intervals quantify sampling noise only.** They say nothing about model risk,
  specification error, or the risk that next month's population differs from this one's &mdash;
  which is the risk this entire project is about.
- **Subgroup results are a diagnostic, not a fairness audit**, and around 20 intervals are reported
  with no multiple-comparison correction.
- **Age is used as a model feature.** In several jurisdictions that alone would make the model
  unlawful for consumer credit. It is present to demonstrate what a model card must disclose.
- **The alerts fire months after the drift starts.** That lag is measured and reported rather than
  engineered away, because it is the honest state of monthly monitoring on cohorts this size.
