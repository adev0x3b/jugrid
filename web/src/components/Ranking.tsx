import type { RankedAsset } from "../api";
import { formatChange, formatKv } from "../lib/format";
import { KIND_SINGULAR } from "../lib/levels";
import { LevelDot } from "./LevelDot";

export type Order = "score" | "change";

export function Ranking({
  rows,
  order,
  canCompare,
  loading,
  onOrder,
  onSelect,
}: {
  rows: RankedAsset[] | undefined;
  order: Order;
  canCompare: boolean;
  loading: boolean;
  onOrder: (order: Order) => void;
  onSelect: (id: number) => void;
}) {
  const effective = canCompare ? order : "score";
  return (
    <section aria-labelledby="ranking-title">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <h2
          id="ranking-title"
          className="text-xs font-semibold tracking-wide text-slate-600 dark:text-slate-400 uppercase dark:text-slate-400"
        >
          {canCompare ? "Assets" : "Most exposed"}
        </h2>
        {canCompare && (
          <fieldset className="flex gap-1 text-xs">
            <legend className="sr-only">Sort the list</legend>
            {(["score", "change"] as const).map((o) => (
              <button
                key={o}
                type="button"
                aria-pressed={effective === o}
                onClick={() => onOrder(o)}
                className={`rounded px-2 py-0.5 focus-visible:outline-2 focus-visible:outline-amber-500 ${
                  effective === o
                    ? "bg-slate-200 font-medium dark:bg-slate-700"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`}
              >
                {o === "score" ? "Most exposed" : "Rising fastest"}
              </button>
            ))}
          </fieldset>
        )}
      </div>
      {loading && !rows ? (
        <p className="text-sm text-slate-600 dark:text-slate-400">Loading…</p>
      ) : rows && rows.length > 0 ? (
        <ol className="divide-y divide-slate-200 dark:divide-slate-800">
          {rows.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                onClick={() => onSelect(row.id)}
                className="flex w-full items-center gap-2 px-1 py-1.5 text-left text-sm hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-amber-500 dark:hover:bg-slate-800"
              >
                <LevelDot level={row.level} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate">
                    {row.name ?? `Unnamed ${KIND_SINGULAR[row.kind].toLowerCase()}`}
                  </span>
                  <span className="block truncate text-xs text-slate-600 dark:text-slate-400">
                    {[KIND_SINGULAR[row.kind], formatKv(row.voltage_kv), row.operator]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                <span className="text-right tabular-nums">
                  <span className="block font-medium">{Math.round(row.score * 100)}</span>
                  {effective === "change" && (
                    <span className="block text-xs text-red-700 dark:text-red-400">
                      {formatChange(row.change)}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-400">No scored assets in this view.</p>
      )}
    </section>
  );
}
