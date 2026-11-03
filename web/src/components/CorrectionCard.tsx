import type { Correction } from "../api";

const VARIABLE_LABEL: Record<string, string> = {
  tasmax: "Daily maximum temperature",
  tas: "Daily mean temperature",
  pr: "Daily rainfall",
  sfcWind: "Daily mean wind",
};

const INDICATOR_LABEL: Record<string, [string, string]> = {
  hot_days: ["Days above 35 °C", "days/yr"],
  wettest_day: ["Wettest day", "mm"],
  windiest_day: ["Windiest day", "m/s"],
  wet_snow_days: ["Wet-snow days", "days/yr"],
};

const n = (value: number, digits = 2) => value.toFixed(digits);
const th = "py-1 pr-2 font-medium";

/** The model card: what the correction learnt from, and how much better it does. */
export function CorrectionCard({ card }: { card: Correction }) {
  const [first, last] = card.trained_on;
  const heldOut = `${card.held_out_from}–${last}`;
  return (
    <section aria-labelledby="correction-title">
      <h3 id="correction-title" className="mb-1 font-semibold">
        Bias correction
      </h3>
      <p>
        Climate models run too warm, too cold, too dry or too windy in places, mountains above all.
        Before scoring, the {card.climate_model} projections are corrected against what was observed
        ({card.reference}, {first}–{last}): a gradient-boosting model learns, per cell and month,
        how each quantile of the model's days maps to the observed one, and the projections keep the
        change they project (quantile delta mapping). The climate grid can show either.
      </p>

      <h4 className="mt-3 mb-1 text-xs font-medium text-slate-600 dark:text-slate-400">
        Average error per quantile, on years and on cells the model did not see
      </h4>
      <div className="overflow-x-auto">
        <table className="w-full text-left tabular-nums">
          <thead className="text-xs text-slate-600 dark:text-slate-400">
            <tr>
              <th scope="col" className={th}>
                Variable
              </th>
              <th scope="col" className={th}>
                {heldOut}: raw
              </th>
              <th scope="col" className={th}>
                corrected
              </th>
              <th scope="col" className={th}>
                Unseen cells: raw
              </th>
              <th scope="col" className={th}>
                corrected
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {Object.entries(card.variables).map(([key, v]) => (
              <tr key={key}>
                <th scope="row" className={th}>
                  {VARIABLE_LABEL[key] ?? key}{" "}
                  <span className="font-normal text-slate-600 dark:text-slate-400">({v.unit})</span>
                </th>
                <td className="py-1 pr-2">{n(v.held_out_years.raw)}</td>
                <td className="py-1 pr-2 font-semibold">{n(v.held_out_years.model)}</td>
                <td className="py-1 pr-2">{n(v.held_out_cells.raw)}</td>
                <td className="py-1 pr-2 font-semibold">{n(v.held_out_cells.model)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h4 className="mt-3 mb-1 text-xs font-medium text-slate-600 dark:text-slate-400">
        The indicators over {heldOut}, averaged over the region
      </h4>
      <div className="overflow-x-auto">
        <table className="w-full text-left tabular-nums">
          <thead className="text-xs text-slate-600 dark:text-slate-400">
            <tr>
              <th scope="col" className={th}>
                Indicator
              </th>
              <th scope="col" className={th}>
                Observed
              </th>
              <th scope="col" className={th}>
                Raw
              </th>
              <th scope="col" className={th}>
                Corrected
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {Object.entries(card.indicators).map(([key, v]) => {
              const [label, unit] = INDICATOR_LABEL[key] ?? [key, ""];
              return (
                <tr key={key}>
                  <th scope="row" className={th}>
                    {label}{" "}
                    <span className="font-normal text-slate-600 dark:text-slate-400">({unit})</span>
                  </th>
                  <td className="py-1 pr-2">{n(v.observed_mean, 1)}</td>
                  <td className="py-1 pr-2">{n(v.raw_mean, 1)}</td>
                  <td className="py-1 pr-2 font-semibold">{n(v.model_mean, 1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
        Model {card.version}. Rainfall and wind are corrected by ratio, temperatures by difference;
        every error is in the variable's own unit.
      </p>
    </section>
  );
}
