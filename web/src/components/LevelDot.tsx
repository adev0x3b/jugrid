import type { Level } from "../api";
import { LEVEL_COLOR, LEVEL_LABEL } from "../lib/levels";

export function LevelDot({ level, label = false }: { level: Level | null; label?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className="inline-block size-2.5 shrink-0 rounded-full ring-1 ring-black/10 dark:ring-white/20"
        style={{ backgroundColor: LEVEL_COLOR[level ?? "unknown"] }}
      />
      {label ? (
        <span>{level ? LEVEL_LABEL[level] : "No data"}</span>
      ) : (
        <span className="sr-only">{level ? LEVEL_LABEL[level] : "No data"}</span>
      )}
    </span>
  );
}
