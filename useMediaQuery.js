/**
 * useMediaQuery — subscribe to a CSS media query and get a boolean back.
 *
 * The implementation is the standard SSR-safe pattern: read once synchronously
 * on first render via the initializer, then subscribe via addEventListener.
 * No layout effect needed — the first render uses the correct value.
 *
 * Notes:
 *   - Returns false on the server (no window). For Vite SPA this never
 *     happens, but the guard is cheap and means the hook is portable.
 *   - `change` event has been the standard since 2018; the older addListener
 *     fallback is intentionally omitted.
 *
 * Usage:
 *   const isMobile = useMediaQuery('(max-width: 768px)');
 */
import { useEffect, useState } from 'react';

export function useMediaQuery(query) {
  const get = () => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia(query).matches;
  };
  const [matches, setMatches] = useState(get);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    // Some browsers fire change synchronously on subscribe; capture initial.
    setMatches(mql.matches);
    const onChange = (e) => setMatches(e.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

/**
 * Convenience wrapper. The 768px breakpoint matches the common tablet-portrait
 * boundary. Anything narrower gets mobile-stacked layouts. Anything wider
 * keeps the desktop multi-column treatments.
 *
 * Why one breakpoint and not three? The app's layouts are either "wide enough
 * for two columns" or "they aren't". A small-tablet stage between phone and
 * desktop didn't reveal any layouts that wanted a middle behavior.
 */
export function useIsMobile() {
  return useMediaQuery('(max-width: 768px)');
}
