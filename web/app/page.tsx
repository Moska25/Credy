import Link from 'next/link';
import AlertRail from '@/components/AlertRail';
import CountUp from '@/components/CountUp';
import IntervalChart from '@/components/charts/IntervalChart';
import LineChart from '@/components/charts/LineChart';
import { Card, Metric, Note, PageHead, Section, TableCard } from '@/components/Page';
import {
  ALERTS, ALERT_TOTALS, AUC, AUC_HI, AUC_LO, CONTROL, DECAY, HERO, META, MONTHS,
  POLICY, SCORE_PSI_MAX, THRESHOLDS, TOUR, VERIFICATION,
} from '@/lib/artifacts';
import { HEAT, HEAT_T, pct } from '@/lib/format';

export default function Overview() {
  const [trainFrom, trainTo] = META.splits.train;
  const [testFrom, testTo] = META.splits.test;
  return (
    <div className="page" data-screen-label="Overview">
      <PageHead kicker="Control centre" meta={`${META.months} monthly cohorts · ${META.rows.toLocaleString('en-US')} applications`} title="Will it still work in six months?">
        Not <em style={{ fontFamily: 'var(--font-serif), serif', fontSize: 18, fontStyle: 'italic', color: 'var(--ink)' }}>what is my AUC</em> &mdash;
        the question that actually decides whether a credit model was worth building. Everything below is computed once, at
        seed time, from a population whose drift we planted ourselves.
      </PageHead>

      <Note bare title="Synthetic data.">
        All {META.rows.toLocaleString('en-US')} applicants come from a documented data-generating process in <code>app/generate.py</code>.
        No number here is a market benchmark. The point of a known DGP is that the drift is <em>planted</em>, so the detectors
        can be scored rather than trusted.
      </Note>

      <Section title="The headline: how much a random split lies to you" meta="gradient boosting · 95% percentile bootstrap">
        <Card variant="accent">
          <div className="verdict">
            <div className="verdict-figure"><CountUp value={HERO.overstatement} places={3} signed /></div>
            <div className="verdict-body">
              <b>AUC invented by the naive split</b>
              <span>
                {HERO.clearAir
                  ? 'The two intervals do not overlap, so this is not sampling noise.'
                  : 'The intervals overlap, so treat the size of this gap with care.'}
              </span>
            </div>
          </div>
          <IntervalChart
            domain={HERO.domain}
            gap={HERO.clearAir ?? undefined}
            xLabel="Test-window AUC (0.5 = coin flip)"
            lanes={[
              { label: 'Temporal split (honest)', sub: `trained on earlier months, scored on months ${testFrom}-${testTo}`, value: HERO.temporal.auc, lo: HERO.temporal.lo, hi: HERO.temporal.hi, color: HEAT[1], textColor: HEAT_T[1] },
              { label: 'Random split (naive)', sub: 'same model, same row counts, rows shuffled across time', value: HERO.random.auc, lo: HERO.random.lo, hi: HERO.random.hi, color: HEAT[4], textColor: HEAT_T[4] },
            ]}
          />
        </Card>
        <Note title="Why it happens.">
          A random split puts month-{META.months} applications into training, so the model is scored on a population it has already been
          shown. The temporal split forbids that. Same model, same {META.rows.toLocaleString('en-US')} rows &mdash; the only
          difference is which rows were allowed into training.
        </Note>
      </Section>

      <Section title="Stability at a glance" meta={`champion: ${META.champion.toLowerCase()}`}>
        <div className="metrics">
          <Metric label="Alerts fired" color="var(--clay)"
            value={<CountUp value={ALERT_TOTALS.total} />}
            sub={`${ALERT_TOTALS.high} high severity, first in month ${ALERT_TOTALS.firstMonth}`} />
          <Metric label="AUC decay, val → test" color="var(--clay)"
            value={<CountUp value={DECAY.delta} places={3} signed />}
            sub={`95% CI [${DECAY.lo.toFixed(3)}, ${DECAY.hi.toFixed(3)}] · excludes zero`} />
          <Metric label="Score PSI, peak over the window" color="var(--stone)"
            value={<CountUp value={SCORE_PSI_MAX} places={2} />}
            sub="stable band. The coldest tile on this page, and that is the finding" />
          <Metric label="Profit lost to a stale cut-off" color="var(--terra)" value={POLICY.stale.profitGapLabel}
            sub={`${pct(POLICY.stale.profitGapPct)} of the re-optimised profit on the test cohort`} />
        </div>
      </Section>

      <Section title="Open alerts" meta={`${ALERT_TOTALS.total} firing from month ${ALERT_TOTALS.firstMonth} · ${ALERT_TOTALS.high} high`}>
        <AlertRail alerts={ALERTS} limit={5} moreHref="/drift" moreCount={ALERT_TOTALS.total - 5} />
      </Section>

      <Section title="Discrimination month by month" meta={`band = 95% bootstrap CI, ${META.nBootMonthly} resamples per month`}>
        <Card>
          <LineChart
            height={310}
            xLabel="Application month (1 = first cohort)"
            yLabel="AUC"
            xTicks={[1, 4, 8, 12, 16, 20, 24]}
            refLine={THRESHOLDS.aucFloor}
            refLabel={`agreed floor ${THRESHOLDS.aucFloor.toFixed(2)}`}
            readoutPrefix="month "
            formatValue="n3"
            spans={[{ from: trainFrom, to: trainTo, fill: 'color-mix(in srgb, var(--ink) 4%, transparent)', label: `months ${trainFrom}-${trainTo} in-sample` }]}
            series={[{
              label: 'AUC with 95% CI',
              color: HEAT[3],
              band: true,
              points: MONTHS.map((m, i) => [m, AUC[i], AUC_LO[i], AUC_HI[i]]),
            }]}
          />
        </Card>
      </Section>

      <Section title="Did the detectors catch what we planted?">
        <Note tone="sage" title="This is the argument for synthetic data.">
          Each row is a drift we injected on purpose at a known month. A detector that fires on it is doing its job; a blank
          row is a genuine miss. No real dataset can be scored this way.
        </Note>
        <div style={{ height: 18 }} />
        <TableCard minWidth={660}>
          <thead>
            <tr>
              <th>Injected drift</th>
              <th className="n">Starts</th>
              <th>Detector</th>
              <th className="n">First alert</th>
              <th className="n">Lag</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {VERIFICATION.map((v) => (
              <tr key={v.injected}>
                <td>{v.injected}</td>
                <td className="n">month {v.starts}</td>
                <td className="mono">{v.detector}</td>
                <td className="n">month {v.first}</td>
                <td className="n">{v.lag} mo</td>
                <td><span className={v.detected ? 'pill pill--sage' : 'pill pill--clay'}>{v.detected ? 'detected' : 'missed'}</span></td>
              </tr>
            ))}
          </tbody>
        </TableCard>
        <Note tone="gold" title="And the other half of the claim.">
          The identical rules were run again over a stationary control population of {CONTROL.rows.toLocaleString('en-US')} applications
          with every drift switch off. It produced {CONTROL.alerts} alerts against {ALERT_TOTALS.total}, and not one came from a
          drift-specific rule. Hit rate without a false-alarm rate is not evidence &mdash; see <Link href="/drift">the control table</Link>.
        </Note>
      </Section>

      <Section title="The rest of the lab, in one number each" meta="every figure read from the artifacts">
        <ul className="tour">
          {TOUR.map((t) => (
            <li key={t.href}>
              <Link className="tour-go" href={t.href}>{t.label} &rarr;</Link>
              <span className="tour-figure">{t.figure}</span>
              <span className="tour-what">{t.what}</span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
