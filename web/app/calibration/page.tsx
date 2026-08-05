import Link from 'next/link';
import LineChart from '@/components/charts/LineChart';
import { Card, Note, PageHead, Section } from '@/components/Page';
import { CALIBRATION, CALIBRATION_META, META, RELIABILITY, RELIABILITY_DOMAIN } from '@/lib/artifacts';
import { HEAT, HEAT_T, sgn } from '@/lib/format';

export const metadata = { title: 'Calibration · Credy' };

export default function Calibration() {
  const [valFrom, valTo] = META.splits.validation;
  const [xMin, xMax, yMin, yMax] = RELIABILITY_DOMAIN;
  const tick = (i: number) => xMin + ((xMax - xMin) * i) / 4;
  return (
    <div className="page" data-screen-label="Calibration">
      <PageHead kicker="Level, not order" meta="10 equal-count bins on the test months" title="Calibration">
        A model can rank applicants correctly and still be wrong about how much risk it is holding. Ranking is what AUC
        measures; <em style={{ fontFamily: 'var(--font-serif), serif', fontSize: 18 }}>level</em> is what a price, a provision
        and a capital number depend on. They fail separately, so they are tracked separately.
      </PageHead>

      <Section title="Three variants, one reference line" meta={`recalibrators fitted on ${CALIBRATION_META.fittedOn}`}>
        <div className="metrics" style={{ marginBottom: 18 }}>
          {CALIBRATION.map((v) => (
            <div key={v.label} className="metric" style={{ borderTop: `3px solid ${HEAT[v.heat]}` }}>
              <div className="metric-label">{v.label}</div>
              <div className="metric-value" style={{ color: HEAT_T[v.heat] }}>{v.slope.toFixed(3)}</div>
              <div className="metric-sub">
                slope against a perfect 1.000 &middot;{' '}
                {`${Math.abs(Math.round((1 - v.slope) * 100))}% ${v.slope < 1 ? 'flatter' : 'steeper'} than perfect`}
              </div>
              <div style={{ display: 'flex', gap: 16, marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
                <span style={{ fontSize: 11, color: 'var(--faint)' }}>intercept <b className="num" style={{ color: 'var(--ink)' }}>{sgn(v.intercept)}</b></span>
                <span style={{ fontSize: 11, color: 'var(--faint)' }}>Brier <b className="num" style={{ color: 'var(--ink)' }}>{v.brier.toFixed(5)}</b></span>
                <span style={{ fontSize: 11, color: 'var(--faint)' }}>ECE <b className="num" style={{ color: 'var(--ink)' }}>{v.ece.toFixed(4)}</b></span>
              </div>
            </div>
          ))}
        </div>

        <Card>
          <LineChart
            height={360}
            xLabel="Mean predicted probability of default in bin"
            yLabel="Observed default rate in bin"
            xMin={xMin}
            xMax={xMax}
            yMin={yMin}
            yMax={yMax}
            diagonal
            xTicks={[0, 1, 2, 3, 4].map(tick)}
            readoutPrefix="bin at "
            formatX="n3"
            formatValue="n3"
            series={[
              { label: 'Raw model output', color: HEAT[4], points: RELIABILITY.raw },
              { label: 'Platt scaling', color: HEAT[2], points: RELIABILITY.platt },
              { label: 'Isotonic regression', color: HEAT[1], points: RELIABILITY.isotonic },
            ]}
          />
        </Card>
        <Note tone="gold" title="Read it as a distance, not a shape.">
          The closer a curve sits to the dashed 45&deg; line, the better calibrated that variant is. Everything above the line
          is under-prediction: bins where more applicants defaulted than the model expected. All three variants spend most of
          the range above it, because the recalibrators were fitted on validation months {valFrom}&ndash;{valTo} and the
          population kept moving afterwards. Recalibration is not a fix for drift; it is a snapshot that also goes stale.
        </Note>
      </Section>

      <Section title="What recalibration can and cannot buy">
        <div className="cards">
          <Card>
            <div className="metric-label" style={{ color: 'var(--sage-ink)' }}>It buys</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              A better <b style={{ color: 'var(--ink)' }}>level</b>. Both recalibrators pull the Brier score down without
              reordering applicants: AUC is bit-identical after Platt ({CALIBRATION_META.aucUnchanged.platt.toFixed(4)} against{' '}
              {CALIBRATION_META.aucUnchanged.raw.toFixed(4)} raw) and moves only where isotonic collapses ties (
              {CALIBRATION_META.aucUnchanged.isotonic.toFixed(4)}). If the number is going into a price or a provision, this
              step is not optional &mdash; but note the slope: fitted on {CALIBRATION_META.fittedOn}, it is already stale by the
              test months.
            </p>
          </Card>
          <Card>
            <div className="metric-label" style={{ color: 'var(--clay-ink)' }}>It cannot buy</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              Any <b style={{ color: 'var(--ink)' }}>ranking</b> at all. A monotone map cannot rescue a model that has stopped
              separating good from bad, and it cannot see a concept drift that changed what a feature means. That is what the{' '}
              <Link href="/drift">drift page</Link> is for.
            </p>
          </Card>
        </div>
      </Section>
    </div>
  );
}
