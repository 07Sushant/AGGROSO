import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { ApprovalChecklist } from "@/api/types";
import { cn } from "@/lib/utils";

/** Server-enforced checklist (spec §6.4) with live ticks; non-blocking items show as warnings. */
export function ApprovalChecklistView({ checklist }: { checklist: ApprovalChecklist }) {
  const done = checklist.items.filter((i) => i.ok).length;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground" aria-live="polite">
        {done} of {checklist.items.length} checks pass
        {checklist.blockers.length ? ` · ${checklist.blockers.length} blocking` : " · ready to approve"}
      </p>
      <ul className="space-y-2" aria-label="Approval checklist">
        {checklist.items.map((item) => {
          const warn = !item.ok && !item.blocking;
          const Icon = item.ok ? CheckCircle2 : warn ? AlertTriangle : XCircle;
          return (
            <li
              key={item.id}
              data-testid={`check-${item.id}`}
              className={cn(
                "flex items-start gap-2 rounded-md border p-2 text-sm",
                item.ok ? "border-border" : warn ? "border-warning/40 bg-warning-subtle" : "border-danger/30 bg-danger-subtle",
              )}
            >
              <Icon
                className={cn("mt-0.5 h-4 w-4 shrink-0", item.ok ? "text-success" : warn ? "text-warning" : "text-danger")}
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="font-medium">
                  {item.label}{" "}
                  <span className="sr-only">{item.ok ? "(passed)" : warn ? "(warning)" : "(blocking)"}</span>
                  {!item.ok ? (
                    <span className={cn("ml-1 text-xs font-normal", warn ? "text-warning-strong" : "text-danger-strong")}>
                      {warn ? "Warning" : "Blocking"}
                    </span>
                  ) : null}
                </p>
                {item.detail ? <p className={cn("text-xs", warn ? "text-warning-strong" : "text-danger-strong")}>{item.detail}</p> : null}
              </div>
            </li>
          );
        })}
      </ul>
      {checklist.self_approval ? (
        <p role="alert" className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning-subtle p-2 text-sm text-warning-strong">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          Self-approval: you edited this version. You can still approve; it will be recorded as self-approved in the audit log.
        </p>
      ) : null}
    </div>
  );
}
