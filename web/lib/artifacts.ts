/**
 * Precomputed artifacts.
 *
 * Every figure below is a build output of the Python side: `app/seed.py` writes
 * them to SQLite, `scripts/export_artifacts.py` dumps them to `artifacts.json`,
 * and this module is a typed view over that file. Nothing here is authored by
 * hand, which is the point — the UI is not allowed to invent a number.
 *
 * To refresh:  ./.venv/bin/python -m app.seed && ./.venv/bin/python -m scripts.export_artifacts
 *
 * Swapping the import for `await fetch('/api/artifacts')` changes nothing else.
 */

import raw from './artifacts.json';

type Json = typeof raw;

export const META = raw.meta as {
  build: string; rows: number; months: number; dataSeed: number; champion: string;
  nBoot: number; nBootMonthly: number; builtSeconds: number;
  splits: Record<'train' | 'validation' | 'test', [number, number]>;
  splitSizes: Record<'train' | 'validation' | 'test', number>;
  perMonth: number;
};

export const MONTHS: number[] = raw.months;

/** Champion AUC per cohort month, with its own bootstrap interval per month. */
export const AUC: number[] = raw.auc;
export const AUC_LO: number[] = raw.aucLo;
export const AUC_HI: number[] = raw.aucHi;

/** Observed default rate against the model's mean predicted PD. These two
 *  lines coming apart is the whole calibration argument. */
export const BAD_RATE: number[] = raw.badRate;
export const MEAN_PREDICTED: number[] = raw.meanPredicted;

/** Score PSI and Jensen-Shannon divergence. Never leaves the stable band. */
export const SCORE_PSI: number[] = raw.scorePsi;
export const SCORE_JS: number[] = raw.scoreJs;
export const SCORE_PSI_MAX: number = raw.scorePsiMax;

export const THRESHOLDS = raw.thresholds as {
  scorePsiAlert: number; psiWatch: number; psiShift: number; aucFloor: number;
  aucBaseline: number; slopeBand: number[]; pdGap: number; missingnessJump: number;
};

/** PSI per feature per month, against the pooled training reference. */
export const FEATURE_PSI: Record<string, number[]> = raw.featurePsi;
export const WORST_FEATURE = raw.worstFeature as { name: string; psi: number };

/** Missing-data rates, each against its own pooled training reference. */
export const MISSINGNESS: Record<string, { ref: number; rates: number[] }> = raw.missingness;

export type Alert = {
  month: number;
  severity: 'high' | 'medium';
  rule: string;
  title: string;
  trigger: string;
  action: string;
};

/** Severity is written out as a word so it never depends on colour alone. */
export const ALERTS = raw.alerts as Alert[];
export const ALERT_TOTALS = raw.alertTotals as { total: number; high: number; firstMonth: number };

/** Alerts per rule on the drifted cohort against the stationary control.
 *  A rule that fires on everything is not a detector. */
export const BY_RULE = raw.byRule as {
  rule: string; drifted: number; control: number; verdict: string;
  kind: 'ok' | 'bad' | 'idle';
}[];

export const CONTROL = raw.control as {
  rows: number; alerts: number; badRateYear1: number; badRateYear2: number;
};

/** Detectors scored against the drift that was planted. No real dataset can
 *  produce this table, which is the argument for a written-down DGP. */
export const VERIFICATION = raw.verification as {
  injected: string; starts: number; detector: string; first: number;
  lag: number; alerts: number; detected: boolean;
}[];

/** Temporal split against random split, same model, same row counts. */
export const COMPARISON = raw.comparison as {
  label: string; temporal: number[]; random: number[];
  overstatement: number; disjoint: boolean; champion: boolean;
}[];

export const HERO = raw.hero as {
  overstatement: number;
  domain: [number, number];
  clearAir: [number, number] | null;
  temporal: { auc: number; lo: number; hi: number };
  random: { auc: number; lo: number; hi: number };
};

export const DECAY = raw.decay as {
  delta: number; lo: number; hi: number; excludesZero: boolean;
  validation: { auc: number; lo: number; hi: number };
  test: { auc: number; lo: number; hi: number };
};

export type ModelWindow = {
  window: string; n: number; badRate: number;
  auc: number; lo: number; hi: number;
  gini: number; ks: number; logLoss: number; brier: number; slope: number;
};

export const PER_MODEL = raw.perModel as { label: string; windows: ModelWindow[] }[];

/** Operating points on the test window. Precision is the share of declined
 *  applications that really would have defaulted. */
export const OPERATING_POINTS = raw.operatingPoints as {
  rejectRate: number; threshold: number; nRejected: number;
  precision: number; recall: number; approvedBadRate: number;
}[];

/** Calibration variants. AUC is unchanged by Platt and all but unchanged by
 *  isotonic: a monotone map cannot reorder a single pair. */
export const CALIBRATION = raw.calibration.variants as {
  key: string; label: string; slope: number; intercept: number;
  brier: number; logLoss: number; ece: number; heat: number;
}[];
export const CALIBRATION_META = {
  fittedOn: raw.calibration.fittedOn,
  aucUnchanged: raw.calibration.aucUnchanged as Record<string, number>,
};

/** Reliability curves, 10 equal-count bins on the test months. */
export const RELIABILITY: Record<string, number[][]> = raw.calibration.reliability;
export const RELIABILITY_DOMAIN = raw.calibration.reliabilityDomain as number[];

/** AUC by subgroup level, one shared domain across all four dimensions. */
export const SUBGROUPS = raw.subgroups.blocks as {
  dimension: string; note: string;
  levels: { level: string; n: number; badRate: number; auc: number; lo: number; hi: number }[];
}[];
export const SUBGROUP_DOMAIN = raw.subgroups.domain as [number, number];
export const SUBGROUP_META = {
  minGroup: raw.subgroups.minGroup,
  levels: raw.subgroups.levels,
  scored: raw.subgroups.scored,
};
export const WIDEST_GAP = raw.subgroups.widestGap as {
  dimension: string; gap: number; best: number; worst: number;
  bestLevel: string; worstLevel: string; overlapping: boolean;
};

/** Estimated coefficients against the DGP's true values. The three income
 *  columns are algebraically related, so none of them recovers the effect
 *  alone — which is why magnitudes here are not feature importances. */
export const COEFFICIENTS = raw.coefficients as [string, number, number | null][];

export const DATA_DICTIONARY = raw.dataDictionary as [string, string, string, string][];

/** Four independently switchable drifts, on a documented schedule. */
export const DRIFT_SCHEDULE = raw.driftSchedule as [string, string, string, string][];

export const SAMPLE_ROWS = raw.sampleRows as (string | number | null)[][];

export const COHORTS = raw.cohorts as {
  month: number; n: number; badRate: number; incomePresent: number;
}[];

export const POLICY = raw.policy as {
  referenceGrid: PolicyGridRow[];
  testGrid: PolicyGridRow[];
  presets: Record<string, number>;
  presetRates: Record<string, number>;
  defaults: { lgd: number; margin: number; fr_cost: number };
  referenceLabel: string;
  testLabel: string;
  referenceN: number;
  testN: number;
  stale: { profitGap: number; profitGapPct: number; profitGapLabel: string };
};

export type PolicyGridRow = {
  threshold: number;
  n_approved: number;
  approval_rate: number;
  n_approved_bad: number;
  approved_bad_rate: number;
  principal_good: number;
  principal_bad: number;
  n_rejected_good: number;
};

/** Preformatted headline figures, so the nav and the tour can never fall out
 *  of step with the page they point at. */
export const FIGURES = raw.figures as Record<string, string>;

/** The closing panel on the overview: every page in one number. */
export const TOUR = [
  { href: '/performance', label: 'Performance', figure: FIGURES.decay,
    what: 'AUC lost from the validation window to the test window, with the interval on the difference and the month-by-month decay behind it.' },
  { href: '/calibration', label: 'Calibration', figure: FIGURES.calibrationSlope,
    what: 'Calibration slope on the raw score against a perfect 1.000, before and after Platt and isotonic. Ranking and pricing fail differently.' },
  { href: '/drift', label: 'Drift', figure: FIGURES.worstPsi,
    what: `Peak PSI on ${WORST_FEATURE.name}, the feature that moved most, against a score PSI that never left the stable band.` },
  { href: '/subgroups', label: 'Subgroups', figure: FIGURES.widestGap,
    what: `Widest AUC spread across any dimension (${WIDEST_GAP.dimension}), reported with cohort sizes and intervals rather than as a ranking.` },
  { href: '/policy', label: 'Policy', figure: FIGURES.staleCost,
    what: 'Profit given up by holding the cut-off that was optimal at deployment, six months after deployment.' },
  { href: '/model-card', label: 'Model card', figure: FIGURES.alerts,
    what: 'Open alerts, the limitations that produced them, and the ethical notes, in the form a real model card takes.' },
];

export type { Json };
