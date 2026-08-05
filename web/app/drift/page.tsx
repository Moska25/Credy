import AlertRail from '@/components/AlertRail';
import HeatMatrix, { RampLegend } from '@/components/HeatMatrix';
import LineChart from '@/components/charts/LineChart';
import { Card, Metric, Note, PageHead, Section, TableCard } from '@/components/Page';
import {
  ALERTS, ALERT_TOTALS, BY_RULE, CONTROL, FEATURE_PSI, META, MISSINGNESS, MONTHS,
  SCORE_JS, SCORE_PSI, SCORE_PSI_MAX, THRESHOLDS, VERIFICATION,
} from '@/lib/artifacts';
import { HEAT, pct } from '@/lib/format';

export const metadata = { title: 'Drift · Credy' };

const psiRows = Object.entries(FEATURE_PSI).map(([feature, values]) => ({ feature, values }));

/** Missingness is shaded against each row's own reference, not against zero:
 *  the coldest step spans ~two standard errors at this cohort size, so a month
 *  moving inside its own sampling noise stays unshaded. */
const missRows = Object.entries(MISSINGNESS).map(([feature, m]) => ({
  feature,
  reference: pct(m.ref, 0),
  values: m.rates.map((r) => r - m.ref),
  raw: m.rates,
}));

/** The two features that moved most, chosen from the data rather than named in
 *  the markup, so the chart stays correct if the DGP changes. */
const movers = Object.entries(FEATURE_PSI)
  .sort((a, b) => Math.max(...b[1]) - Math.max(...a[1]))
  .slice(0, 2);

const scorePsiRule = BY_RULE.find((r) => r.rule === 'score_psi');

export default function Drift() {
  const monitoredFrom = META.splits.validation[0];
  return (
    <div className="page" data-screen-label="Drift">
      <PageHead kicker="Monitoring" meta={`monitored from month ${monitoredFrom} onwards`} title="Drift monitoring">
        Every cohort from month {monitoredFrom} onwards, compared back to the pooled training months: population stability index and
        Jensen-Shannon divergence per feature, the model&rsquo;s own score distribution, missing-data rates, and the alert rules
        built on top of them.
      </PageHead>

      <Note bare title="Synthetic data with planted drift.">
        Four drifts were injected on purpose at known months. That is what makes the verification table at the bottom of this
        page possible at all.
      </Note>

      <Section title="The finding: score PSI missed the drift that mattered">
        <div className="metrics" style={{ marginBottom: 16 }}>
          <Metric label="Max score PSI, whole window" value={SCORE_PSI_MAX.toFixed(2)} color="var(--stone-ink)"
            sub={`alert threshold is ${THRESHOLDS.scorePsiAlert.toFixed(2)}, never reached`} />
          <Metric label="Score PSI alerts fired" value={String(scorePsiRule?.drifted ?? 0)} color="var(--stone-ink)"
            sub="the rule exists and stayed silent" />
          <Metric label="Alerts fired by other rules" value={ALERT_TOTALS.total} color="var(--clay-ink)" sub={`${ALERT_TOTALS.high} high severity`} />
        </div>

        <Note tone="clay" title="Why this matters more than any chart on the page.">
          Score PSI is the monitor most credit risk functions actually run, because it needs no outcomes &mdash; just the score
          distribution. Here it stayed comfortably inside the stable band all the way to month 24 while the observed default
          rate nearly tripled. The reason is mechanical: the model cannot see the drift, so it keeps producing same-looking
          scores. A monitor built only on model outputs is blind to concept drift by construction, and outcome-based monitoring
          &mdash; the only thing that catches it &mdash; arrives late.
        </Note>
        <div style={{ height: 18 }} />

        <Card>
          <LineChart
            height={290}
            xLabel="Application month"
            yLabel="Divergence from training reference"
            xTicks={[1, 4, 8, 12, 16, 20, 24]}
            yMin={0}
            refLine={THRESHOLDS.scorePsiAlert}
            refLabel={`PSI alert threshold ${THRESHOLDS.scorePsiAlert.toFixed(2)}`}
            readoutPrefix="month "
            formatValue="n2"
            series={[
              { label: 'Score PSI vs training reference', color: HEAT[0], points: MONTHS.map((m, i) => [m, SCORE_PSI[i]]) },
              { label: 'Score Jensen-Shannon divergence (bits)', color: HEAT[1], points: MONTHS.map((m, i) => [m, SCORE_JS[i]]) },
            ]}
          />
        </Card>
      </Section>

      <Section title="Feature PSI by month" meta="one heat ramp, used here and everywhere else">
        <Card>
          <HeatMatrix
            rows={psiRows}
            format={(v) => v.toFixed(2)}
            ariaLabel="Population stability index per feature per application month, against the pooled training reference"
          />
          <RampLegend />
          <p className="small faint" style={{ margin: '14px 0 0', maxWidth: '92ch' }}>
            The two underlined steps are the industry convention. They are a convention, not a law: they have no distributional
            justification and they do not adjust for sample size. With {META.perMonth.toLocaleString('en-US')} applications a
            month a PSI of 0.05 is indistinguishable from noise; with a million rows it would not be. The two colder steps exist
            because a three-band scale that treats everything under 0.10 as one flat colour hides the ramps that make up most of
            this page. Cells in the two convention bands also carry a rule along their top edge, so the cut-points survive
            greyscale.
          </p>
        </Card>
      </Section>

      <Section title="The two features that actually moved">
        <Card>
          <LineChart
            height={300}
            xLabel="Application month"
            yLabel="PSI vs training reference"
            xTicks={[1, 4, 8, 12, 16, 20, 24]}
            yMin={0}
            refLine={THRESHOLDS.psiShift}
            refLabel={`shifted band ${THRESHOLDS.psiShift.toFixed(2)}`}
            readoutPrefix="month "
            formatValue="n2"
            series={movers.map(([feature, values], i) => ({
              label: `${feature} PSI`,
              color: HEAT[i === 0 ? 4 : 3],
              points: MONTHS.map((m, j) => [m, values[j]] as [number, number]),
            }))}
          />
        </Card>
        <p className="small faint" style={{ margin: '12px 0 0', maxWidth: '88ch' }}>
          Both are ramps, not step changes, which is why PSI takes months to cross a fixed threshold. A slow drift is the
          hardest kind to alert on: by the time a conventional cut-point trips, the population has already moved a long way.
        </p>
      </Section>

      <Section title="Missing-data rates" meta="shaded by distance above its own reference">
        <Card>
          <HeatMatrix
            rows={missRows.map((r) => ({ feature: r.feature, reference: r.reference, values: r.values, display: r.raw }))}
            stops={[0.0125, 0.04, THRESHOLDS.missingnessJump, 0.2]}
            format={(v) => String(Math.round(v * 100))}
            showReference
            ariaLabel="Missing-value rate per feature per application month, against the training reference rate"
          />
          <p className="small faint" style={{ margin: '14px 0 0', maxWidth: '92ch' }}>
            Cells are the missing rate as a whole percentage, shaded by how far it sits above <code>ref</code> — the pooled
            training rate for that feature. The coldest step spans 1.25 points, roughly two standard errors on a cohort of{' '}
            {META.perMonth.toLocaleString('en-US')} at these rates: below that a month is moving inside its own sampling noise
            and shading it would invent a pattern. Missingness in <code>income</code> and <code>credit_history_years</code> is
            informative here &mdash; the absence of the field predicts risk on its own, and both models get an explicit missing
            indicator for that reason. Only <code>employment_tenure</code> steps, and it steps hard enough to be the one drift
            the detectors caught in the month it started.
          </p>
        </Card>
      </Section>

      <Section title="False-alarm control" meta="same rules, all four switches off">
        <Note tone="sage" title="A detector that always fires is not a detector.">
          The same monitoring stack was run a second time over a stationary population of{' '}
          {CONTROL.rows.toLocaleString('en-US')} applications generated with every drift switch off. Base default rate{' '}
          {pct(CONTROL.badRateYear1)} in year one and {pct(CONTROL.badRateYear2)} in year two. Anything it fires is a false
          alarm by construction.
        </Note>
        <div style={{ height: 18 }} />
        <TableCard minWidth={660}>
          <thead>
            <tr>
              <th>Rule</th>
              <th className="n">Alerts on the drifted cohort</th>
              <th className="n">False alarms on the control</th>
              <th>Reading</th>
            </tr>
          </thead>
          <tbody>
            {BY_RULE.map((r) => (
              <tr key={r.rule}>
                <td className="mono">{r.rule}</td>
                <td className="n">{r.drifted}</td>
                <td className="n">{r.control}</td>
                <td>
                  <span className={r.kind === 'ok' ? 'pill pill--sage' : r.kind === 'bad' ? 'pill pill--clay' : 'pill pill--idle'}>
                    {r.verdict}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </TableCard>
        <p className="small faint" style={{ margin: '12px 0 0', maxWidth: '88ch' }}>
          Two rules deserve comment. <code>score_psi</code> never fires on either cohort &mdash; it is not producing false
          alarms, it is simply blind here. <code>auc_floor</code> fires on the stationary control too, because it compares
          against a fixed 0.70 floor that happens to sit close to this model&rsquo;s genuine out-of-sample level. That is a
          badly chosen threshold, not evidence of drift, and it is exactly the kind of thing a control run exposes.
        </p>
      </Section>

      <Section title="Verification against the injected drift" meta="scored against a known schedule">
        <TableCard minWidth={760}>
          <thead>
            <tr>
              <th>Injected drift</th><th className="n">Injected from</th><th>Detector</th>
              <th className="n">First alert</th><th className="n">Detection lag</th><th className="n">Alerts</th><th>Result</th>
            </tr>
          </thead>
          <tbody>
            {VERIFICATION.map((v) => (
              <tr key={v.injected}>
                <td>{v.injected}</td>
                <td className="n">month {v.starts}</td>
                <td className="mono">{v.detector}</td>
                <td className="n">month {v.first}</td>
                <td className="n">{v.lag} months</td>
                <td className="n">{v.alerts}</td>
                <td><span className={v.detected ? 'pill pill--sage' : 'pill pill--clay'}>{v.detected ? 'detected' : 'missed'}</span></td>
              </tr>
            ))}
          </tbody>
        </TableCard>
        <Note tone="sage" title="This table is the whole argument for synthetic data.">
          Because the generator wrote the drift schedule, each detector can be scored rather than admired. The lags are the
          interesting part: three of the four drifts are linear ramps, and a ramp has to grow for several months before a fixed
          threshold on a {META.perMonth.toLocaleString('en-US')}-application cohort can separate it from noise. On a real
          portfolio you would never know whether a quiet month meant no drift or an insensitive detector.
        </Note>
      </Section>

      <Section title="The full alert stack" meta={`${ALERTS.length} of ${ALERT_TOTALS.total} shown · one rule per row`}>
        <AlertRail alerts={ALERTS} />
      </Section>
    </div>
  );
}
