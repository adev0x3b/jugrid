export type ScenarioKey = "baseline" | "ssp245_2050" | "ssp585_2050";
export type HazardKey = "heat" | "heavy_rain" | "wind" | "wet_snow" | "flood";
export type View = "overall" | HazardKey;
export type Kind = "line" | "minor_line" | "cable" | "substation" | "plant";
export type Level = "low" | "medium" | "high" | "very_high";

export interface Scenario {
  key: ScenarioKey;
  label: string;
  start_year: number;
  end_year: number;
}

export interface Hazard {
  key: HazardKey;
  label: string;
  indicator: string;
  unit: string;
  low: number;
  high: number;
  projected: boolean;
}

export interface Run {
  step: string;
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  detail: string | null;
}

export type GridSource = "corrected" | "raw";

/** The model card of the bias correction the scores use. */
export interface Correction {
  version: string;
  method: string;
  climate_model: string;
  reference: string;
  trained_on: [number, number];
  held_out_from: number;
  variables: Record<
    string,
    {
      transform: "difference" | "ratio";
      unit: string;
      held_out_years: { raw: number; empirical: number; model: number };
      held_out_cells: { raw: number; model: number };
    }
  >;
  indicators: Record<
    string,
    {
      observed_mean: number;
      raw_mean: number;
      model_mean: number;
      raw_error: number;
      model_error: number;
    }
  >;
}

export interface Meta {
  region: string;
  bbox: [number, number, number, number];
  climate_model: string;
  scenarios: Scenario[];
  hazards: Hazard[];
  kinds: Kind[];
  vulnerability: Record<Kind, Record<HazardKey, number>>;
  sources: { name: string; url: string; license: string }[];
  runs: Run[];
  correction: Correction | null;
}

export interface Risk {
  scenario: ScenarioKey;
  hazard: View;
  value: number | null;
  score: number | null;
  level: Level | null;
  flooded_km: number | null;
}

export interface Asset {
  id: number;
  osm_type: string;
  osm_id: number;
  osm_url: string;
  kind: Kind;
  name: string | null;
  operator: string | null;
  voltage_kv: number | null;
  length_km: number;
  lon: number;
  lat: number;
  geometry: GeoJSON.Geometry;
  tags: Record<string, string>;
  risks: Risk[];
}

export interface KindSummary {
  kind: Kind;
  count: number;
  length_km: number;
  levels: Record<Level | "unknown", number>;
}

export interface RankedAsset {
  id: number;
  kind: Kind;
  name: string | null;
  operator: string | null;
  voltage_kv: number | null;
  length_km: number;
  value: number | null;
  score: number;
  level: Level;
  baseline_score: number | null;
  change: number | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string, params?: URLSearchParams): Promise<T> {
  const url = params && [...params].length ? `${path}?${params}` : path;
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let message = `The server answered ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Not JSON: keep the status line.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export function query(values: Record<string, string | number | string[] | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined) continue;
    for (const one of Array.isArray(value) ? value : [value]) params.append(key, String(one));
  }
  return params;
}

export const api = {
  meta: () => get<Meta>("/api/meta"),
  assets: (scenario: ScenarioKey, view: View) =>
    get<GeoJSON.FeatureCollection>("/api/assets", query({ scenario, view })),
  asset: (id: number) => get<Asset>(`/api/assets/${id}`),
  summary: (scenario: ScenarioKey) => get<KindSummary[]>("/api/summary", query({ scenario })),
  ranking: (scenario: ScenarioKey, view: View, kinds: Kind[], order: "score" | "change") =>
    get<RankedAsset[]>("/api/ranking", query({ scenario, view, kind: kinds, order, limit: 25 })),
  grid: (hazard: HazardKey, scenario: ScenarioKey, correction: GridSource) =>
    get<GeoJSON.FeatureCollection>(`/api/grid/${hazard}`, query({ scenario, correction })),
  exportUrl: (scenario: ScenarioKey) => `/api/export.csv?${query({ scenario })}`,
};
