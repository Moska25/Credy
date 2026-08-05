import Link from 'next/link';
import { Card, Note, PageHead, Section, TableCard } from '@/components/Page';
import { ALERTS, CALIBRATION, COEFFICIENTS, META, WIDEST_GAP } from '@/lib/artifacts';
import { sgn } from '@/lib/format';

export const metadata = { title: 'Model card · Credy' };

const LIMITATIONS: { when: string; weight: 'bad' | 'warn' | 'ok'; what: string }[] = [
  { when: 'data', weight: 'bad', what: 'Synthetic. Every relationship in it was written by hand, so the model is being tested on a world it can in principle fit perfectly. Real applicant data contains structure no generator thought of.' },
  { when: 'labels', weight: 'bad', what: 'Default is observed for every application, including declined ones. Real portfolios only observe outcomes for approved applicants, which biases every refit. No reject inference is implemented.' },
  { when: 'horizon', weight: 'warn', what: 'Default is a single binary flag with no time-to-event, so no survival view and no lifetime PD is possible.' },
  { when: 'economics', weight: 'warn', what: 'One period, no funding cost, no operational cost, no recovery curve, no prepayment. Loss given default is a constant rather than a distribution.' },
  { when: 'selection', weight: 'warn', what: "The champion was chosen on the validation window and this card then reports test numbers for all three. Reporting a selected model's test performance without accounting for the selection is mildly optimistic." },
  { when: 'intervals', weight: 'warn', what: "Bootstrap intervals assume applications are independent draws. They quantify sampling noise only — not model risk, not specification error, and explicitly not the risk that next month's population differs from this month's, which is the risk this whole project is about." },
  { when: 'explanations', weight: 'ok', what: 'No per-application reason codes. A production credit model needs adverse action reasons; this one cannot produce them.' },
];

const span = (k: 'train' | 'validation' | 'test') => META.splits[k].join('–');

const BASICS: [string, React.ReactNode][] = [
  ['model', <>{META.champion} (<code>HistGradientBoostingClassifier</code>), champion of three candidates</>],
  ['candidates', 'Points scorecard (baseline), logistic regression, gradient boosting'],
  ['task', 'Binary classification: probability that an application defaults'],
  ['training', `${META.splitSizes.train.toLocaleString('en-US')} applications, months ${span('train')}`],
  ['validation', `${META.splitSizes.validation.toLocaleString('en-US')} applications, months ${span('validation')} (recalibration fitted here)`],
  ['test', `${META.splitSizes.test.toLocaleString('en-US')} applications, months ${span('test')}, never used for any fitting or selection`],
  ['split', 'Strictly temporal. No row from a later month appears in an earlier window.'],
  ['features', '11 applicant attributes plus 3 explicit missing indicators and 2 derived ratios'],
  ['determinism', 'Every random seed fixed; rebuilding reproduces these numbers exactly'],
  ['build time', `${META.builtSeconds} s for generation, fitting, evaluation and monitoring`],
];

export default function ModelCard() {
  const platt = CALIBRATION.find((v) => v.key === 'platt')!;
  return (
    <div className="page" data-screen-label="Model card">
      <PageHead kicker="Disclosure" meta="not a regulatory artefact · reviewed by nobody" title="Model card">
        What this model is, what it was fitted on, how well it works with intervals attached, and the specific circumstances
        under which it should not be used &mdash; which is the part of a model card that is usually missing.
      </PageHead>

      <Note bare title="This card describes a model fitted to synthetic data.">
        It is written in the form a real model card would take so that the form is demonstrated. Every number comes from a
        generated population.
      </Note>

      <Section title="Basics">
        <Card>
          <dl className="kv">
            {BASICS.map(([k, v]) => (
              <div key={k} style={{ display: 'contents' }}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </Section>

      <Section title="Intended use">
        <div className="cards">
          <Card>
            <div className="metric-label" style={{ color: 'var(--sage-ink)' }}>What it is for</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              Demonstrating a credit risk evaluation and monitoring workflow end to end: temporal validation, interval
              estimation, calibration, drift detection and threshold economics. A teaching and engineering artefact.
            </p>
          </Card>
          <Card>
            <div className="metric-label" style={{ color: 'var(--clay-ink)' }}>What it is not for</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              Any real credit decision about any real person. The model has never seen a real applicant, its features are
              invented and its economics are illustrative. It must not be used to score, rank, price or decline anyone.
            </p>
          </Card>
          <Card>
            <div className="metric-label" style={{ color: 'var(--gold-ink)' }}>Out-of-scope populations</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              Everything outside the generated distribution: other products, geographies, periods, commercial lending &mdash;
              and, given the drift results on this very site, populations only a few months away.
            </p>
          </Card>
        </div>
      </Section>

      <Section title="Estimated versus true coefficients" meta={`logistic regression on months ${span('train')}`}>
        <TableCard minWidth={640}>
          <thead>
            <tr>
              <th>Feature</th><th className="n">Estimated</th><th className="n">True (DGP)</th><th className="n">Difference</th><th>Sign</th>
            </tr>
          </thead>
          <tbody>
            {COEFFICIENTS.map(([feature, estimated, truth]) => {
              const match = truth == null ? null : Math.sign(estimated) === Math.sign(truth);
              return (
                <tr key={feature}>
                  <td className="mono" style={{ color: 'var(--ink)' }}>{feature}</td>
                  <td className="n">{sgn(estimated)}</td>
                  <td className="n muted">{truth == null ? 'not in DGP' : sgn(truth)}</td>
                  <td className="n">{truth == null ? 'n/a' : sgn(estimated - truth)}</td>
                  <td>
                    <span className={match == null ? 'pill pill--idle' : match ? 'pill pill--sage' : 'pill pill--clay'}>
                      {match == null ? 'n/a' : match ? 'match' : 'wrong sign'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </TableCard>
        <Note tone="gold" title="Why some estimates are attenuated.">
          <code>z_income</code>, <code>log_loan_amount</code> and <code>loan_to_income</code> are algebraically related &mdash;
          loan-to-income <em>is</em> loan divided by income &mdash; so the true income effect is split across three collinear
          columns and none recovers it alone. This is a real property of the fit, and it is why coefficient magnitudes from a
          correlated design should never be read as feature importances.
        </Note>
      </Section>

      <Section title="Known failures on this very dataset">
        <TableCard minWidth={600}>
          <thead>
            <tr><th className="n">Month</th><th>Rule</th><th>Finding</th></tr>
          </thead>
          <tbody>
            {ALERTS.filter((a) => a.severity === 'high').map((a, i) => (
              <tr key={`${a.month}-${i}`}>
                <td className="n">{a.month}</td>
                <td className="mono" style={{ color: 'var(--clay-ink)' }}>{a.rule}</td>
                <td>{a.title}</td>
              </tr>
            ))}
          </tbody>
        </TableCard>
        <p className="small faint" style={{ margin: '12px 0 0', maxWidth: '88ch' }}>
          Calibration on the test window after Platt scaling fitted on validation: slope {platt.slope.toFixed(3)}, intercept{' '}
          {sgn(platt.intercept)}, Brier {platt.brier.toFixed(5)}. Details on <Link href="/calibration">the calibration page</Link>.
        </p>
      </Section>

      <Section title="Limitations, ranked by how much they undermine the result">
        <ul className="limits">
          {LIMITATIONS.map((l) => (
            <li key={l.when} data-weight={l.weight}>
              <span className="when">{l.when}</span>
              <span className="what">{l.what}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Ethical notes">
        <div className="cards">
          <Card>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              <b style={{ color: 'var(--ink)' }}>Automated credit decisions harm people when they are wrong.</b> A false decline
              is not a rounding error to the person declined; it is a refused loan. The false-decline cost in the{' '}
              <Link href="/policy">policy simulator</Link> is a crude stand-in, and treating it purely as lost margin
              understates it.
            </p>
          </Card>
          <Card>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              <b style={{ color: 'var(--ink)' }}>Subgroup results are a diagnostic, not a fairness audit.</b> Widest observed
              spread on this dataset: {WIDEST_GAP.dimension}, {WIDEST_GAP.worst.toFixed(3)} to {WIDEST_GAP.best.toFixed(3)} AUC,
              with overlapping intervals. See <Link href="/subgroups">subgroups</Link> for what that distinction means.
            </p>
          </Card>
          <Card>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              <b style={{ color: 'var(--ink)' }}>Features that proxy for protected characteristics are not screened.</b> Age is
              used directly. In several jurisdictions that alone would make the model unlawful for consumer credit. Read its
              presence as a demonstration of what a model card must disclose.
            </p>
          </Card>
          <Card>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              <b style={{ color: 'var(--ink)' }}>Drift is a safety issue, not just an accuracy issue.</b> The alerts here fire
              months after the drift begins. A model that is quietly under-predicting risk is also quietly approving people who
              cannot afford the loan.
            </p>
          </Card>
        </div>
      </Section>
    </div>
  );
}
