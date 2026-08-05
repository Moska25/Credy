import { HEAT, HEAT_T } from '@/lib/format';

export type Lane = {
  label: string;
  sub?: string;
  value: number;
  lo: number;
  hi: number;
  color?: string;
  /** Text-safe counterpart for the numeric label. Defaults from `color`. */
  textColor?: string;
};

/**
 * Point estimate and 95% interval per lane, on one shared domain. Sharing the
 * domain is the whole point: four panels on four scales look comparable and
 * are not, which is how the eye stops comparing them.
 */
export default function IntervalChart({
  lanes, xLabel, domain, rowHeight = 74, gap, width = 780, minWidth = 340,
}: {
  lanes: Lane[];
  xLabel?: string;
  domain?: [number, number];
  rowHeight?: number;
  /** Shade the clear air between two disjoint intervals. */
  gap?: [number, number];
  width?: number;
  minWidth?: number;
}) {
  const W = width;
  const H = lanes.length * rowHeight + 46;

  const values = lanes.flatMap((l) => [l.lo, l.hi]);
  let [x0, x1] = domain ?? [Math.min(...values), Math.max(...values)];
  if (!domain) {
    const pad = (x1 - x0) * 0.12;
    x0 -= pad;
    x1 += pad;
  }
  const X = (v: number) => ((v - x0) / (x1 - x0)) * W;
  const ticks = [0, 1, 2, 3, 4].map((i) => x0 + ((x1 - x0) * i) / 4);

  return (
    <div className="chart-scroll">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth }} role="img" aria-label={xLabel ?? 'intervals'}>
        {ticks.map((v, i) => (
          <g key={i}>
            <line x1={X(v)} x2={X(v)} y1={0} y2={H - 46} stroke="var(--line)" />
            <text x={X(v)} y={H - 26} textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'} fontSize={10.5} fill="var(--faint)" fontFamily="var(--font-mono), monospace">
              {v.toFixed(3)}
            </text>
          </g>
        ))}

        {gap ? (
          <g data-anim="fade" style={{ animationDelay: '0.3s' }}>
            <rect x={X(gap[0])} y={0} width={X(gap[1]) - X(gap[0])} height={H - 46} fill="color-mix(in srgb, var(--clay) 15%, transparent)" />
            {gap.map((v, i) => (
              <line key={i} x1={X(v)} x2={X(v)} y1={0} y2={H - 46} stroke={HEAT[4]} strokeWidth={1.25} strokeDasharray="4 4" />
            ))}
          </g>
        ) : null}

        {lanes.map((lane, i) => {
          const cy = i * rowHeight + rowHeight * 0.74;
          const color = lane.color ?? HEAT[1];
          const textColor = lane.textColor ?? HEAT_T[1];
          return (
            <g key={lane.label}>
              <line
                x1={X(lane.lo)} x2={X(lane.hi)} y1={cy} y2={cy}
                stroke={color} strokeWidth={2.5}
                pathLength={1} strokeDasharray={1}
                data-anim="draw"
                style={{ strokeDashoffset: 0, animationDelay: `${0.15 + i * 0.1}s` }}
              />
              {[lane.lo, lane.hi].map((v, k) => (
                <line key={k} x1={X(v)} x2={X(v)} y1={cy - 6} y2={cy + 6} stroke={color} strokeWidth={2.5} data-anim="fade" style={{ animationDelay: `${0.8 + i * 0.1}s` }} />
              ))}
              <circle cx={X(lane.value)} cy={cy} r={5.5} fill={color} data-anim="fade" style={{ animationDelay: `${0.85 + i * 0.1}s` }} />
              <text x={2} y={i * rowHeight + 20} fontSize={14} fontWeight={700} fill="var(--ink)">{lane.label}</text>
              {lane.sub ? <text x={2} y={i * rowHeight + 38} fontSize={11.5} fill="var(--muted)">{lane.sub}</text> : null}
              <text x={W - 2} y={i * rowHeight + 22} textAnchor="end" fontSize={14} fontWeight={600} fill={textColor} fontFamily="var(--font-mono), monospace">
                {lane.value.toFixed(3)}  [{lane.lo.toFixed(3)}, {lane.hi.toFixed(3)}]
              </text>
            </g>
          );
        })}

        {xLabel ? <text x={W / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--muted)">{xLabel}</text> : null}
      </svg>
    </div>
  );
}
