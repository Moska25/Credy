'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FINDINGS, ROUTES } from '@/lib/nav';
import { onOpenPalette } from '@/components/paletteBus';

type Entry = { href: string; label: string; badge?: string; hint: string };

const POOL: Entry[] = [
  ...ROUTES.map((r) => ({ href: r.href, label: r.label, badge: r.figure, hint: r.hint })),
  ...FINDINGS,
];

export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return POOL.slice(0, 8);
    return POOL.filter((e) => `${e.label} ${e.hint} ${e.badge ?? ''}`.toLowerCase().includes(q));
  }, [query]);

  useEffect(() => onOpenPalette(() => { setOpen(true); setQuery(''); setSelected(0); }), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery('');
        setSelected(0);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  if (!open) return null;

  const go = (href: string) => { setOpen(false); router.push(href); };

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected((s) => (s + 1) % Math.max(1, results.length)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSelected((s) => (s - 1 + results.length) % Math.max(1, results.length)); }
    else if (e.key === 'Enter' && results[selected]) { e.preventDefault(); go(results[selected].href); }
  };

  return (
    <div className="palette-backdrop" data-anim="overlay" onClick={() => setOpen(false)} role="presentation">
      <div className="palette" data-anim="dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Search the lab" aria-modal="true">
        <div className="palette-input">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--terra)" strokeWidth="2.75" strokeLinecap="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            placeholder="Jump to a page, metric or finding"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(0); }}
            onKeyDown={onInputKey}
            aria-label="Search"
          />
          <kbd>esc</kbd>
        </div>

        <ul className="palette-results">
          {results.map((entry, i) => (
            <li key={`${entry.href}-${entry.label}`}>
              <a
                href={entry.href}
                className="palette-result"
                data-selected={i === selected ? '1' : undefined}
                onMouseEnter={() => setSelected(i)}
                onClick={(e) => { e.preventDefault(); go(entry.href); }}
              >
                <span className="label">{entry.label}</span>
                <span className="badge">{entry.badge}</span>
                <span className="hint">{entry.hint}</span>
              </a>
            </li>
          ))}
          {results.length === 0 ? <li className="palette-result"><span className="hint">Nothing matches that.</span></li> : null}
        </ul>

        <div className="palette-foot">
          <span>&#8593;&#8595; to move</span>
          <span>&#8629; to open</span>
          <span>&#8984;K anywhere</span>
        </div>
      </div>
    </div>
  );
}
