import type { Kind, KindSummary } from "../api";
import { formatKm } from "../lib/format";
import { KIND_LABEL, LEVEL_COLOR, LEVEL_LABEL, LEVELS, LINE_KINDS } from "../lib/levels";

export function Summary({
  rows,
  kinds,
  onToggle,
}: {
  rows: KindSummary[];
  kinds: Kind[];
  onToggle: (kind: Kind) => void;
}) {
  return (
    <section aria-labelledby="summary-title">
      <h2
        id="summary-title"
        className="mb-1.5 text-xs font-semibold tracking-wide text-slate-600 dark:text-slate-400 uppercase dark:text-slate-400"
      >
        Assets on the map
      </h2>
      <ul className="space-y-1">
        {rows.map((row) => {
          const shown = kinds.includes(row.kind);
          const amount = LINE_KINDS.includes(row.kind)
            ? formatKm(row.length_km)
            : `${row.count.toLocaleString("en")}`;
          return (
            <li key={row.kind}>
              <button
                type="button"
                aria-pressed={shown}
                onClick={() => onToggle(row.kind)}
                className={`w-full rounded-md px-2 py-1.5 text-left transition hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-amber-500 dark:hover:bg-slate-800 ${
                  shown ? "" : "opacity-50"
                }`}
              >
                <span className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className={`inline-flex size-4 items-center justify-center rounded border text-[10px] ${
                        shown
                          ? "border-slate-900 bg-slate-900 text-white dark:border-amber-400 dark:bg-amber-400 dark:text-slate-950"
                          : "border-slate-400"
                      }`}
                    >
                      {shown ? "✓" : ""}
                    </span>
                    {KIND_LABEL[row.kind]}
                  </span>
                  <span className="text-slate-600 tabular-nums dark:text-slate-300">{amount}</span>
                </span>
                <LevelBar row={row} />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function LevelBar({ row }: { row: KindSummary }) {
  const total = row.count || 1;
  const parts = LEVELS.filter((level) => row.levels[level] > 0);
  const description = LEVELS.map((l) => `${row.levels[l]} ${LEVEL_LABEL[l].toLowerCase()}`).join(
    ", ",
  );
  return (
    <span className="mt-1 flex h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
      <span className="sr-only">{description}</span>
      {parts.map((level) => (
        <span
          key={level}
          style={{
            width: `${(row.levels[level] / total) * 100}%`,
            backgroundColor: LEVEL_COLOR[level],
          }}
        />
      ))}
    </span>
  );
}
