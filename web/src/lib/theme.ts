import { useCallback, useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
const KEY = "jugrid-theme";
const listeners = new Set<() => void>();

function current(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function useTheme(): [Theme, () => void] {
  const theme = useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, current);
  const toggle = useCallback(() => {
    const next: Theme = current() === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // Storage blocked: the choice lasts until the page closes.
    }
    for (const listener of listeners) listener();
  }, []);
  return [theme, toggle];
}
