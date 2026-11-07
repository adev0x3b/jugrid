import { useQuery } from "@tanstack/react-query";
import { useEffect, useEffectEvent } from "react";
import { api, type Hazard, type Risk, type Scenario, type View } from "../api";
import { formatKm, formatKv, formatValue } from "../lib/format";
import { KIND_SINGULAR, LINE_KINDS, VIEW_LABEL } from "../lib/levels";
import { LevelDot } from "./LevelDot";

const ROWS: View[] = ["overall", "heat", "heavy_rain", "wind", "wet_snow", "flood"];

export function AssetPanel({
  id,
  scenarios,
  hazards,
  onClose,
}: {
  id: number;
  scenarios: Scenario[];
  hazards: Hazard[];
  onClose: () => void;
}) {
  const { data, error, isPending } = useQuery({
    queryKey: ["asset", id],
    queryFn: ({ signal }) => api.asset(id, signal),
  });

  // Escape closes the panel. The handler is an effect event, so the listener
  // is registered once and still calls the latest onClose, whatever the
  // parent passes on each render.
  const close = useEffectEvent(onClose);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const risk = (scenario: string, hazard: View): Risk | undefined =>
    data?.risks.find((r) => r.scenario === scenario && r.hazard === hazard);
  const unit = (view: View) => hazards.find((h) => h.key === view)?.unit ?? "";

  return (
    <section
      aria-labelledby="asset-title"
      className="absolute inset-x-0 bottom-0 z-20 max-h-[70%] overflow-y-auto rounded-t-2xl border-t border-slate-200 bg-white p-4 shadow-2xl md:inset-x-auto md:top-3 md:right-3 md:bottom-auto md:max-h-[calc(100%-1.5rem)] md:w-[26rem] md:rounded-xl md:border dark:border-slate-700 dark:bg-slate-900"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold tracking-wide text-slate-600 dark:text-slate-400 uppercase dark:text-slate-400">
            {data ? KIND_SINGULAR[data.kind] : "Asset"}
          </p>
          <h2 id="asset-title" className="text-lg leading-snug font-semibold">
            {data ? (data.name ?? `Unnamed ${KIND_SINGULAR[data.kind].toLowerCase()}`) : "Loading…"}
          </h2>
          {data && (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {[
                formatKv(data.voltage_kv),
                data.operator,
                LINE_KINDS.includes(data.kind) ? formatKm(data.length_km) : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded-md p-1.5 text-slate-600 dark:text-slate-400 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-amber-500 dark:hover:bg-slate-800"
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" className="size-5" fill="currentColor">
            <path d="M5.3 4.3a1 1 0 0 0-1 1.4L8.6 10l-4.3 4.3a1 1 0 1 0 1.4 1.4l4.3-4.3 4.3 4.3a1 1 0 0 0 1.4-1.4L11.4 10l4.3-4.3a1 1 0 0 0-1.4-1.4L10 8.6 5.7 4.3a1 1 0 0 0-.4 0Z" />
          </svg>
        </button>
      </div>

      {error && <p className="text-sm text-red-700 dark:text-red-400">{error.message}</p>}
      {isPending && <p className="text-sm text-slate-600 dark:text-slate-400">Loading…</p>}

      {data && (
        <>
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Risk by hazard and scenario</caption>
              <thead>
                <tr className="text-left text-xs text-slate-600 dark:text-slate-400">
                  <th scope="col" className="px-1 py-1 font-medium">
                    Hazard
                  </th>
                  {scenarios.map((s) => (
                    <th key={s.key} scope="col" className="px-1 py-1 font-medium" title={s.label}>
                      {s.key === "baseline"
                        ? "Today"
                        : s.key === "ssp245_2050"
                          ? "2050 mid"
                          : "2050 high"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {ROWS.map((view) => (
                  <tr key={view} className={view === "overall" ? "font-semibold" : undefined}>
                    <th scope="row" className="px-1 py-1.5 text-left font-medium">
                      {VIEW_LABEL[view]}
                    </th>
                    {scenarios.map((s) => {
                      const r = risk(s.key, view);
                      return (
                        <td key={s.key} className="px-1 py-1.5 align-top">
                          <LevelDot level={r?.level ?? null} />{" "}
                          <span className="tabular-nums">
                            {view === "overall"
                              ? r?.score == null
                                ? "No data"
                                : Math.round(r.score * 100)
                              : formatValue(r?.value, unit(view))}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(() => {
            const wet = risk("baseline", "flood")?.flooded_km;
            return wet ? (
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                {formatKm(wet)} of this line run through a 1-in-100-year flood.
              </p>
            ) : null;
          })()}
          <p className="mt-3 text-xs text-slate-600 dark:text-slate-400">
            Overall is out of 100: the worst hazard, weighted by how much it hurts a{" "}
            {KIND_SINGULAR[data.kind].toLowerCase()}.
          </p>
          <a
            href={data.osm_url}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-block text-sm font-medium text-amber-700 underline-offset-2 hover:underline dark:text-amber-400"
          >
            Open in OpenStreetMap
          </a>
        </>
      )}
    </section>
  );
}
