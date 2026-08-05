import Link from 'next/link';
import IntervalChart from '@/components/charts/IntervalChart';
import CountUp from '@/components/CountUp';
import { Card, Metric, PageHead, Section } from '@/components/Page';
import { SUBGROUPS, SUBGROUP_DOMAIN, SUBGROUP_META, WIDEST_GAP } from '@/lib/artifacts';
import { pct } from '@/lib/format';

export const metadata = { title: 'Subgroups · Credy' };

export default function Subgroups() {
  const { scored, levels, minGroup } = SUBGROUP_META;
  return (
    <div className="page" data-screen-label="Subgroups">
      <PageHead kicker="Diagnostic, not audit" meta={`${scored} intervals, no multiple-comparison correction`} title="Subgroups">
        Four dimensions on one shared axis, because four separate tables looked comparable and were not. An overlap between two
        intervals should be visible at a glance &mdash; that is the whole point of the page.
      </PageHead>

      <section className="section">
        <div className="metrics">
          <Metric label="Widest spread" color="var(--terra-ink)" value={<CountUp value={WIDEST_GAP.gap} places={3} />}
            sub={`AUC, across ${WIDEST_GAP.dimension} · intervals ${WIDEST_GAP.overlapping ? 'overlap' : 'are disjoint'}`} />
          <Metric label="Levels scored" value={String(scored)}
            sub={`of ${levels} · ${levels - scored} below the ${minGroup}-application floor`} />
          <Metric label="Reporting floor" value={String(minGroup)}
            sub="applications, and at least 15 defaults, or no AUC is reported" />
        </div>
      </section>

      <Section title="AUC by level, all four dimensions" meta="dot is the point estimate, bar is the 95% interval">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(500px, 100%), 1fr))', gap: 14 }}>
          {SUBGROUPS.map((block) => (
            <Card key={block.dimension}>
              <div style={{ fontFamily: 'var(--font-mono), monospace', fontSize: 11.5, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--sage-ink)', marginBottom: 16 }}>
                {block.dimension}
              </div>
              <IntervalChart
                width={600}
                rowHeight={70}
                domain={SUBGROUP_DOMAIN}
                xLabel="AUC on the test months (0.5 = coin flip)"
                lanes={block.levels.map((l) => ({
                  label: l.level,
                  sub: `${l.n.toLocaleString('en-US')} applications, ${pct(l.badRate)} default rate`,
                  value: l.auc,
                  lo: l.lo,
                  hi: l.hi,
                }))}
              />
              <p className="small faint" style={{ margin: '10px 0 0' }}>{block.note}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Why this is not a fairness audit">
        <div className="cards">
          <Card>
            <div className="metric-label" style={{ color: 'var(--gold-ink)' }}>Equal AUC is not fairness</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              Discrimination measures ordering <em>within</em> a group. Two groups can share an AUC and still be approved at
              wildly different rates, or priced at wildly different levels. The broker channel here ranks best of any level and
              defaults most &mdash; both facts are true at once.
            </p>
          </Card>
          <Card>
            <div className="metric-label" style={{ color: 'var(--gold-ink)' }}>{scored} intervals, no correction</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              At this many comparisons, at least one interval is expected to look surprising by chance. Nothing here is
              corrected for that, so no single level should be read as a finding. It is a place to start looking.
            </p>
          </Card>
          <Card>
            <div className="metric-label" style={{ color: 'var(--clay-ink)' }}>Age is a model feature</div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)' }}>
              In several jurisdictions that alone would make this model unlawful for consumer credit. It is here to demonstrate
              what a <Link href="/model-card">model card</Link> has to disclose, not as a defensible design choice.
            </p>
          </Card>
        </div>
      </Section>
    </div>
  );
}
