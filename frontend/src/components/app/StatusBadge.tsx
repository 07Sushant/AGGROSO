import {
  AlertTriangle,
  Archive,
  Check,
  CheckCircle2,
  CircleDashed,
  Clock,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  Undo2,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "slate" | "emerald" | "rose" | "sky" | "amber";

/** The single status -> colour/icon mapping (spec §8.0). Always icon + text, never colour only. */
const STATUS: Record<string, { tone: Tone; icon: LucideIcon; label?: string; spin?: boolean }> = {
  DRAFT: { tone: "slate", icon: CircleDashed, label: "Draft" },
  APPROVED: { tone: "emerald", icon: ShieldCheck, label: "Approved" },
  REJECTED: { tone: "rose", icon: XCircle, label: "Rejected" },
  SUPERSEDED: { tone: "slate", icon: Archive, label: "Superseded" },
  REVOKED: { tone: "amber", icon: Undo2, label: "Revoked" },
  QUEUED: { tone: "slate", icon: Clock, label: "Queued" },
  RUNNING: { tone: "sky", icon: Loader2, label: "Running", spin: true },
  ROLLING_BACK: { tone: "sky", icon: Loader2, label: "Rolling back", spin: true },
  PROCESSING: { tone: "sky", icon: Loader2, label: "Processing", spin: true },
  COMPLETED: { tone: "emerald", icon: CheckCircle2, label: "Completed" },
  SUCCEEDED: { tone: "emerald", icon: CheckCircle2, label: "Succeeded" },
  FAILED: { tone: "rose", icon: AlertTriangle, label: "Failed" },
  ROLLED_BACK: { tone: "amber", icon: Undo2, label: "Rolled back" },
  PASS: { tone: "emerald", icon: CheckCircle2, label: "PASS" },
  FAIL: { tone: "rose", icon: XCircle, label: "FAIL" },
  ACCEPTED: { tone: "emerald", icon: Check, label: "Accepted" },
  INSERTED: { tone: "emerald", icon: Check, label: "Inserted" },
  QUARANTINED: { tone: "rose", icon: ShieldAlert, label: "Quarantined" },
  REJECTED_RECORD: { tone: "rose", icon: ShieldAlert, label: "Rejected" },
  SKIPPED_EXISTING: { tone: "slate", icon: Archive, label: "Skipped (exists)" },
  PROPOSED: { tone: "sky", icon: CircleDashed, label: "Proposed" },
};

const TONE: Record<Tone, string> = {
  slate: "bg-muted text-foreground border-border",
  emerald: "bg-success-subtle text-success-strong border-success/30",
  rose: "bg-danger-subtle text-danger-strong border-danger/30",
  sky: "bg-info-subtle text-info-strong border-info/30",
  amber: "bg-warning-subtle text-warning-strong border-warning/30",
};

export function StatusBadge({ status, label, className }: { status: string; label?: string; className?: string }) {
  const def = STATUS[status] ?? { tone: "slate" as Tone, icon: CircleDashed };
  const Icon = def.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium",
        TONE[def.tone],
        className,
      )}
    >
      <Icon className={cn("h-3.5 w-3.5", def.spin && "animate-spin")} aria-hidden="true" />
      {label ?? def.label ?? status}
    </span>
  );
}
