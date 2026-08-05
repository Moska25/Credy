import { heatFill, heatLevel } from '@/lib/format';
import { MONTHS } from '@/lib/artifacts';

export type MatrixRow = {
  feature: string;
  /** The magnitude the shading is computed from. */
  values: number[];
  /** What to print, when it differs from what is shaded (e.g. shade the rise
   *  over reference, print the rate itself). Defaults to `values`. */
  display?: number[];
  reference?: string;
};

/**
 * One heat ramp, used for every magnitude in the app. Cells in the two
 * conventional bands also carry a rule along their top edge, so the cut-points
 * survive greyscale and colour-blind viewing rather than living in hue alone.
 */
export default function HeatMatrix({
  rows, stops, format, showReference, ariaLabel,
}: {
  rows: MatrixRow[];
  /** Band edges. Defaults to the PSI convention. */
  stops?: number[];
  format: (v: number) => string;
  /** Shade against each row's own reference rather than against zero. */
  showReference?: boolean;
  ariaLabel: string;
}) {
  return (
    <div className="table-scroll">
      <table className="matrix" aria-label={ariaLabel}>
        <thead>
          <tr>
            <th className="rowhead" style={{ paddingBottom: 8 }}>Feature</th>
            {showReference ? <th style={{ fontSize: 10 }}>ref</th> : null}
            {MONTHS.map((m) => <th key={m} scope="col">{m}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.feature}>
              <th className="rowhead" scope="row">{row.feature}</th>
              {showReference ? <td className="refcell">{row.reference}</td> : null}
              {row.values.map((v, i) => {
                const level = heatLevel(v, stops);
                return (
                  <td
                    key={i}
                    style={{
                      background: heatFill(level),
                      color: level === 0 ? 'var(--faint)' : 'var(--ink)',
                      borderTopColor: level >= 3 ? `var(--heat-${level})` : 'transparent',
                      fontWeight: level === 4 ? 700 : 500,
                    }}
                  >
                    {format(row.display ? row.display[i] : v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RampLegend() {
  const steps = [
    { level: 0, label: '< 0.02' },
    { level: 1, label: '0.02–0.05' },
    { level: 2, label: '0.05–0.10' },
    { level: 3, label: '0.10–0.25 · "watch"', convention: true },
    { level: 4, label: '> 0.25 · "shifted"', convention: true },
  ];
  return (
    <div className="ramp">
      {steps.map((s) => (
        <div key={s.level} className={s.convention ? 'ramp-step ramp-step--convention' : 'ramp-step'}>
          <b style={{ background: heatFill(s.level) }} />
          <em>{s.label}</em>
        </div>
      ))}
    </div>
  );
}
