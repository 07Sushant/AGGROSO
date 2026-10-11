import { AlertTriangle, CloudOff } from "lucide-react";
import type { AiStatus } from "@/api/types";

export const BACKUP_BANNER_TEXT =
  "Our main AI service is unavailable right now. A backup AI is handling your request, so responses may take longer.";
export const DOWN_BANNER_TEXT =
  "AI services are unavailable. You can still edit plans manually, run dry runs and execute approved plans.";

/**
 * Fallback visibility (spec §7.2). Amber when health says backup or an agent run fell back;
 * red when health says down. Never names a provider or model.
 */
export function AiBanner({ status, fellBack = false }: { status: AiStatus | undefined; fellBack?: boolean }) {
  if (status === "down") {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-lg border border-danger/40 bg-danger-subtle p-3 text-sm text-danger-strong">
        <CloudOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>{DOWN_BANNER_TEXT}</p>
      </div>
    );
  }
  if (status === "backup" || fellBack) {
    return (
      <div role="status" className="flex items-start gap-3 rounded-lg border border-warning/40 bg-warning-subtle p-3 text-sm text-warning-strong">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>{BACKUP_BANNER_TEXT}</p>
      </div>
    );
  }
  return null;
}
