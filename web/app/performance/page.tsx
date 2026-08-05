import Link from 'next/link';
import LineChart from '@/components/charts/LineChart';
import { Card, Metric, Note, PageHead, Section, TableCard } from '@/components/Page';
import { AUC, AUC_HI, AUC_LO, BAD_RATE, COMPARISON, DECAY, MEAN_PREDICTED, META, MONTHS, OPERATING_POINTS, PER_MODEL, THRESHOLDS } from '@/lib/artifacts';
import { HEAT, HEAT_T, ci, pct, sgn } from '@/lib/format';

export const metadata = { title: 'Performance · Credy' };

export default function Performance() {
  const [valFrom, valTo] = META.splits.validation;
  const [testFrom, testTo] = META.splits.test;
  const last = MONTHS.length - 1;
  return (
    <div className="page" data-screen-label="Performance">
      <PageHead kicker="Discrimination" meta={`${META.nBoot} bootstrap resamples per interval`} title="Performance">
        Every headline number carries a 95% percentile bootstrap interval, and the same three models are re-run under a naive
        random split so the size of that shortcut is on the page rather than in a footnote.
      </PageHead>

      <Section title="Temporal split versus random split">
        <TableCard minWidth={700}>
          <thead>
            <tr>
              <th>Model</th>
              <th className="n">Temporal test AUC</th>
              <th className="n">Random test AUC</th>
              <th className="n">Overstatement</th>
              <th>Intervals</th>
            </tr>
          </thead>
          <tbody>
            {COMPARISON.map((c) => (
              <tr key={c.label}>
                <td>
                  {c.label}
                  {c.champion ? <span className="num" style={{ marginLeft: 8, fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--terra-ink)' }}>champion</span> : null}
                </td>
                <td className="n">{ci(c.temporal[0], c.temporal[1], c.temporal[2])}</td>
                <td className="n">{ci(c.random[0], c.random[1], c.random[2])}</td>
                <td className="n" style={{ color: c.disjoint ? HEAT_T[4] : 'var(--faint)' }}>{sgn(c.overstatement)}</td>
                <td>
                  <span className={c.disjoint ? 'pill pill--clay' : 'pill pill--idle'}>{c.disjoint ? 'disjoint' : 'overlap'}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </TableCard>
        <Note title="How to read this.">
          Both columns evaluate the same model family on the same {META.rows.toLocaleString('en-US')} applicants with identical
          window sizes ({META.splitSizes.train.toLocaleString('en-US')} / {META.splitSizes.validation.toLocaleString('en-US')} /{' '}
          {META.splitSizes.test.toLocaleString('en-US')}). The only difference is that the random split lets rows from months{' '}
          {testFrom}&ndash;{testTo} into training. The scorecard is affected least, which is exactly what you would expect: a
          fixed points table cannot memorise a period it was never fitted on.
        </Note>
      </Section>

      <Section title="All three models, all three windows" meta="temporal split only">
        <TableCard minWidth={900}>
          <thead>
            <tr>
              <th>Model</th><th>Window</th><th className="n">Rows</th><th className="n">Bad rate</th>
              <th className="n">AUC (95% CI)</th><th className="n">Gini</th><th className="n">KS</th>
              <th className="n">Log loss</th><th className="n">Brier</th><th className="n">Cal. slope</th>
            </tr>
          </thead>
          <tbody>
            {PER_MODEL.flatMap((m) =>
              m.windows.map((w, i) => (
                <tr key={`${m.label}-${w.window}`} style={i === 0 ? { borderTop: '1px solid var(--line-2)' } : undefined}>
                  <td style={{ fontWeight: 600 }}>{i === 0 ? m.label : ''}</td>
                  <td className="mono">{w.window}{w.window === 'train' ? <span className="faint"> (in-sample)</span> : null}</td>
                  <td className="n">{w.n.toLocaleString('en-US')}</td>
                  <td className="n">{pct(w.badRate)}</td>
                  <td className="n">{ci(w.auc, w.lo, w.hi)}</td>
                  <td className="n">{w.gini.toFixed(3)}</td>
                  <td className="n">{w.ks.toFixed(3)}</td>
                  <td className="n">{w.logLoss.toFixed(3)}</td>
                  <td className="n">{w.brier.toFixed(4)}</td>
                  <td className="n">{w.slope.toFixed(2)}</td>
                </tr>
              )),
            )}
          </tbody>
        </TableCard>
        <p className="small faint" style={{ margin: '12px 0 0', maxWidth: '88ch' }}>
          Train-window rows are in-sample and are shown only so the overfitting gap is visible. Gradient boosting stops early
          on a random 15% slice of the training months, which is why its in-sample AUC is not absurd.
        </p>
      </Section>

      <Section title="Month by month: does it decay?" meta={`${META.champion.toLowerCase()}, ${META.nBootMonthly} resamples per month`}>
        <Card>
          <LineChart
            height={300}
            xLabel="Application month (1 = first cohort)"
            yLabel="AUC"
            xTicks={[1, 4, 8, 12, 16, 20, 24]}
            refLine={THRESHOLDS.aucFloor}
            refLabel="agreed floor"
            readoutPrefix="month "
            formatValue="n3"
            spans={[
              { from: valFrom, to: valTo, fill: 'color-mix(in srgb, var(--sage) 8%, transparent)', label: 'validation' },
              { from: testFrom, to: testTo, fill: 'color-mix(in srgb, var(--clay) 8%, transparent)', label: 'test' },
            ]}
            series={[{ label: 'AUC with 95% CI', color: HEAT[3], band: true, points: MONTHS.map((m, i) => [m, AUC[i], AUC_LO[i], AUC_HI[i]]) }]}
          />
        </Card>
        <div style={{ height: 14 }} />
        <Card>
          <LineChart
            height={300}
            xLabel="Application month"
            yLabel="Share of applications"
            xTicks={[1, 4, 8, 12, 16, 20, 24]}
            yMin={0}
            readoutPrefix="month "
            formatValue="pct"
            series={[
              { label: 'Observed default rate', color: HEAT[4], points: MONTHS.map((m, i) => [m, BAD_RATE[i]]) },
              { label: 'Mean predicted PD', color: HEAT[1], points: MONTHS.map((m, i) => [m, MEAN_PREDICTED[i]]) },
            ]}
          />
        </Card>
        <Note tone="clay" title="The two charts say different things.">
          The first is about <em>ranking</em>, and it sags modestly. The second is about <em>level</em>, and the two lines come
          apart completely: by month {MONTHS[last]} the observed default rate is {pct(BAD_RATE[last])} while the model still
          predicts an average of {pct(MEAN_PREDICTED[last])}. A model can keep ranking applicants correctly while being badly wrong about how
          much risk it is looking at &mdash; which is why <Link href="/calibration">calibration</Link> is tracked separately.
        </Note>
      </Section>

      <Section title="Did discrimination actually decline?">
        <div className="metrics">
          <Metric small label="AUC, validation window" value={ci(DECAY.validation.auc, DECAY.validation.lo, DECAY.validation.hi)}
            sub={`months ${valFrom}–${valTo}`} />
          <Metric small label="AUC, test window" value={ci(DECAY.test.auc, DECAY.test.lo, DECAY.test.hi)}
            sub={`months ${testFrom}–${testTo}, never used for fitting`} />
          <Metric small label="Difference (val − test)" value={sgn(DECAY.delta)} color="var(--clay-ink)"
            sub={`95% CI [${DECAY.lo.toFixed(3)}, ${DECAY.hi.toFixed(3)}] · excludes zero`} />
        </div>
        <Note tone="gold" title="What this test does and does not prove.">
          Because the interval excludes zero we can say the later window discriminates worse, under the assumption that
          applicants are independent draws. It does <em>not</em> establish a cause: drift, a harder population and simple bad
          luck in one window all produce the same signature. It is also a single comparison chosen after looking at the data.
          Treat it as evidence to open an investigation, not as a finding.
        </Note>
      </Section>

      <Section title="Operating points on the test window">
        <TableCard minWidth={760}>
          <thead>
            <tr>
              <th className="n">Decline the riskiest</th><th className="n">PD cut-off</th><th className="n">Applications declined</th>
              <th className="n">Precision</th><th className="n">Recall of defaulters</th><th className="n">Bad rate among approved</th>
            </tr>
          </thead>
          <tbody>
            {OPERATING_POINTS.map((o) => (
              <tr key={o.rejectRate}>
                <td className="n">{pct(o.rejectRate, 0)}</td>
                <td className="n">{o.threshold.toFixed(4)}</td>
                <td className="n">{o.nRejected.toLocaleString('en-US')}</td>
                <td className="n">{pct(o.precision)}</td>
                <td className="n">{pct(o.recall)}</td>
                <td className="n">{pct(o.approvedBadRate)}</td>
              </tr>
            ))}
          </tbody>
        </TableCard>
        <p className="small faint" style={{ margin: '12px 0 0', maxWidth: '88ch' }}>
          Precision here is the share of declined applications that really would have defaulted. Turning these into money needs
          a loss given default and a margin &mdash; that is the <Link href="/policy">policy simulator</Link>.
        </p>
      </Section>
    </div>
  );
}
