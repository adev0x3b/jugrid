import type { Scenario, ScenarioKey } from "../api";

const SUBTITLE: Record<ScenarioKey, string> = {
  baseline: "",
  ssp245_2050: "middle road",
  ssp585_2050: "high emissions",
};

export function ScenarioPicker({
  scenarios,
  value,
  onChange,
}: {
  scenarios: Scenario[];
  value: ScenarioKey;
  onChange: (key: ScenarioKey) => void;
}) {
  return (
    <fieldset className="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
      <legend className="sr-only">Climate scenario</legend>
      {scenarios.map((s) => (
        <label
          key={s.key}
          title={s.label}
          className="cursor-pointer rounded-md px-2 py-1 text-center leading-tight text-slate-600 transition has-checked:bg-white has-checked:font-semibold has-checked:text-slate-900 has-checked:shadow-sm has-focus-visible:outline-2 has-focus-visible:outline-amber-500 hover:text-slate-900 dark:text-slate-300 dark:has-checked:bg-slate-950 dark:has-checked:text-white dark:hover:text-white"
        >
          <input
            type="radio"
            name="scenario"
            value={s.key}
            checked={s.key === value}
            onChange={() => onChange(s.key)}
            className="sr-only"
          />
          <span className="block text-sm">{s.key === "baseline" ? "Today" : "2050"}</span>
          <span className="block text-[11px] text-slate-600 dark:text-slate-400">
            {s.key === "baseline" ? `${s.start_year}–${s.end_year}` : SUBTITLE[s.key]}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
