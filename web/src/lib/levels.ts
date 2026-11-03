import type { Kind, Level, View } from "../api";

export const LEVELS: Level[] = ["low", "medium", "high", "very_high"];

export const LEVEL_LABEL: Record<Level, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  very_high: "Very high",
};

/** One colour per level, readable on both the light and the dark base map. */
export const LEVEL_COLOR: Record<Level | "unknown", string> = {
  low: "#2e9e6b",
  medium: "#e3b505",
  high: "#f07c1e",
  very_high: "#d7263d",
  unknown: "#94a3b8",
};

export const KIND_LABEL: Record<Kind, string> = {
  line: "Power lines",
  minor_line: "Distribution lines",
  cable: "Underground cables",
  substation: "Substations",
  plant: "Power plants",
};

export const KIND_SINGULAR: Record<Kind, string> = {
  line: "Power line",
  minor_line: "Distribution line",
  cable: "Underground cable",
  substation: "Substation",
  plant: "Power plant",
};

export const LINE_KINDS: Kind[] = ["line", "minor_line", "cable"];

export const VIEW_LABEL: Record<View, string> = {
  overall: "Overall",
  heat: "Heat",
  heavy_rain: "Heavy rain",
  wind: "Wind",
  wet_snow: "Wet snow",
  flood: "Flood",
};

export function levelOf(score: number | null | undefined): Level | null {
  if (score === null || score === undefined) return null;
  if (score < 0.25) return "low";
  if (score < 0.5) return "medium";
  if (score < 0.75) return "high";
  return "very_high";
}
