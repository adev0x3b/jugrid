import { useCallback, useSyncExternalStore } from "react";
import type { Kind, ScenarioKey, View } from "../api";

/** What the page shows lives in the address, so a link opens the same map. */
export interface MapState {
  scenario: ScenarioKey;
  view: View;
  kinds: Kind[];
  asset: number | null;
  grid: boolean;
  /** The climate grid from the raw projections instead of the bias-corrected ones. */
  raw: boolean;
}

const SCENARIOS: ScenarioKey[] = ["baseline", "ssp245_2050", "ssp585_2050"];
const VIEWS: View[] = ["overall", "heat", "heavy_rain", "wind", "wet_snow", "flood"];
export const ALL_KINDS: Kind[] = ["line", "minor_line", "cable", "substation", "plant"];

export function parse(search: string): MapState {
  const params = new URLSearchParams(search);
  const scenario = params.get("scenario") as ScenarioKey | null;
  const view = params.get("view") as View | null;
  const kinds = (params.get("kinds") ?? "")
    .split(",")
    .filter((k): k is Kind => (ALL_KINDS as string[]).includes(k));
  const asset = Number(params.get("asset"));
  return {
    scenario: scenario && SCENARIOS.includes(scenario) ? scenario : "baseline",
    view: view && VIEWS.includes(view) ? view : "overall",
    kinds: kinds.length ? kinds : ALL_KINDS,
    asset: Number.isInteger(asset) && asset > 0 ? asset : null,
    grid: params.get("grid") === "1",
    raw: params.get("raw") === "1",
  };
}

export function serialize(state: MapState): string {
  const params = new URLSearchParams();
  if (state.scenario !== "baseline") params.set("scenario", state.scenario);
  if (state.view !== "overall") params.set("view", state.view);
  if (state.kinds.length !== ALL_KINDS.length) params.set("kinds", state.kinds.join(","));
  if (state.asset !== null) params.set("asset", String(state.asset));
  if (state.grid) params.set("grid", "1");
  if (state.raw) params.set("raw", "1");
  const text = params.toString();
  return text ? `?${text}` : "";
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function useMapState(): [MapState, (change: Partial<MapState>) => void] {
  const search = useSyncExternalStore(subscribe, () => window.location.search);
  const state = parse(search);
  const update = useCallback((change: Partial<MapState>) => {
    const next = { ...parse(window.location.search), ...change };
    const url = `${window.location.pathname}${serialize(next)}`;
    window.history.replaceState(null, "", url);
    for (const listener of listeners) listener();
  }, []);
  return [state, update];
}
