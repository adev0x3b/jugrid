import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { KindSummary, RankedAsset } from "./api";
import { META, mockApi, renderWithQuery } from "./testing";

vi.mock("./components/MapView", () => ({
  MapView: ({ onSelect }: { onSelect: (id: number) => void }) => (
    <button type="button" onClick={() => onSelect(7)}>
      map
    </button>
  ),
}));

const SUMMARY: KindSummary[] = [
  {
    kind: "line",
    count: 3,
    length_km: 120.4,
    levels: { low: 1, medium: 1, high: 0, very_high: 1, unknown: 0 },
  },
  {
    kind: "substation",
    count: 2,
    length_km: 0,
    levels: { low: 2, medium: 0, high: 0, very_high: 0, unknown: 0 },
  },
];
const RANKED: RankedAsset[] = [
  {
    id: 7,
    kind: "line",
    name: "Linea Torino-Chivasso",
    operator: "Terna",
    voltage_kv: 132,
    length_km: 20,
    value: 14,
    score: 0.92,
    level: "very_high",
    baseline_score: 0.3,
    change: 0.62,
  },
];

function api(overrides: Record<string, unknown> = {}) {
  return mockApi({
    "/api/meta": META,
    "/api/summary": SUMMARY,
    "/api/ranking": RANKED,
    "/api/assets?": { type: "FeatureCollection", features: [] },
    "/api/assets/7": {
      ...RANKED[0],
      osm_type: "way",
      osm_id: 1,
      osm_url: "https://osm/way/1",
      lon: 7,
      lat: 45,
      geometry: { type: "Point", coordinates: [7, 45] },
      tags: {},
      risks: [],
    },
    ...overrides,
  });
}

beforeEach(() => window.history.replaceState(null, "", "/"));
afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("shows the region, the summary and the most exposed assets", async () => {
    api();
    renderWithQuery(<App />);
    expect(await screen.findByText("Piemonte power grid")).toBeInTheDocument();
    const lists = screen.getByRole("complementary", { name: "Map controls and lists" });
    expect(await within(lists).findByText("120 km")).toBeInTheDocument();
    expect(
      within(lists).getByRole("button", { name: /Linea Torino-Chivasso/ }),
    ).toBeInTheDocument();
  });

  it("keeps the scenario and view in the address and asks the API for them", async () => {
    const fetchMock = api();
    renderWithQuery(<App />);
    const lists = await screen.findByRole("complementary", { name: "Map controls and lists" });
    await userEvent.click(screen.getByRole("radio", { name: /high emissions/ }));
    await userEvent.click(within(lists).getByRole("button", { name: "Wind" }));
    expect(window.location.search).toBe("?scenario=ssp585_2050&view=wind");
    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls).toContain("/api/assets?scenario=ssp585_2050&view=wind");
    expect(within(lists).getByRole("button", { name: "Rising fastest" })).toBeInTheDocument();
  });

  it("hides a kind of asset, but never all of them", async () => {
    api();
    renderWithQuery(<App />);
    const lists = await screen.findByRole("complementary", { name: "Map controls and lists" });
    const lines = await within(lists).findByRole("button", { name: /Power lines/ });
    await userEvent.click(lines);
    expect(window.location.search).toBe("?kinds=minor_line%2Ccable%2Csubstation%2Cplant");
  });

  it("opens an asset from the list", async () => {
    api();
    renderWithQuery(<App />);
    const lists = await screen.findByRole("complementary", { name: "Map controls and lists" });
    await userEvent.click(
      await within(lists).findByRole("button", { name: /Linea Torino-Chivasso/ }),
    );
    expect(window.location.search).toBe("?asset=7");
    expect(
      await screen.findByRole("heading", { name: "Linea Torino-Chivasso" }),
    ).toBeInTheDocument();
  });

  it("tells a fresh install how to fill the map", async () => {
    api({ "/api/summary": [] });
    renderWithQuery(<App />);
    expect(await screen.findByText(/No assets yet/)).toHaveTextContent(
      "docker compose run --rm ingest",
    );
  });

  it("says so when the API is down", async () => {
    mockApi({});
    renderWithQuery(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("JuGrid cannot reach its API.");
  });
});
