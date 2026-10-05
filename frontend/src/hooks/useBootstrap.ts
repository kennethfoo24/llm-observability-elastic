import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, auth, onUnauthorized } from "../lib/api";
import type { AppConfig, ModelInfo, Persona } from "../lib/types";

type Phase = "locked" | "loading" | "ready" | "error";

export function useBootstrap() {
  const [phase, setPhase] = useState<Phase>(auth.get() ? "loading" : "locked");
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | undefined>();
  const alive = useRef(true);

  // Idempotent: a 401 can arrive both via the onUnauthorized subscription and as a thrown ApiError.
  const lock = useCallback(() => {
    auth.clear();
    if (alive.current) {
      setPersonas([]);
      setModels([]);
      setConfig(null);
      setError(undefined);
      setPhase("locked");
    }
  }, []);

  const load = useCallback(async (): Promise<boolean> => {
    try {
      const [p, m, c] = await Promise.all([api.personas(), api.models(), api.config()]);
      if (!alive.current) return true;
      setPersonas(p);
      setModels(m);
      setConfig(c);
      setError(undefined);
      setPhase("ready");
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        lock();
        return false;
      }
      if (alive.current) {
        setError("Could not reach the assistant service. Check that the backend is running and try again.");
        setPhase("error");
      }
      return false;
    }
  }, [lock]);

  useEffect(() => {
    alive.current = true;
    const off = onUnauthorized(lock);
    if (auth.get()) void load();
    return () => {
      alive.current = false;
      off();
    };
  }, [load, lock]);

  // false means the password was rejected (401) or loading failed; only a 401 clears the stored password,
  // so the error screen can retry with it.
  const unlock = useCallback(
    async (pw: string) => {
      auth.set(pw);
      // Stay in "locked" while checking so the gate keeps its busy and error state (it would remount otherwise).
      return load();
    },
    [load],
  );

  const refreshModels = useCallback(async () => {
    try {
      const m = await api.models();
      if (alive.current) setModels(m);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) lock();
    }
  }, [lock]);

  return { phase, personas, models, config, error, unlock, refreshModels, lock, reload: load };
}
