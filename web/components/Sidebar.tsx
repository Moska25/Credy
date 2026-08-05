'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { GROUPS, ROUTES } from '@/lib/nav';
import { META } from '@/lib/artifacts';
import { openPalette } from '@/components/paletteBus';

const RUN_META: [string, string][] = [
  ['build', META.build],
  ['rows', META.rows.toLocaleString('en-US')],
  ['seed', String(META.dataSeed)],
  ['built in', `${META.builtSeconds} s`],
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Credy</span>
        </div>
        <p className="brand-sub">Credit risk and model stability laboratory</p>
      </div>

      <button type="button" className="search-btn" onClick={openPalette}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.75" strokeLinecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-4.3-4.3" />
        </svg>
        <span>Search the lab</span>
        <kbd>&#8984;K</kbd>
      </button>

      <nav className="nav" aria-label="Primary">
        {GROUPS.map((group) => (
          <div key={group} style={{ display: 'contents' }}>
            <div className="nav-group">{group}</div>
            {ROUTES.filter((r) => r.group === group).map((route) => (
              <Link
                key={route.href}
                href={route.href}
                className="nav-item"
                aria-current={pathname === route.href ? 'page' : undefined}
              >
                {route.label}
                {route.figure ? (
                  <span className="nav-figure" data-hot={route.hot ? '1' : undefined}>{route.figure}</span>
                ) : null}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <dl className="runmeta">
        {RUN_META.map(([label, value]) => (
          <div key={label} style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}
