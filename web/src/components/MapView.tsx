import {
  LngLatBounds,
  Map as MapLibre,
  NavigationControl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type MapLayerMouseEvent,
  setWorkerUrl,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { useEffect, useLayoutEffect, useRef } from "react";
import type { Kind } from "../api";
import { LEVEL_COLOR } from "../lib/levels";
import type { Theme } from "../lib/theme";

const STYLE: Record<Theme, string> = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};

const levelColor: ExpressionSpecification = [
  "match",
  ["coalesce", ["get", "level"], "unknown"],
  "low",
  LEVEL_COLOR.low,
  "medium",
  LEVEL_COLOR.medium,
  "high",
  LEVEL_COLOR.high,
  "very_high",
  LEVEL_COLOR.very_high,
  LEVEL_COLOR.unknown,
];

// Vite cannot see the worker MapLibre loads at run time, so it is emitted as an asset and
// pointed at here.
setWorkerUrl(workerUrl);

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export interface MapViewProps {
  theme: Theme;
  bbox: [number, number, number, number];
  assets: GeoJSON.FeatureCollection | undefined;
  grid: GeoJSON.FeatureCollection | undefined;
  kinds: Kind[];
  selected: number | null;
  focus: GeoJSON.Geometry | null;
  onSelect: (id: number | null) => void;
}

function addLayers(map: MapLibre) {
  map.addSource("grid", { type: "geojson", data: EMPTY });
  map.addSource("assets", { type: "geojson", data: EMPTY, promoteId: "id" });
  map.addLayer({
    id: "grid",
    type: "fill",
    source: "grid",
    paint: {
      "fill-color": levelColor,
      "fill-opacity": 0.28,
      "fill-outline-color": "rgba(0,0,0,0)",
    },
  });
  const isLine: ExpressionSpecification = ["==", ["geometry-type"], "LineString"];
  map.addLayer({
    id: "lines-casing",
    type: "line",
    source: "assets",
    filter: ["all", isLine, ["==", ["id"], -1]],
    paint: { "line-color": "#0f172a", "line-width": 8, "line-opacity": 0.8 },
  });
  map.addLayer({
    id: "lines",
    type: "line",
    source: "assets",
    filter: isLine,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": levelColor,
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        7,
        ["case", [">=", ["coalesce", ["get", "voltage_kv"], 0], 200], 2, 1],
        13,
        ["case", [">=", ["coalesce", ["get", "voltage_kv"], 0], 200], 5, 3],
      ],
      "line-dasharray": [
        "case",
        ["==", ["get", "kind"], "cable"],
        ["literal", [2, 1.5]],
        ["literal", [1, 0]],
      ],
    },
  });
  map.addLayer({
    id: "sites",
    type: "circle",
    source: "assets",
    filter: ["==", ["geometry-type"], "Point"],
    paint: {
      "circle-color": levelColor,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 7, 3, 13, 7],
      "circle-stroke-color": [
        "case",
        ["boolean", ["feature-state", "selected"], false],
        "#0f172a",
        "#ffffff",
      ],
      "circle-stroke-width": ["case", ["boolean", ["feature-state", "selected"], false], 3, 1],
    },
  });
}

function sync(map: MapLibre, { assets, grid, kinds, selected }: MapViewProps) {
  if (!map.getSource("assets")) return;
  (map.getSource("assets") as GeoJSONSource).setData(assets ?? EMPTY);
  (map.getSource("grid") as GeoJSONSource).setData(grid ?? EMPTY);
  const kindFilter: ExpressionSpecification = ["in", ["get", "kind"], ["literal", kinds]];
  map.setFilter("lines", ["all", ["==", ["geometry-type"], "LineString"], kindFilter]);
  map.setFilter("sites", ["all", ["==", ["geometry-type"], "Point"], kindFilter]);
  map.setFilter("lines-casing", [
    "all",
    ["==", ["geometry-type"], "LineString"],
    ["==", ["id"], selected ?? -1],
  ]);
  map.removeFeatureState({ source: "assets" });
  if (selected !== null)
    map.setFeatureState({ source: "assets", id: selected }, { selected: true });
}

export function MapView(props: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const latest = useRef(props);
  const { assets, grid, kinds, selected, theme, focus } = props;
  useLayoutEffect(() => {
    latest.current = props;
  });

  useEffect(() => {
    if (!container.current) return;
    const [w, s, e, n] = latest.current.bbox;
    const map = new MapLibre({
      container: container.current,
      style: STYLE[latest.current.theme],
      bounds: [w, s, e, n],
      fitBoundsOptions: { padding: 24 },
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-left");
    map.on("style.load", () => {
      addLayers(map);
      map.moveLayer("lines-casing");
      map.moveLayer("lines");
      map.moveLayer("sites");
      sync(map, latest.current);
    });
    for (const layer of ["lines", "sites"]) {
      map.on("click", layer, (event: MapLayerMouseEvent) => {
        const id = event.features?.[0]?.id;
        if (typeof id === "number") latest.current.onSelect(id);
      });
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    mapRef.current?.setStyle(STYLE[theme]);
  }, [theme]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.isStyleLoaded()) sync(map, { ...latest.current, assets, grid, kinds, selected });
  }, [assets, grid, kinds, selected]);

  useEffect(() => {
    const map = mapRef.current;
    const geometry = focus;
    if (!map || !geometry) return;
    const coords: [number, number][] =
      geometry.type === "Point"
        ? [geometry.coordinates as [number, number]]
        : geometry.type === "LineString"
          ? (geometry.coordinates as [number, number][])
          : geometry.type === "MultiLineString"
            ? (geometry.coordinates.flat() as [number, number][])
            : [];
    if (coords.length === 0) return;
    const bounds = coords.reduce((b, c) => b.extend(c), new LngLatBounds(coords[0], coords[0]));
    map.fitBounds(bounds, { padding: 80, maxZoom: 13, duration: 600 });
  }, [focus]);

  // MapLibre makes its container position: relative, so the container fills a positioned box.
  return (
    <section className="absolute inset-0" aria-label="Map of the grid's assets, coloured by risk">
      <div ref={container} className="h-full w-full" />
    </section>
  );
}
