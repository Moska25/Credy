import Link from 'next/link';
import { META, type Alert } from '@/lib/artifacts';

/**
 * Thirty-nine alerts is a log, not a deck of cards. Each entry is a ruled row
 * hanging off one spine; at this count a box per entry would read as filing
 * rather than monitoring. Severity is written out as a word, so it never
 * depends on colour.
 */
export default function AlertRail({ alerts, limit, moreHref, moreCount }: {
  alerts: Alert[];
  limit?: number;
  moreHref?: string;
  moreCount?: number;
}) {
  const shown = limit ? alerts.slice(0, limit) : alerts;

  return (
    <>
      <ul className="rail">
        {shown.map((a, i) => (
          <li key={`${a.month}-${a.rule}-${i}`} className={a.severity === 'high' ? 'alert alert--high' : 'alert'}>
            <span className="alert-when">month {a.month}</span>
            <span style={{ minWidth: 0 }}>
              <span className="alert-head">
                <span className="alert-sev">{a.severity === 'high' ? 'high' : 'med'}</span>
                <b className="alert-title">{a.title}</b>
              </span>
              <span className="alert-trigger">{a.trigger}</span>
              <span className="alert-action"><b>action</b>{a.action}</span>
            </span>
          </li>
        ))}
      </ul>
      {moreHref && moreCount ? (
        <p className="small faint" style={{ margin: '12px 0 0 20px' }}>
          {moreCount} further alerts, listed in full on <Link href={moreHref}>the drift page</Link>. Months{' '}
          {META.splits.train.join('–')} are the training reference and are not monitored, because alerting on them would be
          circular.
        </p>
      ) : null}
    </>
  );
}
