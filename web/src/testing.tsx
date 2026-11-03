import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";
import type { Meta } from "./api";

export const META: Meta = {
  region: "Piemonte",
  bbox: [6.62, 44.06, 9.22, 46.47],
  climate_model: "EC-Earth3",
  scenarios: [
    { key: "baseline", label: "Today (1995-2014)", start_year: 1995, end_year: 2014 },
    { key: "ssp245_2050", label: "2050, middle road", start_year: 2041, end_year: 2060 },
    { key: "ssp585_2050", label: "2050, high emissions", start_year: 2041, end_year: 2060 },
  ],
  hazards: [
    {
      key: "heat",
      label: "Extreme heat",
      indicator: "Days a year above 35 °C",
      unit: "days/yr",
      low: 0,
      high: 20,
      projected: true,
    },
    {
      key: "heavy_rain",
      label: "Heavy rain",
      indicator: "Wettest day of the year",
      unit: "mm",
      low: 40,
      high: 120,
      projected: true,
    },
    {
      key: "wind",
      label: "Wind",
      indicator: "Windiest day of the year",
      unit: "m/s",
      low: 5,
      high: 12,
      projected: true,
    },
    {
      key: "wet_snow",
      label: "Wet snow",
      indicator: "Days a year of wet snow on lines",
      unit: "days/yr",
      low: 1,
      high: 12,
      projected: true,
    },
    {
      key: "flood",
      label: "River flood",
      indicator: "Water depth, 1-in-100-year flood",
      unit: "m",
      low: 0,
      high: 1.5,
      projected: false,
    },
  ],
  kinds: ["line", "minor_line", "cable", "substation", "plant"],
  vulnerability: {
    line: { heat: 0.7, heavy_rain: 0.3, wind: 1, wet_snow: 1, flood: 0.3 },
    minor_line: { heat: 0.6, heavy_rain: 0.4, wind: 1, wet_snow: 1, flood: 0.4 },
    cable: { heat: 0.5, heavy_rain: 0.5, wind: 0, wet_snow: 0, flood: 0.7 },
    substation: { heat: 0.7, heavy_rain: 0.6, wind: 0.3, wet_snow: 0.4, flood: 1 },
    plant: { heat: 0.6, heavy_rain: 0.5, wind: 0.5, wet_snow: 0.4, flood: 0.9 },
  },
  sources: [
    {
      name: "OpenStreetMap contributors",
      url: "https://www.openstreetmap.org/copyright",
      license: "ODbL 1.0",
    },
  ],
  runs: [],
  correction: null,
};

export const CORRECTION: NonNullable<Meta["correction"]> = {
  version: "2026-11-03-abc1234",
  method: "Quantile delta mapping learnt by gradient boosting, per cell and month",
  climate_model: "EC-Earth3",
  reference: "E-OBS v32.0e ensemble mean",
  trained_on: [1995, 2014],
  held_out_from: 2010,
  variables: {
    tasmax: {
      transform: "difference",
      unit: "°C",
      held_out_years: { raw: 1.59, empirical: 1.15, model: 1.15 },
      held_out_cells: { raw: 1.33, model: 0.57 },
    },
  },
  indicators: {
    hot_days: {
      observed_mean: 2.1,
      raw_mean: 0.4,
      model_mean: 1.9,
      raw_error: 1.7,
      model_error: 0.6,
    },
  },
};

/** Answers fetch() from a table of path prefixes; the first match wins. */
export function mockApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async (input) => {
    const url = String(input);
    const match = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((prefix) => url.startsWith(prefix));
    if (!match) return new Response(JSON.stringify({ detail: "Not found" }), { status: 404 });
    return new Response(JSON.stringify(routes[match]), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
