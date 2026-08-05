'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Counts up to the final value on mount. The rendered text starts AT the final
 * value and only animates if the timeline is live — so server output, print and
 * static captures all show the real number rather than a zero.
 */
export default function CountUp({ value, places = 0, signed = false, duration = 900 }: {
  value: number;
  places?: number;
  signed?: boolean;
  duration?: number;
}) {
  const format = (v: number) => `${signed && v >= 0 ? '+' : ''}${v.toFixed(places)}`;
  const [display, setDisplay] = useState(() => format(value));
  const frame = useRef<number>(0);

  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const start = performance.now();
    const step = (now: number) => {
      const k = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - k, 3);
      setDisplay(format(value * eased));
      if (k < 1) frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, places, signed, duration]);

  return <>{display}</>;
}
