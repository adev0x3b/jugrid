import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MapViewProps } from "./MapView";

// A stand-in for MapLibre that records what the component asks of it. Its style never
// reports loaded, as MapLibre's does not while basemap tiles are still arriving.
const maps = vi.hoisted(() => [] as FakeMap[]);

interface FakeMap {
  handlers: Record<string, (() => void)[]>;
  sources: Record<string, { setData: ReturnType<typeof vi.fn<(data: unknown) => void>> }>;
  setStyle: ReturnType<typeof vi.fn<(style: string, options: object) => void>>;
  fire: (event: string) => void;
}

vi.mock("maplibre-gl/dist/maplibre-gl-worker.mjs?url", () => ({ default: "" }));
vi.mock("maplibre-gl", () => {
  class FakeMapLibre implements FakeMap {
    handlers: Record<string, (() => void)[]> = {};
    sources: Record<string, { setData: ReturnType<typeof vi.fn<(data: unknown) => void>> }> = {};
    setStyle = vi.fn<(style: string, options: object) => void>();
    constructor() {
      maps.push(this);
    }
    fire(event: string) {
      for (const handler of this.handlers[event] ?? []) handler();
    }
    on(event: string, layerOrHandler: unknown, handler?: () => void) {
      const fn = (handler ?? layerOrHandler) as () => void;
      (this.handlers[typeof layerOrHandler === "string" ? `${event}:${layerOrHandler}` : event] ??=
        []).push(fn);
    }
    isStyleLoaded() {
      return false;
    }
    addControl() {}
    addSource(id: string) {
      this.sources[id] = { setData: vi.fn<(data: unknown) => void>() };
    }
    getSource(id: string) {
      return this.sources[id];
    }
    addLayer() {}
    moveLayer() {}
    setFilter() {}
    removeFeatureState() {}
    setFeatureState() {}
    fitBounds() {}
    remove() {}
    getCanvas() {
      return { style: {} };
    }
  }
  return {
    Map: FakeMapLibre,
    NavigationControl: function NavigationControl() {},
    LngLatBounds: function LngLatBounds() {},
    setWorkerUrl: () => {},
  };
});

const { MapView } = await import("./MapView");

const ASSETS: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: 1,
      properties: { kind: "substation", level: "high" },
      geometry: { type: "Point", coordinates: [7.7, 45.1] },
    },
  ],
};

function props(overrides: Partial<MapViewProps> = {}): MapViewProps {
  return {
    theme: "light",
    bbox: [6.6, 44.0, 9.2, 46.5],
    assets: undefined,
    grid: undefined,
    kinds: ["substation"],
    selected: null,
    focus: null,
    onSelect: () => {},
    ...overrides,
  };
}

describe("MapView", () => {
  it("draws assets that arrive while the basemap is still loading", () => {
    const { rerender } = render(<MapView {...props()} />);
    const map = maps.at(-1)!;
    map.fire("style.load");

    rerender(<MapView {...props({ assets: ASSETS })} />);

    expect(map.sources.assets?.setData).toHaveBeenLastCalledWith(ASSETS);
  });

  it("draws assets that arrived before the style, once it loads", () => {
    render(<MapView {...props({ assets: ASSETS })} />);
    const map = maps.at(-1)!;

    map.fire("style.load");

    expect(map.sources.assets?.setData).toHaveBeenLastCalledWith(ASSETS);
  });

  it("reloads the whole style when the theme changes, so the layers come back", () => {
    const { rerender } = render(<MapView {...props()} />);
    const map = maps.at(-1)!;

    rerender(<MapView {...props({ theme: "dark" })} />);

    expect(map.setStyle).toHaveBeenLastCalledWith(expect.stringContaining("dark"), {
      diff: false,
    });
  });
});
