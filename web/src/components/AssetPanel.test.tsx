import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Asset } from "../api";
import { META, mockApi, renderWithQuery } from "../testing";
import { AssetPanel } from "./AssetPanel";

const LINE: Asset = {
  id: 7,
  osm_type: "way",
  osm_id: 401,
  osm_url: "https://www.openstreetmap.org/way/401",
  kind: "line",
  name: null,
  operator: "Terna",
  voltage_kv: 132,
  length_km: 20.4,
  lon: 7.7,
  lat: 45.1,
  geometry: {
    type: "LineString",
    coordinates: [
      [7.65, 45.05],
      [7.8, 45.2],
    ],
  },
  tags: {},
  risks: [
    {
      scenario: "baseline",
      hazard: "wind",
      value: 6.5,
      score: 0.06,
      level: "low",
      flooded_km: null,
    },
    {
      scenario: "ssp585_2050",
      hazard: "wind",
      value: 14,
      score: 1,
      level: "very_high",
      flooded_km: null,
    },
    {
      scenario: "ssp585_2050",
      hazard: "overall",
      value: 1,
      score: 1,
      level: "very_high",
      flooded_km: null,
    },
    {
      scenario: "baseline",
      hazard: "flood",
      value: 0.8,
      score: 0.16,
      level: "low",
      flooded_km: 1.25,
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

describe("AssetPanel", () => {
  it("names an unnamed line by its kind and shows voltage, operator and length", async () => {
    mockApi({ "/api/assets/7": LINE });
    renderWithQuery(
      <AssetPanel id={7} scenarios={META.scenarios} hazards={META.hazards} onClose={() => {}} />,
    );
    expect(await screen.findByRole("heading", { name: "Unnamed power line" })).toBeInTheDocument();
    expect(screen.getByText("132 kV · Terna · 20.4 km")).toBeInTheDocument();
  });

  it("tabulates every hazard against every scenario, with units", async () => {
    mockApi({ "/api/assets/7": LINE });
    renderWithQuery(
      <AssetPanel id={7} scenarios={META.scenarios} hazards={META.hazards} onClose={() => {}} />,
    );
    const wind = await screen.findByRole("row", { name: /^Wind/ });
    expect(wind).toHaveTextContent("Low 6.5 m/s");
    expect(wind).toHaveTextContent("Very high 14 m/s");
    expect(screen.getByRole("row", { name: /^Overall/ })).toHaveTextContent("Very high 100");
    expect(
      screen.getByText("1.3 km of this line run through a 1-in-100-year flood."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in OpenStreetMap" })).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/way/401",
    );
  });

  it("closes with the button and with Escape", async () => {
    mockApi({ "/api/assets/7": LINE });
    const onClose = vi.fn<() => void>();
    renderWithQuery(
      <AssetPanel id={7} scenarios={META.scenarios} hazards={META.hazards} onClose={onClose} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("says when the asset is gone", async () => {
    mockApi({});
    renderWithQuery(
      <AssetPanel id={99} scenarios={META.scenarios} hazards={META.hazards} onClose={() => {}} />,
    );
    expect(await screen.findByText("Not found")).toBeInTheDocument();
  });
});
