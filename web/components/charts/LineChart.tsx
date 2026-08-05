'use client';

import { useState } from 'react';
import { format, type Fmt } from '@/lib/format';

export type Series = {
  label: string;
  color: string;
  points: number[][]; // [x, y] or [x, y, lo, hi]
  band?: boolean;
  dashed?: boolean;
  dots?: boolean;
  width?: number;
};

export type LineChartProps = {
  series: Series[];
  xLabel?: string;
  yLabel?: string;
  height?: number;
  xTicks?: number[];
  yTicks?: number[];
  xMin?: number;
  xMax?: number;
  yMin?: number;
  yMax?: number;
  yPlaces?: number;
  formatX?: Fmt;
  formatY?: Fmt;
  formatValue?: Fmt;
  readoutPrefix?: string;
  /** Horizontal reference line — an agreed floor, an alert threshold. */
  refLine?: number;
  refLabel?: string;
  /** Vertical marker — a chosen operating point. Drawn as a dashed rule so it
   *  never covers the curves it is meant to help you read. */
  markerX?: number;
  markerLabel?: string;
  /** Wide, low-alpha background bands: the train / validation / test windows. */
  spans?: { from: number; to: number; fill: string; label?: string }[];
  /** Draw the 45 degree line (reliability curves only). */
  diagonal?: boolean;
  minWidth?: number;
};

const W = 780;
const PAD = { left: 62, right: 18, top: 16, bottom: 48 };

export default function LineChart(props: LineChartProps) {
  const {
    series, xLabel, yLabel, height = 300, xTicks = [], yTicks, yPlaces = 2,
    formatX, formatY, formatValue, readoutPrefix = '', refLine, refLabel,
    markerX, markerLabel, spans = [], diagonal, minWidth = 600,
  } = props;

  const [readout, setReadout] = useState<{ x: number; values: { label: string; color: string; v: number | null }[] } | null>(null);

  const H = height;
  const xs = series.flatMap((s) => s.points.map((p) => p[0]));
  const xMin = props.xMin ?? Math.min(...xs);
  const xMax = props.xMax ?? Math.max(...xs);

  const ys = series.flatMap((s) => s.points.flatMap((p) => [p[1], p[2] ?? p[1], p[3] ?? p[1]]));
  if (refLine != null) ys.push(refLine);
  let yMin = props.yMin ?? Math.min(...ys);
  let yMax = props.yMax ?? Math.max(...ys);
  const pad = ((yMax - yMin) || 0.02) * 0.1;
  if (props.yMin == null) yMin -= pad;
  if (props.yMax == null) yMax += pad;

  const X = (v: number) => PAD.left + ((v - xMin) / (xMax - xMin || 1)) * (W - PAD.left - PAD.right);
  const Y = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * (H - PAD.top - PAD.bottom);

  const yGrid = yTicks ?? [0, 1, 2, 3, 4].map((i) => yMin + ((yMax - yMin) * i) / 4);
  const plotMid = PAD.top + (H - PAD.bottom - PAD.top) / 2;

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const v = xMin + ((e.clientX - rect.left) / rect.width) * (xMax - xMin);
    let index = 0;
    let best = Infinity;
    series[0].points.forEach((p, i) => {
      const d = Math.abs(p[0] - v);
      if (d < best) { best = d; index = i; }
    });
    setReadout({
      x: series[0].points[index][0],
      values: series.map((s) => {
        const p = s.points[index] ?? s.points[s.points.length - 1];
        return { label: s.label, color: s.color, v: p ? p[1] : null };
      }),
    });
  };

  return (
    <div className="chart">
      <div className="chart-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth }} role="img" aria-label={xLabel ?? 'chart'}>
          {yGrid.map((v, i) => (
            <g key={`y${i}`}>
              <line x1={PAD.left} x2={W - PAD.right} y1={Y(v)} y2={Y(v)} stroke="var(--line)" />
              <text x={PAD.left - 10} y={Y(v) + 3.5} textAnchor="end" fontSize={10.5} fill="var(--faint)" fontFamily="var(--font-mono), monospace">
                {format(formatY, v, yPlaces)}
              </text>
            </g>
          ))}

          {xTicks.map((v, i) => (
            <g key={`x${i}`}>
              <line x1={X(v)} x2={X(v)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--line)" />
              <text x={X(v)} y={H - PAD.bottom + 20} textAnchor="middle" fontSize={10.5} fill="var(--faint)" fontFamily="var(--font-mono), monospace">
                {format(formatX, v, 0)}
              </text>
            </g>
          ))}

          {spans.map((s, i) => (
            <g key={`s${i}`} data-anim="fade">
              <rect x={X(s.from)} y={PAD.top} width={X(s.to) - X(s.from)} height={H - PAD.bottom - PAD.top} fill={s.fill} />
              {s.label ? (
                <text x={(X(s.from) + X(s.to)) / 2} y={PAD.top + 14} textAnchor="middle" fontSize={10} fill="var(--faint)" fontFamily="var(--font-mono), monospace" letterSpacing="0.08em">
                  {s.label}
                </text>
              ) : null}
            </g>
          ))}

          {diagonal ? (
            <>
              <line x1={X(xMin)} y1={Y(xMin)} x2={X(Math.min(xMax, yMax))} y2={Y(Math.min(xMax, yMax))} stroke="var(--line-2)" strokeWidth={1.25} strokeDasharray="6 5" />
              <text
                x={X(xMin + (xMax - xMin) * 0.52)}
                y={Y(xMin + (xMax - xMin) * 0.52) - 9}
                fontSize={10.5}
                fill="var(--muted)"
                fontFamily="var(--font-mono), monospace"
                transform={`rotate(-24 ${X(xMin + (xMax - xMin) * 0.52)} ${Y(xMin + (xMax - xMin) * 0.52) - 9})`}
              >
                perfect calibration: predicted = observed
              </text>
            </>
          ) : null}

          {refLine != null ? (
            <>
              <line x1={PAD.left} x2={W - PAD.right} y1={Y(refLine)} y2={Y(refLine)} stroke="var(--heat-2)" strokeWidth={1.25} strokeDasharray="5 4" opacity={0.8} />
              <text x={W - PAD.right} y={Y(refLine) - 7} textAnchor="end" fontSize={10.5} fill="var(--heat-t-2)" fontFamily="var(--font-mono), monospace">
                {refLabel}
              </text>
            </>
          ) : null}

          {markerX != null ? (() => {
            // Flip the label inward past 70% of the plot width, or it runs off
            // the viewBox and gets clipped by the svg's overflow.
            const mx = X(markerX);
            const flip = mx > PAD.left + (W - PAD.left - PAD.right) * 0.7;
            return (
              <>
                <line x1={mx} x2={mx} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--terra)" strokeWidth={1.5} strokeDasharray="5 4" />
                <text x={flip ? mx - 7 : mx + 7} y={PAD.top + 12} textAnchor={flip ? 'end' : 'start'} fontSize={10.5} fill="var(--terra-ink)" fontFamily="var(--font-mono), monospace">
                  {markerLabel}
                </text>
              </>
            );
          })() : null}

          {series.map((s, si) => {
            const path = s.points.map((p, i) => `${i ? 'L' : 'M'}${X(p[0])} ${Y(p[1])}`).join(' ');
            const up = s.points.map((p) => `${X(p[0])},${Y(p[3] ?? p[1])}`).join(' ');
            const down = [...s.points].reverse().map((p) => `${X(p[0])},${Y(p[2] ?? p[1])}`).join(' ');
            return (
              <g key={si}>
                {s.band ? <polygon points={`${up} ${down}`} fill={s.color} opacity={0.14} data-anim="fade" style={{ animationDelay: '0.2s' }} /> : null}
                <path
                  d={path}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={s.width ?? 2.25}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeDasharray={s.dashed ? '6 5' : '1'}
                  pathLength={s.dashed ? undefined : 1}
                  data-anim={s.dashed ? 'fade' : 'draw'}
                  style={{ strokeDashoffset: 0 }}
                />
                {s.dots !== false
                  ? s.points.map((p, i) => (
                      <circle key={i} cx={X(p[0])} cy={Y(p[1])} r={2.6} fill={s.color} data-anim="fade" style={{ animationDelay: `${0.5 + i * 0.012}s` }} />
                    ))
                  : null}
              </g>
            );
          })}

          {readout ? <line x1={X(readout.x)} x2={X(readout.x)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--terra)" strokeWidth={1.25} opacity={0.7} /> : null}

          {yLabel ? (
            <text x={16} y={plotMid} textAnchor="middle" fontSize={11} fill="var(--muted)" transform={`rotate(-90 16 ${plotMid})`}>
              {yLabel}
            </text>
          ) : null}
          {xLabel ? (
            <text x={PAD.left + (W - PAD.left - PAD.right) / 2} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--muted)">
              {xLabel}
            </text>
          ) : null}

          <rect
            x={PAD.left}
            y={PAD.top}
            width={W - PAD.left - PAD.right}
            height={H - PAD.bottom - PAD.top}
            fill="transparent"
            style={{ cursor: 'crosshair' }}
            onMouseMove={onMove}
            onMouseLeave={() => setReadout(null)}
          />
        </svg>
      </div>

      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.label}>
            <i style={s.dashed ? { borderTop: `3px dashed ${s.color}` } : { background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>

      {/* The readout is part of the chart frame, not a tooltip that follows the
          cursor: on a chart whose job is comparison, the numbers belong in one
          predictable place. */}
      <div className="readout">
        {readout ? (
          <>
            <b className="readout-at">{readoutPrefix}{format(formatX, readout.x, 0)}</b>
            {readout.values.map((v) => (
              <span key={v.label}>
                <i style={{ background: v.color }} />
                {v.label}
                <b>{v.v == null ? 'n/a' : format(formatValue, v.v, yPlaces + 1)}</b>
              </span>
            ))}
          </>
        ) : (
          <span className="faint" style={{ fontSize: 11.5 }}>hover the plot to read values</span>
        )}
      </div>
    </div>
  );
}
