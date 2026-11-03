import type { Hazard, View } from "../api";
import { LEVEL_COLOR, LEVEL_LABEL, LEVELS } from "../lib/levels";

export function Legend({ view, hazards }: { view: View; hazards: Hazard[] }) {
  const hazard = hazards.find((h) => h.key === view);
  return (
    <div className="space-y-2">
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs" aria-label="Risk levels">
        {LEVELS.map((level) => (
          <li key={level} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-5 rounded-sm"
              style={{ backgroundColor: LEVEL_COLOR[level] }}
            />
            {LEVEL_LABEL[level]}
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-600 dark:text-slate-400">
        {hazard ? (
          <>
            {hazard.indicator}: no risk at {hazard.low} {hazard.unit}, full at {hazard.high}{" "}
            {hazard.unit}, weighted by how much it hurts each kind of asset.
            {hazard.projected
              ? ""
              : " Flood maps have no projection, so they read the same in every scenario."}
          </>
        ) : (
          <>Each asset takes the colour of its worst hazard.</>
        )}
      </p>
    </div>
  );
}
