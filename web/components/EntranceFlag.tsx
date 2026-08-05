'use client';

import { useEffect } from 'react';

/**
 * Sets <html data-entered="1"> — the flag every entrance animation in
 * globals.css is scoped to — but only after confirming the document timeline
 * is actually advancing.
 *
 * This matters more than it looks. If animations are applied unconditionally
 * with animation-fill-mode: both, then any renderer that does not advance the
 * timeline (a print pass, an offscreen capture, a screenshot pipeline) pins
 * every animated element to its 0% keyframe and the page comes out blank.
 * Failing open costs one attribute.
 */
export default function EntranceFlag() {
  useEffect(() => {
    const before = document.timeline?.currentTime ?? 0;
    const id = window.setTimeout(() => {
      const after = document.timeline?.currentTime ?? 0;
      if (Number(after) > Number(before)) document.documentElement.setAttribute('data-entered', '1');
    }, 200);
    return () => window.clearTimeout(id);
  }, []);

  return null;
}
