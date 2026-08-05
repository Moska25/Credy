import type { ReactNode } from 'react';

/** Page head: kicker, hairline, right-hand meta, display title, lede. */
export function PageHead({ kicker, meta, title, children }: {
  kicker: string;
  meta?: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <>
      <div className="page-rule">
        <span className="kicker">{kicker}</span>
        <span className="fill" />
        {meta ? <span className="meta">{meta}</span> : null}
      </div>
      <h1 className="display">{title}</h1>
      {children ? <p className="lede">{children}</p> : null}
    </>
  );
}

export function Section({ title, meta, children }: { title: string; meta?: string; children: ReactNode }) {
  return (
    <section className="section">
      <div className="section-head">
        <h2 className="h2">{title}</h2>
        <span className="fill" />
        {meta ? <span className="meta">{meta}</span> : null}
      </div>
      {children}
    </section>
  );
}

export function Note({ tone = 'terra', title, children, bare = false }: {
  tone?: 'terra' | 'sage' | 'gold' | 'clay';
  title?: string;
  children: ReactNode;
  bare?: boolean;
}) {
  const cls = ['note', tone !== 'terra' ? `note--${tone}` : '', bare ? 'note--bare' : ''].filter(Boolean).join(' ');
  return (
    <p className={cls}>
      {title ? <b>{title}</b> : null} {children}
    </p>
  );
}

export function Metric({ label, value, sub, color, small }: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  color?: string;
  small?: boolean;
}) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className={small ? 'metric-value metric-value--sm' : 'metric-value'} style={color ? { color } : undefined}>{value}</div>
      {sub ? <div className="metric-sub">{sub}</div> : null}
    </div>
  );
}

export function Card({ children, variant, flush }: { children: ReactNode; variant?: 'accent' | 'alarm'; flush?: boolean }) {
  const cls = ['card', variant ? `card--${variant}` : '', flush ? 'card--flush' : ''].filter(Boolean).join(' ');
  return <div className={cls}>{children}</div>;
}

export function TableCard({ children, minWidth = 680 }: { children: ReactNode; minWidth?: number }) {
  return (
    <div className="card card--flush">
      <div className="table-scroll">
        <table className="data" style={{ minWidth }}>{children}</table>
      </div>
    </div>
  );
}
