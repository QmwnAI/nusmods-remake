/**
 * useAsync — small hook that unifies the loading/error/data trinity we've been
 * repeating on every page.
 *
 * Before:
 *   const [data, setData] = useState(null);
 *   const [loading, setLoading] = useState(true);
 *   const [error, setError] = useState(null);
 *   useEffect(() => {
 *     (async () => {
 *       try { setData(await api.thing()); }
 *       catch (e) { setError(e.message); }
 *       finally { setLoading(false); }
 *     })();
 *   }, [...deps]);
 *
 * After:
 *   const { data, loading, error, refetch } = useAsync(() => api.thing(), [...deps]);
 *
 * Cancellation: if the effect re-runs (deps changed) or the component unmounts
 * before the fetch resolves, we discard the result so we don't set state on an
 * unmounted component or clobber newer data with stale results.
 *
 * When to use it:
 *   - One-shot fetches on mount / when deps change.
 *   - Not for interactive mutations (POST/PUT/DELETE from a button click) —
 *     for those, useCallback + try/catch + toast is clearer.
 *   - Not when you need optimistic updates or manual state control.
 *
 * Returns { data, loading, error, refetch }:
 *   - `data` is the last successful value (unchanged on subsequent errors).
 *   - `loading` is true during first load AND during refetches.
 *   - `error` is null | Error | string.
 *   - `refetch` re-runs the fetch.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export function useAsync(asyncFn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Latest asyncFn ref so refetch always calls the most recent closure.
  const fnRef = useRef(asyncFn);
  fnRef.current = asyncFn;

  // Bumps on each fetch attempt; identifies stale resolutions.
  const runIdRef = useRef(0);

  const run = useCallback(() => {
    const myRunId = ++runIdRef.current;
    setLoading(true);
    setError(null);
    Promise.resolve()
      .then(() => fnRef.current())
      .then((result) => {
        if (myRunId !== runIdRef.current) return;
        setData(result);
        setLoading(false);
      })
      .catch((e) => {
        if (myRunId !== runIdRef.current) return;
        setError(e);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    run();
    // Bump on cleanup so any in-flight promise becomes a no-op.
    return () => { runIdRef.current++; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, refetch: run };
}
