import { Card, Note, PageHead, Section, TableCard } from '@/components/Page';
import { COHORTS, DATA_DICTIONARY, DRIFT_SCHEDULE, META, SAMPLE_ROWS } from '@/lib/artifacts';
import { pct } from '@/lib/format';

export const metadata = { title: 'Data & DGP · Credy' };

const SAMPLE_HEADERS = ['id', 'month', 'age', 'income', 'employment', 'tenure', 'debt ratio', 'history', 'delinq', 'loan', 'term', 'region', 'channel', 'true pd', 'default'];

const cell = (v: string | number | null, i: number) => {
  if (v == null) return '—';
  if (i === 13) return (v as number).toFixed(3);
  if (typeof v === 'number' && (i === 5 || i === 6)) return v.toFixed(2);
  if (typeof v === 'number' && (i === 3 || i === 9)) return v.toLocaleString('en-US');
  return String(v);
};

/** Bars share one scale, rounded up to the next whole percent above the worst
 *  cohort, so the longest bar never touches the edge and none of them lie. */
const BAR_MAX = Math.ceil(Math.max(...COHORTS.map((c) => c.badRate)) * 100 + 1) / 100;

export default function DataPage() {
  return (
    <div className="page" data-screen-label="Data">
      <PageHead kicker="Provenance" meta={`${META.rows.toLocaleString('en-US')} rows · ${META.months} cohorts · seed ${META.dataSeed}`} title="Data and the generating process">
        The subject here is drift detection, and you cannot claim a detector works unless you know what it was supposed to
        detect. Because this repository writes the data-generating process itself, the drift schedule is known &mdash; which is
        the one thing a public lending dataset cannot give you.
      </PageHead>

      <Section title="The process, in one line">
        <Card>
          <pre className="ledger" style={{ color: 'var(--terra-ink)' }}>{`logit P(default) = b0(month)
                 + sum_j beta_j * feature_j
                 + beta_missing * 1[field absent]`}</pre>
          <p style={{ margin: '14px 0 0', fontSize: 13, color: 'var(--muted)', maxWidth: '88ch' }}>
            Latent age, income, debt and history factors are drawn from a correlated Gaussian, then transformed into the
            observable schema. Every constant was chosen by measuring, not by guessing: the first version produced a 16%
            first-month default rate and a random-split overstatement of only +0.01 AUC, which meant the headline comparison had
            no signal at all.
          </p>
        </Card>
      </Section>

      <Section title="The drift schedule" meta="four switches, independently toggleable">
        <TableCard minWidth={720}>
          <thead>
            <tr><th>Switch</th><th className="n">Months</th><th>What it does</th><th>Changes</th></tr>
          </thead>
          <tbody>
            {DRIFT_SCHEDULE.map(([name, when, what, affects]) => (
              <tr key={name}>
                <td className="mono" style={{ color: 'var(--terra-ink)', whiteSpace: 'nowrap' }}>{name}</td>
                <td className="n">{when}</td>
                <td style={{ maxWidth: '52ch' }}>{what}</td>
                <td className="mono">{affects}</td>
              </tr>
            ))}
          </tbody>
        </TableCard>
        <Note tone="sage" title="The business story behind all four.">
          An issuer chasing volume in year two. Applicants get poorer, the book gets riskier, the broker panel is opened up so
          broker volume grows while broker quality collapses, and an upstream HR feed starts dropping employment tenure. Three
          of the four are linear ramps, which is exactly the shape a fixed threshold is worst at catching.
        </Note>
      </Section>

      <Section title="Data dictionary">
        <TableCard minWidth={800}>
          <thead>
            <tr><th>Column</th><th>Type / range</th><th>How it is generated</th><th>Missing</th></tr>
          </thead>
          <tbody>
            {DATA_DICTIONARY.map(([name, type, how, missing]) => (
              <tr key={name}>
                <td className="mono" style={{ color: 'var(--ink)', whiteSpace: 'nowrap' }}>{name}</td>
                <td className="mono" style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>{type}</td>
                <td className="muted">{how}</td>
                <td className="mono faint" style={{ fontSize: 11.5 }}>{missing}</td>
              </tr>
            ))}
          </tbody>
        </TableCard>
      </Section>

      <Section title="Cohorts" meta={`bar is the default rate on a 0–${pct(BAR_MAX, 0)} scale`}>
        <TableCard minWidth={600}>
          <thead>
            <tr>
              <th className="n">Month</th><th className="n">Applications</th><th className="n">Default rate</th>
              <th style={{ width: '40%' }} />
              <th className="n">Income present</th>
            </tr>
          </thead>
          <tbody>
            {COHORTS.map((c) => (
              <tr key={c.month}>
                <td className="n">{c.month}</td>
                <td className="n">{c.n.toLocaleString('en-US')}</td>
                <td className="n">{pct(c.badRate)}</td>
                <td>
                  <span style={{ display: 'block', height: 7, borderRadius: 999, background: 'color-mix(in srgb, var(--ink) 7%, transparent)' }}>
                    <span
                      data-anim="grow"
                      style={{
                        display: 'block',
                        height: 7,
                        borderRadius: 999,
                        transformOrigin: 'left',
                        width: `${(c.badRate / BAR_MAX) * 100}%`,
                        background: 'linear-gradient(90deg, var(--sage), var(--clay))',
                      }}
                    />
                  </span>
                </td>
                <td className="n muted">{pct(c.incomePresent)}</td>
              </tr>
            ))}
          </tbody>
        </TableCard>
      </Section>

      <Section title="Sample rows" meta="every 3,571st applicant · — is a genuine missing value">
        <TableCard minWidth={1000}>
          <thead>
            <tr>{SAMPLE_HEADERS.map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {SAMPLE_ROWS.map((row) => (
              <tr key={String(row[0])}>
                {row.map((v, i) => (
                  <td key={i} className="n" style={{ textAlign: 'left', color: v == null ? 'var(--faint)' : undefined }}>
                    {cell(v, i)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </TableCard>
      </Section>

      <Section title="Running it against real lending data">
        <div className="cards">
          <Card>
            <div className="metric-label" style={{ color: 'var(--sage-ink)' }}>A source-agnostic adapter layer</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              Every adapter returns the same applicant schema, so the modelling, drift and policy code never learns which
              dataset it is looking at. Neither public dataset is vendored here and neither ever will be &mdash; they belong to
              their publishers.
            </p>
          </Card>
          <Card>
            <div className="metric-label" style={{ color: 'var(--clay-ink)' }}>An unresolved loan must never be labelled good</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              A loan issued three months ago and still current has not defaulted <em>yet</em>. Labelling it 0 biases the base
              rate down, and biases it more for recent cohorts than old ones &mdash; manufacturing exactly the fake temporal
              trend this repository exists to detect.
            </p>
          </Card>
          <Card>
            <div className="metric-label" style={{ color: 'var(--gold-ink)' }}>No real source has a known drift schedule</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              So the verification table refuses rather than rendering empty. An empty verification table reads as &ldquo;no drift
              was injected&rdquo;, which on real data is an unfalsifiable claim rather than a result.
            </p>
          </Card>
        </div>
      </Section>
    </div>
  );
}
