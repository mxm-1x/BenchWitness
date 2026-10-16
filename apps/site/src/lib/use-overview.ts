"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Overview } from "./api";

export function useOverview() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/readyz", { cache: "no-store" });
      if (!response.ok) throw new Error("FalkorDB is unavailable");
      const data = await api<Overview>("/api/v1/overview");
      setOverview(data);
      setReady(true);
    } catch (cause) {
      setReady(false);
      setError(cause instanceof Error ? cause.message : "Unable to load graph data");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  return { overview, ready, loading, error, refresh };
}
