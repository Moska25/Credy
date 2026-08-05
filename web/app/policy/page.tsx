import PolicySimulator from '@/components/PolicySimulator';
import { PageHead } from '@/components/Page';
import { POLICY } from '@/lib/artifacts';

export const metadata = { title: 'Policy · Credy' };

export default function PolicyPage() {
  return (
    <div className="page" data-screen-label="Policy">
      <PageHead kicker="Economics" meta={`${POLICY.testLabel} · ${POLICY.testN.toLocaleString('en-US')} applications`} title="Turning a probability into money">
        Drag the threshold. Every figure below recomputes from a precomputed grid &mdash; deliberately simple arithmetic that
        can be checked by hand, on a single-period book with no funding cost, no recovery curve and no prepayment.
      </PageHead>
      <PolicySimulator />
    </div>
  );
}
