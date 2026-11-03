import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import { api, type HazardKey, type Kind } from "./api";
import { AboutDialog } from "./components/AboutDialog";
import { AssetPanel } from "./components/AssetPanel";
import { Legend } from "./components/Legend";
import { Ranking, type Order } from "./components/Ranking";
import { ScenarioPicker } from "./components/ScenarioPicker";
import { Summary } from "./components/Summary";
import { ViewPicker } from "./components/ViewPicker";
import { useTheme } from "./lib/theme";
import { useMapState } from "./lib/urlState";

const MapView = lazy(() => import("./components/MapView").then((m) => ({ default: m.MapView })));

export function App() {
  const [state, update] = useMapState();
  const [theme, toggleTheme] = useTheme();
  const [order, setOrder] = useState<Order>("score");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const assets = useQuery({
    queryKey: ["assets", state.scenario, state.view],
    queryFn: () => api.assets(state.scenario, state.view),
    placeholderData: keepPreviousData,
  });
  const summary = useQuery({
    queryKey: ["summary", state.scenario],
    queryFn: () => api.summary(state.scenario),
    placeholderData: keepPreviousData,
  });
  const canCompare = state.scenario !== "baseline";
  const effectiveOrder = canCompare ? order : "score";
  const ranking = useQuery({
    queryKey: ["ranking", state.scenario, state.view, state.kinds, effectiveOrder],
    queryFn: () => api.ranking(state.scenario, state.view, state.kinds, effectiveOrder),
    placeholderData: keepPreviousData,
  });
  const gridHazard: HazardKey | null =
    state.grid && state.view !== "overall" && state.view !== "flood" ? state.view : null;
  const grid = useQuery({
    queryKey: ["grid", gridHazard, state.scenario],
    queryFn: () => api.grid(gridHazard!, state.scenario),
    enabled: gridHazard !== null,
  });
  const selected = useQuery({
    queryKey: ["asset", state.asset],
    queryFn: () => api.asset(state.asset!),
    enabled: state.asset !== null,
  });

  const toggleKind = (kind: Kind) => {
    const next = state.kinds.includes(kind)
      ? state.kinds.filter((k) => k !== kind)
      : [...state.kinds, kind];
    update({ kinds: next.length ? next : state.kinds });
  };

  if (meta.isPending) {
    return <p className="p-6 text-sm text-slate-600 dark:text-slate-400">Loading JuGrid…</p>;
  }
  if (meta.isError) {
    return (
      <div role="alert" className="p-6 text-sm">
        <p className="font-semibold">JuGrid cannot reach its API.</p>
        <p className="text-slate-600 dark:text-slate-300">{meta.error.message}</p>
      </div>
    );
  }

  const m = meta.data;
  const empty = summary.data !== undefined && summary.data.length === 0;
  const failed = [assets, summary, ranking].find((q) => q.isError)?.error;
  const climateView = state.view !== "overall" && state.view !== "flood";

  const panel = (
    <div className="space-y-5">
      <ViewPicker value={state.view} onChange={(view) => update({ view })} />
      <Legend view={state.view} hazards={m.hazards} />
      {climateView && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={state.grid}
            onChange={(e) => update({ grid: e.target.checked })}
            className="size-4 accent-slate-900 dark:accent-amber-400"
          />
          Show the climate grid
        </label>
      )}
      {summary.data && <Summary rows={summary.data} kinds={state.kinds} onToggle={toggleKind} />}
      <Ranking
        rows={ranking.data}
        order={order}
        canCompare={canCompare}
        loading={ranking.isFetching}
        onOrder={setOrder}
        onSelect={(asset) => {
          update({ asset });
          setSheetOpen(false);
        }}
      />
      <a
        href={api.exportUrl(state.scenario)}
        download
        className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-amber-500 dark:border-slate-600 dark:hover:bg-slate-800"
      >
        Download this scenario as CSV
      </a>
    </div>
  );

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-200 px-3 py-2 md:flex-nowrap md:px-4 dark:border-slate-800">
        <div className="flex min-w-0 flex-1 items-center gap-2 md:flex-none">
          <img src="/favicon.svg" alt="" className="size-7" />
          <h1 className="text-lg font-bold tracking-tight">JuGrid</h1>
          <span className="truncate text-sm text-slate-600 dark:text-slate-400">
            {m.region} power grid
          </span>
        </div>
        <div className="order-last w-full md:order-none md:ml-auto md:w-[26rem]">
          <ScenarioPicker
            scenarios={m.scenarios}
            value={state.scenario}
            onChange={(scenario) => update({ scenario })}
          />
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setAboutOpen(true)}
            className="rounded-md px-2.5 py-1.5 text-sm hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-amber-500 dark:hover:bg-slate-800"
          >
            About the data
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            className="rounded-md p-2 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-amber-500 dark:hover:bg-slate-800"
          >
            {theme === "dark" ? (
              <svg aria-hidden="true" viewBox="0 0 20 20" className="size-5" fill="currentColor">
                <path d="M10 3a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V4a1 1 0 0 1 1-1Zm0 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm6-5a1 1 0 1 1 0 2h-1a1 1 0 1 1 0-2h1ZM5 10a1 1 0 0 1-1 1H3a1 1 0 1 1 0-2h1a1 1 0 0 1 1 1Zm5 5a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1Zm4.24-9.66a1 1 0 0 1 0 1.42l-.7.7a1 1 0 1 1-1.42-1.41l.7-.71a1 1 0 0 1 1.42 0ZM7.88 13.54a1 1 0 0 1 0 1.41l-.71.71a1 1 0 0 1-1.41-1.42l.7-.7a1 1 0 0 1 1.42 0Zm6.36 1.41a1 1 0 0 1-1.42 0l-.7-.7a1 1 0 1 1 1.41-1.42l.71.71a1 1 0 0 1 0 1.41ZM7.17 7.17a1 1 0 0 1-1.41 0l-.7-.7a1 1 0 0 1 1.41-1.42l.7.71a1 1 0 0 1 0 1.41Z" />
              </svg>
            ) : (
              <svg aria-hidden="true" viewBox="0 0 20 20" className="size-5" fill="currentColor">
                <path d="M17.3 13.4A7.5 7.5 0 0 1 6.6 2.7a.6.6 0 0 0-.8-.7 8.5 8.5 0 1 0 12.2 12.2.6.6 0 0 0-.7-.8Z" />
              </svg>
            )}
          </button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        <aside
          aria-label="Map controls and lists"
          className="hidden w-96 shrink-0 overflow-y-auto border-r border-slate-200 p-4 md:block dark:border-slate-800"
        >
          {panel}
        </aside>

        <main className="relative min-w-0 flex-1">
          <Suspense
            fallback={
              <p className="p-4 text-sm text-slate-600 dark:text-slate-400">Loading the map…</p>
            }
          >
            <MapView
              theme={theme}
              bbox={m.bbox}
              assets={assets.data}
              grid={gridHazard ? grid.data : undefined}
              kinds={state.kinds}
              selected={state.asset}
              focus={selected.data?.geometry ?? null}
              onSelect={(asset) => update({ asset })}
            />
          </Suspense>

          {(empty || failed) && (
            <p
              aria-live="polite"
              className="absolute top-3 left-1/2 z-10 w-[min(28rem,calc(100%-1.5rem))] -translate-x-1/2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 shadow dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
            >
              {failed ? (
                <>Could not load the map data: {failed.message}</>
              ) : (
                <>
                  No assets yet. Fill the map with{" "}
                  <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">
                    docker compose run --rm ingest
                  </code>
                  .
                </>
              )}
            </p>
          )}

          {state.asset !== null && (
            <AssetPanel
              id={state.asset}
              scenarios={m.scenarios}
              hazards={m.hazards}
              onClose={() => update({ asset: null })}
            />
          )}

          {state.asset === null && (
            <div className="absolute inset-x-0 bottom-0 z-10 md:hidden">
              <div
                className={`rounded-t-2xl border-t border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900 ${
                  sheetOpen ? "max-h-[70dvh] overflow-y-auto" : ""
                }`}
              >
                <button
                  type="button"
                  aria-expanded={sheetOpen}
                  onClick={() => setSheetOpen(!sheetOpen)}
                  className="flex w-full flex-col items-center gap-1 px-4 pt-2 pb-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-amber-500"
                >
                  <span
                    aria-hidden="true"
                    className="h-1 w-10 rounded-full bg-slate-300 dark:bg-slate-600"
                  />
                  {sheetOpen ? "Hide the lists" : "Hazards, assets and the most exposed"}
                </button>
                {sheetOpen ? (
                  <div className="px-4 pb-4">{panel}</div>
                ) : (
                  <div className="px-4 pb-3">
                    <Legend view={state.view} hazards={m.hazards} />
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>

      <AboutDialog meta={m} open={aboutOpen} onClose={() => setAboutOpen(false)} />
    </div>
  );
}
