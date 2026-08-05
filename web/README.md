# Credy — Next.js implementation

The redesigned Credy UI as a Next.js 15 App Router project. Same eight routes as the
FastAPI app, same numbers, the redesigned visual language.

```bash
cd nextjs
npm install
npm run dev      # http://localhost:3000
```

## How it is put together

```
app/
  layout.tsx              shell: fonts, palette attribute, sidebar, palette, entrance flag
  globals.css             ALL tokens + component classes. The only stylesheet.
  page.tsx                /              Overview
  performance/page.tsx    /performance
  calibration/page.tsx    /calibration
  drift/page.tsx          /drift
  subgroups/page.tsx      /subgroups
  policy/page.tsx         /policy        (mounts the client simulator)
  model-card/page.tsx     /model-card
  data/page.tsx           /data

lib/
  artifacts.ts            every precomputed figure. Swap for a fetch and nothing else changes.
  policy.ts               threshold economics: the grid, the cumulative arrays, stale-cut-off cost
  format.ts               number formatting + the heat ramp helpers
  nav.ts                  the eight routes, their groups, and the findings the palette searches

components/
  Sidebar.tsx             client — needs usePathname for the active item
  CommandPalette.tsx      client — ⌘K, arrow keys, filters pages AND findings
  PolicySimulator.tsx     client — the only page with real interaction
  charts/LineChart.tsx    client — hover readout
  charts/IntervalChart.tsx  server — no interaction, so no client boundary
  Page.tsx                PageHead / Section / Card / Metric / Note / TableCard
  AlertRail.tsx  HeatMatrix.tsx  CountUp.tsx  EntranceFlag.tsx
```

Everything that does not need a browser stays a server component. `'use client'`
appears in six files and nowhere else.

## Colour

Three palettes live in `globals.css` as token blocks keyed on `data-palette`:

| Palette | Ground | Character |
| --- | --- | --- |
| `vellum` | cream | the light Organic ground — terracotta accent, deep sage second voice. **The default.** |
| `ember` | deep espresso | warm dark, brighter terracotta, for low-light reading |
| `orchard` | deep green | cooler dark, mint sage reads as a genuine second accent |

Switch by changing one attribute in `app/layout.tsx`:

```tsx
<html data-palette="ember">
```

Wire it to a cookie or a user preference if you want it toggleable. **No component
hard-codes a colour** — every fill, stroke, SVG `fill=` and `stroke=` resolves through
`var(--*)`, which is what makes one attribute enough.

The heat ramp (`--heat-0` … `--heat-4`) is one sequential scale used for every
magnitude — PSI, divergence, risk — and for nothing else. Verdicts use `--sage` and
`--clay` directly. Mixing the two is how a heatmap starts lying.

**Two ramps, and the distinction matters.** Every accent has a base value and an
`-ink` counterpart (`--terra` / `--terra-ink`, `--heat-3` / `--heat-t-3`, and so on):

- **base** — fills, borders, chart strokes, the plate dots, display-size numerals
- **`-ink`** — any accent-coloured *text* at interface size

On the cream ground the base terracotta is 3.8:1 against the page. That is fine for a
2px rule or a 74px serif numeral and below AA for a 10px label, which is what the bound
Organic guide means by "tuned to at least 3:1 — enough for icons, large text and
interface chrome, not for body copy". On the dark palettes the two ramps are identical,
so the split costs nothing there. If you add accent-coloured small text, reach for
`-ink`; if you add a stroke or a fill, reach for the base.

`--faint` is likewise set at 0.74 alpha on vellum rather than the ~0.5 that reads fine
on a dark ground — it carries axis ticks, column headers and metric labels, all of
which are real text at 9.5–12.5px.

## Animation: the one thing not to "simplify"

Entrance animations are scoped to `[data-entered='1']`, and `EntranceFlag` only sets
that attribute after checking `document.timeline` is actually advancing.

This is deliberate, and it is easy to break. If you apply the animations
unconditionally with `animation-fill-mode: both`, then any renderer that does not
advance the timeline — a print pass, an offscreen render, a screenshot pipeline —
pins every animated element to its 0% keyframe. Sections at `opacity: 0`, chart lines
at `stroke-dashoffset: 1`, bars at `scaleX(0)`: a blank page.

So: **the resting state is the finished state.** SVG paths carry
`style={{ strokeDashoffset: 0 }}` and the `draw` keyframe is applied on top; bars
render full width and `grow` scales them in; `CountUp` renders the final number and
only animates if the timeline is live. Content never requires an animation to have
completed in order to exist.

`[data-motion='off']` on any ancestor kills all of it, as does
`prefers-reduced-motion`.

## Charts

Hand-rolled inline SVG, no charting library — the app has exactly two chart types and
a library would cost more than it saves.

- `LineChart` — multi-series with optional CI bands, a horizontal reference line
  (`refLine`), a vertical operating-point marker (`markerX`, drawn as a dashed rule so
  it never occludes the curves), wide low-alpha window bands (`spans`), and the 45°
  reliability diagonal. The value readout is a fixed panel under the plot, not a
  cursor-following tooltip: on a chart whose whole job is comparison, the numbers
  belong in one predictable place.
- `IntervalChart` — point estimate plus 95% interval per lane on one shared domain,
  with optional shading of the clear air between two disjoint intervals.

Both take a `minWidth` and scroll inside their own container below it, so a 780px
chart never squeezes its axis labels to 5px and the page itself never scrolls
sideways.

## Data

`lib/artifacts.ts` is a static module because in the Python app every one of these
figures is a build output, written to SQLite at seed time — no model is ever fitted
inside a request. Point it at your own endpoint when you have one:

```ts
// app/page.tsx
const artifacts = await fetch('https://…/api/artifacts', { next: { revalidate: 3600 } }).then(r => r.json());
```

The one exception is `lib/policy.ts`, which does arithmetic on a precomputed grid at
render time — a handful of multiplications, exactly as the FastAPI route does.

## Responsive

The sidebar collapses to a horizontally scrolling nav below 1000px; type steps down
at 640px. Wide tables and charts scroll inside their containers, never the page.
```
