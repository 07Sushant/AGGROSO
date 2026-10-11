import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/api/endpoints";
import { qk } from "@/lib/queryKeys";

const SLOW_MS = 2500;

/**
 * "Waking the server" (spec §8.4 cold start): the first /health/live call is watched; if it
 * takes longer than a few seconds (HF Space waking up), `waking` is true until it answers.
 */
export function useServerWake(): { waking: boolean; down: boolean } {
  const [waking, setWaking] = useState(false);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => !cancelled && setWaking(true), SLOW_MS);
    const attempt = async (tries: number): Promise<void> => {
      try {
        await api.live();
        if (!cancelled) {
          setWaking(false);
          setDown(false);
        }
      } catch {
        if (cancelled) return;
        if (tries > 0) {
          setWaking(true);
          window.setTimeout(() => void attempt(tries - 1), 4000);
        } else {
          setWaking(false);
          setDown(true);
        }
      } finally {
        window.clearTimeout(timer);
      }
    };
    void attempt(15);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  return { waking, down };
}

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: api.health, refetchInterval: 60_000, staleTime: 30_000 });
}

export function useConfig() {
  return useQuery({ queryKey: qk.config, queryFn: api.config, staleTime: 5 * 60_000 });
}
