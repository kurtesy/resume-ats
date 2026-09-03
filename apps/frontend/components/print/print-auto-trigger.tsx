'use client';

import { useEffect } from 'react';

/**
 * Fires the browser's native print dialog on mount when ?autoprint=true.
 * Users pick "Save as PDF" in the dialog — this is the client-side
 * replacement for the old server-rendered (Playwright) PDF endpoint.
 */
export function PrintAutoTrigger({ enabled }: { enabled: boolean }) {
  useEffect(() => {
    if (!enabled) return;
    const timer = setTimeout(() => window.print(), 300);
    return () => clearTimeout(timer);
  }, [enabled]);

  return null;
}
