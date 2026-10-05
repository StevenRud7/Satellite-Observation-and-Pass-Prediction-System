import { useEffect, useState } from "react";

import { fetchHealth } from "../api/client";

export type BackendStatus = "checking" | "online" | "offline";

interface UseBackendHealthResult {
  status: BackendStatus;
  errorMessage: string | null;
}

export function useBackendHealth(): UseBackendHealthResult {
  const [status, setStatus] = useState<BackendStatus>("checking");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check(): Promise<void> {
      try {
        await fetchHealth();
        if (!cancelled) {
          setStatus("online");
          setErrorMessage(null);
        }
      } catch (error) {
        if (!cancelled) {
          setStatus("offline");
          setErrorMessage(error instanceof Error ? error.message : "Unknown error");
        }
      }
    }

    void check();

    return () => {
      cancelled = true;
    };
  }, []);

  return { status, errorMessage };
}
