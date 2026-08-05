import type { Metadata } from 'next';
import { Caprasimo, Figtree, Cormorant_Garamond, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import Sidebar from '@/components/Sidebar';
import CommandPalette from '@/components/CommandPalette';
import EntranceFlag from '@/components/EntranceFlag';

const display = Caprasimo({ weight: '400', subsets: ['latin'], variable: '--font-display' });
const body = Figtree({ subsets: ['latin'], variable: '--font-body' });
const serif = Cormorant_Garamond({ weight: ['400', '500', '600'], style: ['normal', 'italic'], subsets: ['latin'], variable: '--font-serif' });
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono' });

export const metadata: Metadata = {
  title: 'Credy · Credit risk and model stability laboratory',
  description:
    'A credit risk model-stability lab over 40,000 synthetic applicants across 24 monthly cohorts, with four drifts injected on purpose so the detectors can be scored rather than asserted.',
};

/**
 * data-palette picks one of the three token sets in globals.css.
 * Set it here (or from a cookie / user preference) — nothing below needs to know.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-palette="vellum" className={`${display.variable} ${body.variable} ${serif.variable} ${mono.variable}`}>
      <body>
        <EntranceFlag />
        <div className="shell">
          <Sidebar />
          <main className="main">{children}</main>
        </div>
        <CommandPalette />
      </body>
    </html>
  );
}
