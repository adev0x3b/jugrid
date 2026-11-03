import type { View } from "../api";
import { VIEW_LABEL } from "../lib/levels";

const VIEWS: View[] = ["overall", "heat", "heavy_rain", "wind", "wet_snow", "flood"];

export function ViewPicker({ value, onChange }: { value: View; onChange: (v: View) => void }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-xs font-semibold tracking-wide text-slate-600 dark:text-slate-400 uppercase dark:text-slate-400">
        Colour by
      </legend>
      <div className="flex flex-wrap gap-1.5">
        {VIEWS.map((view) => (
          <button
            key={view}
            type="button"
            aria-pressed={view === value}
            onClick={() => onChange(view)}
            className={`rounded-full border px-3 py-1 text-sm transition focus-visible:outline-2 focus-visible:outline-amber-500 ${
              view === value
                ? "border-slate-900 bg-slate-900 text-white dark:border-amber-400 dark:bg-amber-400 dark:text-slate-950"
                : "border-slate-300 hover:border-slate-500 dark:border-slate-600 dark:hover:border-slate-400"
            }`}
          >
            {VIEW_LABEL[view]}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
