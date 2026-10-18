"use client";
import { useCallback, useState } from "react";
import { errorMessage } from "@/components/ui";

/** Tracks one async request: its result, its error, and whether it is in flight. */
export function useRun<T>() {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (fn: () => Promise<T>) => {
    setBusy(true); setError(null);
    try { setData(await fn()); }
    catch (e) { setData(null); setError(errorMessage(e)); }
    finally { setBusy(false); }
  }, []);
  return { data, error, busy, run };
}
