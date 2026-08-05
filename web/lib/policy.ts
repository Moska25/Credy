/**
 * Threshold economics.
 *
 * Exactly what the FastAPI route does: the grid is threshold-independent and
 * was computed once at seed time (one sort over the cohort), so applying a set
 * of economics is a handful of multiplications per row.
 *
 *     approve if PD < threshold
 *     revenue     = margin  × principal of approved loans that did not default
 *     credit loss = lgd     × principal of approved loans that did default
 *     opportunity = fdCost  × good applicants declined
 *     profit      = revenue − credit loss − opportunity
 *
 * `margin`, `lgd` and `fdCost` are inputs, not findings.
 */

import { POLICY, type PolicyGridRow } from './artifacts';

export type Economics = { lgd: number; margin: number; falseDeclineCost: number };

export const DEFAULT_ECONOMICS: Economics = {
  lgd: POLICY.defaults.lgd,
  margin: POLICY.defaults.margin,
  falseDeclineCost: POLICY.defaults.fr_cost,
};

export type Cohort = 'test' | 'reference';
const GRID: Record<Cohort, PolicyGridRow[]> = {
  test: POLICY.testGrid,
  reference: POLICY.referenceGrid,
};

export type PolicyRow = {
  threshold: number;
  approvalRate: number;
  approved: number;
  defaults: number;
  approvedBadRate: number;
  goodPrincipal: number;
  badPrincipal: number;
  principal: number;
  revenue: number;
  creditLoss: number;
  opportunityCost: number;
  goodDeclined: number;
  profit: number;
};

export const applyEconomics = (r: PolicyGridRow, econ: Economics): PolicyRow => {
  const revenue = econ.margin * r.principal_good;
  const creditLoss = econ.lgd * r.principal_bad;
  const opportunityCost = econ.falseDeclineCost * r.n_rejected_good;
  return {
    threshold: r.threshold,
    approvalRate: r.approval_rate,
    approved: r.n_approved,
    defaults: r.n_approved_bad,
    approvedBadRate: r.approved_bad_rate,
    goodPrincipal: r.principal_good,
    badPrincipal: r.principal_bad,
    principal: r.principal_good + r.principal_bad,
    revenue,
    creditLoss,
    opportunityCost,
    goodDeclined: r.n_rejected_good,
    profit: revenue - creditLoss - opportunityCost,
  };
};

/** The thresholds the seeder swept: 0.005 … 0.600 in 0.005 steps. */
export const THRESHOLD_GRID: number[] = POLICY.testGrid.map((r) => r.threshold);

export const curve = (cohort: Cohort, econ: Economics) =>
  GRID[cohort].map((r) => applyEconomics(r, econ));

export const argmaxProfit = (rows: PolicyRow[]) =>
  rows.reduce((a, b) => (b.profit > a.profit ? b : a));

const nearestBy = <T,>(items: T[], distance: (item: T) => number) => {
  let best = 0;
  let bestDistance = Infinity;
  items.forEach((item, i) => {
    const d = distance(item);
    if (d < bestDistance) { bestDistance = d; best = i; }
  });
  return best;
};

export const nearestIndex = (threshold: number) =>
  nearestBy(THRESHOLD_GRID, (t) => Math.abs(t - threshold));

/** Presets are written as a target approval rate on the reference cohort, which
 *  is how a credit policy is actually stated; the seeder turned each one into a
 *  PD cut-off by taking that quantile of the reference score distribution. */
export const PRESETS = Object.entries(POLICY.presetRates).map(([name, targetRate]) => ({
  name,
  targetRate,
  threshold: POLICY.presets[name],
}));

export const indexForPreset = (name: string) => nearestIndex(POLICY.presets[name]);

export const DEFAULT_INDEX = indexForPreset('balanced');

/** What a stale cut-off costs: the deployment-optimal threshold, held
 *  unchanged, measured against re-optimising on the current cohort. */
export function staleThresholdCost(econ: Economics) {
  const test = curve('test', econ);
  const reference = curve('reference', econ);
  const bestNow = argmaxProfit(test);
  const bestAtDeployment = argmaxProfit(reference);
  const held = test[nearestIndex(bestAtDeployment.threshold)];
  const gap = bestNow.profit - held.profit;
  return { test, reference, bestNow, bestAtDeployment, held, gap, gapShare: gap / bestNow.profit };
}
