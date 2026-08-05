export const fmt = (x: number | null | undefined, p = 3) =>
  x == null || !isFinite(x) ? 'n/a' : x.toLocaleString('en-US', { minimumFractionDigits: p, maximumFractionDigits: p });

export const pct = (x: number | null | undefined, p = 1) => (x == null ? 'n/a' : `${(x * 100).toFixed(p)}%`);

export const sgn = (x: number, p = 3) => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(p)}`;

export const money = (x: number) => {
  const s = x < 0 ? '−' : '';
  const v = Math.abs(x);
  if (v >= 1e6) return `${s}${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${s}${(v / 1e3).toFixed(1)}k`;
  return `${s}${Math.round(v)}`;
};

/** Chart formats are named rather than passed as functions: a server component
 *  cannot hand a closure to a client component, and every chart on the site is
 *  rendered from a server page. */
export type Fmt = 'n0' | 'n2' | 'n3' | 'pct' | 'money' | 'plain';

export const format = (kind: Fmt | undefined, v: number, fallbackPlaces: number): string => {
  switch (kind) {
    case 'n0': return v.toFixed(0);
    case 'n2': return v.toFixed(2);
    case 'n3': return v.toFixed(3);
    case 'pct': return pct(v);
    case 'money': return money(v);
    case 'plain': return String(v);
    default: return v.toFixed(fallbackPlaces);
  }
};

export const ci = (v: number, lo: number, hi: number, p = 3) =>
  `${v.toFixed(p)}  [${lo.toFixed(p)}, ${hi.toFixed(p)}]`;

/** Heat level for a magnitude, against the PSI convention stops by default. */
export const heatLevel = (v: number, stops: number[] = [0.02, 0.05, 0.1, 0.25]) => {
  for (let i = 0; i < stops.length; i++) if (v < stops[i]) return i;
  return 4;
};

/** Graphics ramp: fills, strokes, chart lines, display-size numerals. */
export const HEAT = ['var(--heat-0)', 'var(--heat-1)', 'var(--heat-2)', 'var(--heat-3)', 'var(--heat-4)'] as const;
/** Text ramp: same hues, deep enough to clear AA at interface size. */
export const HEAT_T = ['var(--heat-t-0)', 'var(--heat-t-1)', 'var(--heat-t-2)', 'var(--heat-t-3)', 'var(--heat-t-4)'] as const;
const MIX = [12, 30, 44, 58, 72];
/** Cell fill for a heat level — the ramp colour mixed into the card surface. */
export const heatFill = (level: number) => `color-mix(in srgb, ${HEAT[level]} ${MIX[level]}%, var(--surface))`;
