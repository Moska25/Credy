import { BY_RULE, FIGURES } from './artifacts';

export type Route = {
  href: string;
  label: string;
  group: string;
  figure?: string;
  hot?: boolean;
  hint: string;
};

/** The eight routes, grouped the way a reader actually moves through them:
 *  the model, then how it is watched, then what it costs, then its paperwork.
 *  Every figure is read off the artifacts, never typed in. */
export const ROUTES: Route[] = [
  { href: '/', label: 'Overview', group: 'The model', figure: FIGURES.alerts, hot: true,
    hint: 'The headline comparison, the alert stack, the verification table' },
  { href: '/performance', label: 'Performance', group: 'The model', figure: FIGURES.testAuc,
    hint: 'Temporal vs random split, month-by-month decay, operating points' },
  { href: '/calibration', label: 'Calibration', group: 'The model', figure: FIGURES.calibrationSlope,
    hint: 'Reliability curves, Platt and isotonic recalibration' },
  { href: '/drift', label: 'Drift', group: 'Monitoring', figure: FIGURES.worstPsi, hot: true,
    hint: 'PSI and JS per feature per month, alert rules, false-alarm control' },
  { href: '/subgroups', label: 'Subgroups', group: 'Monitoring', figure: FIGURES.widestGap,
    hint: 'AUC by level on one shared axis, four dimensions as small multiples' },
  { href: '/policy', label: 'Policy simulator', group: 'Economics', figure: `−${FIGURES.staleCost}`,
    hint: 'Approval threshold economics and what a stale cut-off costs' },
  { href: '/model-card', label: 'Model card', group: 'Provenance',
    hint: 'Intended use, coefficients, known failures, ethical notes' },
  { href: '/data', label: 'Data & DGP', group: 'Provenance',
    hint: 'Data dictionary, the drift schedule, cohort counts, sample rows' },
];

export const GROUPS = ['The model', 'Monitoring', 'Economics', 'Provenance'];

const scorePsi = BY_RULE.find((r) => r.rule === 'score_psi');

/** Findings, so the palette searches conclusions and not just page names. */
export const FINDINGS = [
  { href: '/drift', label: 'Score PSI never fired', badge: `${scorePsi?.drifted ?? 0} alerts`,
    hint: 'The monitor most credit teams run is blind to concept drift by construction' },
  { href: '/policy', label: 'What a stale cut-off costs', badge: FIGURES.staleCostPct,
    hint: 'The profit-maximising threshold moves; holding the old one costs real money' },
  { href: '/drift', label: 'False-alarm control run', badge: FIGURES.controlAlerts,
    hint: 'Identical rules over a stationary population with every drift switch off' },
  { href: '/model-card', label: 'Age is used as a feature', badge: 'ethics',
    hint: 'In several jurisdictions that alone would make the model unlawful' },
  { href: '/performance', label: 'AUC decay, val to test', badge: FIGURES.decay,
    hint: 'Interval on the difference excludes zero' },
];
