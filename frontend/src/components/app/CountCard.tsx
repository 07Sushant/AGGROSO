import { cn } from "@/lib/utils";

/** Number, label and a visible one-line definition (spec §8.0). */
export function CountCard({
  label,
  value,
  definition,
  tone = "default",
}: {
  label: string;
  value: number | string | null | undefined;
  definition: string;
  tone?: "default" | "success" | "danger" | "info" | "warning";
}) {
  const toneClass = {
    default: "text-foreground",
    success: "text-success-strong",
    danger: "text-danger-strong",
    info: "text-info-strong",
    warning: "text-warning-strong",
  }[tone];
  return (
    <div className="min-w-0 rounded-lg border border-border bg-surface p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-xl font-semibold tabular-nums", toneClass)}>{value ?? "-"}</p>
      <p className="mt-1 text-xs text-muted-foreground">{definition}</p>
    </div>
  );
}

export const COUNT_DEFINITIONS = {
  source: "Records in the frozen source snapshot.",
  transformed: "Records where every transform succeeded.",
  accepted: "Transformed records that passed target validation and duplicate checks.",
  rejected: "Records quarantined in the dry run (transform or validation error).",
  inserted: "Rows written to the target by this run.",
  skipped: "Rows already in the target with the same key; not written again.",
  quarantined: "Rows rejected at execute time (target constraint conflicts).",
  target: "Target rows currently attributed to this run.",
} as const;
