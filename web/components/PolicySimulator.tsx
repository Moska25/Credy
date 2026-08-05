'use client';

import { useMemo, useState } from 'react';
import LineChart from '@/components/charts/LineChart';
import { Card, Metric, Note, Section } from '@/components/Page';
import { money, pct } from '@/lib/format';
import { POLICY } from '@/lib/artifacts';
import {
  DEFAULT_ECONOMICS, DEFAULT_INDEX, PRESETS, THRESHOLD_GRID,
  applyEconomics, argmaxProfit, curve, indexForPreset, nearestIndex,
  type Economics,
} from '@/lib/policy';

const int = (x: number) => Math.round(x).toLocaleString('en-US');

export default function PolicySimulator() {
  const [index, setIndex] = useState(DEFAULT_INDEX);
  const [econ, setEcon] = useState<Economics>(DEFAULT_ECONOMICS);
  const [preset, setPreset] = useState<string | null>('balanced');

  const model = useMemo(() => {
    const test = curve('test', econ);
    const reference = curve('reference', econ);
    const chosen = test[index];
    const bestNow = argmaxProfit(test);
    const bestAtDeployment = argmaxProfit(reference);
    const held = test[nearestIndex(bestAtDeployment.threshold)];
    const gap = bestNow.profit - held.profit;
    const presetRows = PRESETS.map((p) => ({ ...p, row: test[indexForPreset(p.name)] }));
    return { test, reference, chosen, bestNow, bestAtDeployment, held, gap, presetRows };
  }, [econ, index]);

  const { chosen } = model;

  const applyPreset = (name: string) => {
    setIndex(indexForPreset(name));
    setPreset(name);
  };

  const ledger = [
    `principal approved   = ${int(chosen.principal)}`,
    `  of which good      = ${int(chosen.goodPrincipal)}`,
    `  of which defaulted = ${int(chosen.badPrincipal)}`,
    '',
    `revenue     = margin ${econ.margin.toFixed(2)} × good principal      = ${int(chosen.revenue)}`,
    `credit loss = lgd ${econ.lgd.toFixed(2)} × defaulted principal    = ${int(chosen.creditLoss)}`,
    `opportunity = ${econ.falseDeclineCost} × ${int(chosen.goodDeclined)} good applicants declined = ${int(chosen.opportunityCost)}`,
    `profit      = revenue − credit loss − opportunity      = ${int(chosen.profit)}`,
  ].join('\n');

  return (
    <>
      <section className="section">
        <Card variant="accent">
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 6 }}>
            <label htmlFor="threshold" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--faint)' }}>
              Approval threshold &mdash; approve if PD below
            </label>
            <span className="num" style={{ fontSize: 26, fontWeight: 600, color: 'var(--terra-ink)', letterSpacing: '-0.02em' }}>
              {chosen.threshold.toFixed(4)}
            </span>
          </div>

          <input
            id="threshold"
            type="range"
            min={0}
            max={THRESHOLD_GRID.length - 1}
            step={1}
            value={index}
            onChange={(e) => { setIndex(Number(e.target.value)); setPreset(null); }}
            style={{ height: 26 }}
          />

          <div className="presets">
            {PRESETS.map((p) => (
              <button
                key={p.name}
                type="button"
                className="preset"
                aria-pressed={preset === p.name}
                onClick={() => applyPreset(p.name)}
              >
                {p.name} &middot; {pct(p.targetRate, 0)}
              </button>
            ))}
          </div>

          <div className="control-row">
            <div className="control">
              <label htmlFor="lgd">Loss given default &middot; <b>{pct(econ.lgd, 0)}</b></label>
              <input id="lgd" type="range" min={10} max={100} step={1} value={Math.round(econ.lgd * 100)}
                onChange={(e) => setEcon({ ...econ, lgd: Number(e.target.value) / 100 })} />
            </div>
            <div className="control">
              <label htmlFor="margin">Margin on good principal &middot; <b>{pct(econ.margin, 0)}</b></label>
              <input id="margin" type="range" min={1} max={25} step={1} value={Math.round(econ.margin * 100)}
                onChange={(e) => setEcon({ ...econ, margin: Number(e.target.value) / 100 })} />
            </div>
            <div className="control">
              <label htmlFor="fdc">Cost of a false decline &middot; <b>{econ.falseDeclineCost}</b></label>
              <input id="fdc" type="range" min={0} max={400} step={5} value={econ.falseDeclineCost}
                onChange={(e) => setEcon({ ...econ, falseDeclineCost: Number(e.target.value) })} />
            </div>
          </div>
        </Card>
      </section>

      <Section title={`Outcome at PD < ${chosen.threshold.toFixed(4)}`}>
        <div className="metrics">
          <Metric label="Approval rate" value={pct(chosen.approvalRate)} sub={`${int(chosen.approved)} approved`} />
          <Metric label="Bad rate among approved" value={pct(chosen.approvedBadRate)} color="var(--gold-ink)" sub={`${int(chosen.defaults)} defaults booked`} />
          <Metric label="Expected credit loss" value={money(chosen.creditLoss)} color="var(--clay-ink)"
            sub={`${econ.lgd.toFixed(2)} × ${money(chosen.badPrincipal)} defaulted principal`} />
          <Metric label="Profit" value={money(chosen.profit)} color="var(--terra-ink)"
            sub={`revenue ${money(chosen.revenue)} − loss − opportunity ${money(chosen.opportunityCost)}`} />
        </div>
      </Section>

      <Section title="Expected loss, line by line">
        <Card>
          <pre className="ledger">{ledger}</pre>
          <p className="small faint" style={{ margin: '14px 0 0', maxWidth: '88ch' }}>
            Deliberately simple arithmetic so it can be checked by hand. It assumes a single-period book, full recovery of
            principal on good loans, no funding cost, no operational cost and no prepayment. Loss is realised in full at
            default rather than over a recovery curve.
          </p>
        </Card>
      </Section>

      <Section title="Profit against threshold" meta="both cohorts, same economics">
        <Card>
          <LineChart
            height={340}
            xLabel="Approval threshold (approve if PD below x)"
            yLabel="Profit (currency units)"
            xMin={THRESHOLD_GRID[0]}
            xMax={THRESHOLD_GRID[THRESHOLD_GRID.length - 1]}
            yPlaces={0}
            xTicks={[0.005, 0.12, 0.24, 0.36, 0.48, 0.6]}
            formatX="n2"
            formatY="money"
            formatValue="money"
            readoutPrefix="PD < "
            markerX={chosen.threshold}
            markerLabel="your threshold"
            series={[
              { label: POLICY.testLabel, color: 'var(--heat-3)', dots: false, points: model.test.map((r) => [r.threshold, r.profit]) },
              { label: POLICY.referenceLabel, color: 'var(--heat-1)', dashed: true, dots: false, points: model.reference.map((r) => [r.threshold, r.profit]) },
            ]}
          />
        </Card>
      </Section>

      <Section title="What a stale cut-off costs">
        <Card variant="alarm">
          <div className="verdict">
            <div className="verdict-figure">{money(model.gap)}</div>
            <div className="verdict-body">
              <b>given up by holding the deployment cut-off</b>
              <span>
                {pct(model.gap / model.bestNow.profit)} of the profit available on the test cohort once the threshold is
                re-optimised.
              </span>
            </div>
          </div>

          <div className="metrics" style={{ borderRadius: 20 }}>
            <Metric small label="Optimal at deployment" value={`PD < ${model.bestAtDeployment.threshold.toFixed(4)}`} color="var(--sage-ink)"
              sub={`peak profit ${money(model.bestAtDeployment.profit)} on ${POLICY.referenceLabel}`} />
            <Metric small label="That cut-off, six months later" value={money(model.held.profit)} color="var(--clay-ink)"
              sub={`held unchanged on ${POLICY.testLabel}`} />
            <Metric small label="Optimal now" value={`PD < ${model.bestNow.threshold.toFixed(4)}`} color="var(--terra-ink)"
              sub={`peak profit ${money(model.bestNow.profit)} on ${POLICY.testLabel}`} />
          </div>

          <Note tone="clay">
            The two profit curves peak in different places, and that gap is the whole point of this page. Nothing about the
            model changed: the population did. A cut-off is a parameter with a shelf life, and nobody schedules its review.
          </Note>
        </Card>
      </Section>

      <Section title="Presets, on the current economics">
        <div className="card card--flush">
          <div className="table-scroll">
            <table className="data" style={{ minWidth: 680 }}>
              <thead>
                <tr>
                  <th>Preset</th>
                  <th className="n">Target rate</th>
                  <th className="n">Threshold</th>
                  <th className="n">Actual rate</th>
                  <th className="n">Bad rate approved</th>
                  <th className="n">Expected loss</th>
                  <th className="n">Profit</th>
                </tr>
              </thead>
              <tbody>
                {model.presetRows.map((p) => (
                  <tr key={p.name}>
                    <td style={{ fontWeight: 600 }}>{p.name}</td>
                    <td className="n">{pct(p.targetRate, 0)}</td>
                    <td className="n">{p.row.threshold.toFixed(4)}</td>
                    <td className="n">{pct(p.row.approvalRate)}</td>
                    <td className="n">{pct(p.row.approvedBadRate)}</td>
                    <td className="n">{money(p.row.creditLoss)}</td>
                    <td className="n" style={{ color: 'var(--terra-ink)' }}>{money(p.row.profit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Section>
    </>
  );
}

export { applyEconomics };
