import { useEffect, useRef } from "react";
import type { HazardKey, Meta } from "../api";
import { formatDate } from "../lib/format";
import { KIND_LABEL } from "../lib/levels";

export function AboutDialog({
  meta,
  open,
  onClose,
}: {
  meta: Meta;
  open: boolean;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const hazardKeys = meta.hazards.map((h) => h.key as HazardKey);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="about-title"
      className="m-auto max-h-[90dvh] w-[min(42rem,calc(100%-2rem))] overflow-y-auto rounded-xl bg-white p-0 text-slate-900 shadow-2xl backdrop:bg-slate-950/60 dark:bg-slate-900 dark:text-slate-100"
    >
      <div className="space-y-5 p-5 text-sm leading-relaxed">
        <div className="flex items-start justify-between gap-4">
          <h2 id="about-title" className="text-lg font-semibold">
            How JuGrid scores {meta.region}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-amber-500 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Close
          </button>
        </div>

        <p>
          Every substation, plant, line and cable OpenStreetMap knows in {meta.region} is checked
          against five hazards. Climate hazards come from the daily {meta.climate_model} projections
          of NASA's NEX-GDDP-CMIP6, bias-corrected at 0.25° (about 25 km). A line reads every cell
          it crosses and keeps the worst. Flood depth comes from the Copernicus 1-in-100-year river
          flood map at about 90 m.
        </p>

        <section>
          <h3 className="mb-1 font-semibold">Scenarios</h3>
          <ul className="list-disc pl-5">
            {meta.scenarios.map((s) => (
              <li key={s.key}>{s.label}</li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="mb-1 font-semibold">Hazards</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="text-xs text-slate-600 dark:text-slate-400">
                <tr>
                  <th scope="col" className="py-1 pr-2 font-medium">
                    Hazard
                  </th>
                  <th scope="col" className="py-1 pr-2 font-medium">
                    Indicator
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    No risk → full risk
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {meta.hazards.map((h) => (
                  <tr key={h.key}>
                    <th scope="row" className="py-1 pr-2 font-medium">
                      {h.label}
                    </th>
                    <td className="py-1 pr-2">{h.indicator}</td>
                    <td className="py-1 tabular-nums">
                      {h.low} → {h.high} {h.unit}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h3 className="mb-1 font-semibold">How much each hazard hurts each asset</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left tabular-nums">
              <thead className="text-xs text-slate-600 dark:text-slate-400">
                <tr>
                  <th scope="col" className="py-1 pr-2 font-medium">
                    Asset
                  </th>
                  {meta.hazards.map((h) => (
                    <th key={h.key} scope="col" className="py-1 pr-2 font-medium">
                      {h.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {meta.kinds.map((kind) => (
                  <tr key={kind}>
                    <th scope="row" className="py-1 pr-2 font-medium">
                      {KIND_LABEL[kind]}
                    </th>
                    {hazardKeys.map((h) => (
                      <td key={h} className="py-1 pr-2">
                        {meta.vulnerability[kind][h].toFixed(1)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
            An asset's score for a hazard is the hazard's 0–1 score times this weight; its overall
            score is the highest of them.
          </p>
        </section>

        <section>
          <h3 className="mb-1 font-semibold">Data</h3>
          <ul className="list-disc pl-5">
            {meta.sources.map((s) => (
              <li key={s.url}>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-2"
                >
                  {s.name}
                </a>{" "}
                <span className="text-slate-600 dark:text-slate-400">({s.license})</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="mb-1 font-semibold">Last updates</h3>
          {meta.runs.length === 0 ? (
            <p>Nothing has been ingested yet.</p>
          ) : (
            <ul className="space-y-1">
              {meta.runs.map((run) => (
                <li key={run.step}>
                  <span className="font-medium capitalize">{run.step}</span>: {run.status},{" "}
                  {formatDate(run.started_at)}
                  {run.detail ? (
                    <span className="text-slate-600 dark:text-slate-400"> · {run.detail}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        <p className="text-xs text-slate-600 dark:text-slate-400">
          One climate model and fixed thresholds: a screening tool to find where to look, not an
          engineering assessment of any single asset.
        </p>
      </div>
    </dialog>
  );
}
