import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api";

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Fetches `fn()` on mount and whenever `deps` changes, exposing a
 * `reload()` for after a mutation. Kept intentionally simple (no caching,
 * no dedup) -- the app's data volumes and click-driven refetches don't
 * need more than that. */
export function useFetch<T>(fn: () => Promise<T>, deps: React.DependencyList): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const stableFn = useCallback(fn, deps); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    stableFn()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.friendlyMessage : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stableFn, tick]);

  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}
