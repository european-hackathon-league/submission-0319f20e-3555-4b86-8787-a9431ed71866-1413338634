"use client";
import { useCallback, useSyncExternalStore } from "react";
const eventName = "bmw-workspace-preference";
function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener(eventName, listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(eventName, listener);
  };
}
export function useStoredValue(key: string, fallback = "") {
  const snapshot = useCallback(() => {
    try {
      return localStorage.getItem(key) || fallback;
    } catch {
      return fallback;
    }
  }, [key, fallback]);
  const server = useCallback(() => fallback, [fallback]);
  const value = useSyncExternalStore(subscribe, snapshot, server);
  const setValue = useCallback(
    (next: string) => {
      try {
        localStorage.setItem(key, next);
        window.dispatchEvent(new Event(eventName));
      } catch {
        /* Private browsing may disallow persistence. */
      }
    },
    [key],
  );
  return [value, setValue] as const;
}
