import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Findings } from "../lib/types";

const EVERY_MS = 3000;
const MAX_TRIES = 8; // Elastic scores an answer 5 to 10 seconds after it is shown

/** Polls for the async quality findings of one answer until they are written, then stops. */
export function useFindings(traceId: string | undefined, enabled: boolean): Findings {
  const [found, setFound] = useState<Findings>({ status: "pending", security: [], quality: [] });
  useEffect(() => {
    setFound({ status: "pending", security: [], quality: [] });
    if (!traceId || !enabled) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const attempt = async (n: number) => {
      let next: Findings = { status: "unavailable", security: [], quality: [] };
      try { next = await api.findings(traceId); } catch { /* keep unavailable */ }
      if (stop) return;
      if (next.status === "ready" || n >= MAX_TRIES) { setFound(next); return; }
      timer = setTimeout(() => attempt(n + 1), EVERY_MS);
    };
    timer = setTimeout(() => attempt(1), EVERY_MS);
    return () => { stop = true; clearTimeout(timer); };
  }, [traceId, enabled]);
  return found;
}
