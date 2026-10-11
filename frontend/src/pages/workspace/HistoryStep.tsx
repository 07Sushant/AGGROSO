import { useQuery } from "@tanstack/react-query";
import { Bot, ChevronRight, Database, FileJson, FlaskConical, History as HistoryIcon, Scale, ShieldCheck, Undo2, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/endpoints";
import type { AuditEvent } from "@/api/types";
import { AgentTrace, traceOf } from "@/components/app/AgentTrace";
import { EmptyState } from "@/components/app/EmptyState";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { JsonViewer } from "@/components/app/JsonViewer";
import { StatusBadge } from "@/components/app/StatusBadge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingBlock } from "@/components/ui/misc";
import { qk } from "@/lib/queryKeys";
import { cn, formatDateTime } from "@/lib/utils";
import { useWorkspace } from "./context";

const ENTITY_ICON: Record<string, LucideIcon> = {
  project: Database,
  plan_version: FileJson,
  dry_run: FlaskConical,
  run: Database,
  agent_run: Bot,
};

function eventIcon(e: AuditEvent): LucideIcon {
  if (e.action.startsWith("rollback")) return Undo2;
  if (e.action.startsWith("reconciliation")) return Scale;
  if (e.action.includes("approved") || e.action.includes("rejected") || e.action.includes("revoked")) return ShieldCheck;
  return ENTITY_ICON[e.entity_type] ?? HistoryIcon;
}

export function EventLine({ e, compact = false }: { e: AuditEvent; compact?: boolean }) {
  const Icon = eventIcon(e);
  const selfApproved = e.details?.self_approved === true;
  const failed = e.action.includes("failed") || e.details?.status === "FAIL";
  return (
    <li className="relative pl-6">
      <span className={cn("absolute left-0 top-0.5 flex h-4 w-4 items-center justify-center rounded-full border bg-surface", failed ? "border-danger text-danger" : "border-border")}>
        <Icon className="h-2.5 w-2.5" aria-hidden="true" />
      </span>
      <p className="flex flex-wrap items-center gap-x-2 text-sm">
        <span className="font-mono text-xs font-medium">{e.action}</span>
        {typeof e.details?.status === "string" && ["PASS", "FAIL"].includes(e.details.status as string) ? <StatusBadge status={e.details.status as string} /> : null}
        {selfApproved ? <span className="rounded-full border border-warning/40 bg-warning-subtle px-2 text-xs text-warning-strong">self-approved</span> : null}
        <span className="text-xs text-muted-foreground">
          {e.actor ?? "system"} · {formatDateTime(e.created_at)}
        </span>
      </p>
      {!compact ? (
        <details className="mt-1">
          <summary className="flex cursor-pointer items-center gap-1 text-xs text-muted-foreground">
            <ChevronRight className="h-3 w-3" aria-hidden="true" /> {e.entity_type} #{e.entity_id} details
          </summary>
          <div className="mt-1 space-y-1">
            {e.request_id ? (
              <p className="text-xs">
                Request{" "}
                <Link className="font-mono text-primary hover:underline" to={`/logs?request_id=${encodeURIComponent(e.request_id)}`}>
                  {e.request_id}
                </Link>
              </p>
            ) : null}
            <JsonViewer value={e.details} maxHeight="12rem" />
          </div>
        </details>
      ) : null}
    </li>
  );
}

function AgentRunItem({ id, label }: { id: number; label: ReactNode }) {
  const [open, setOpen] = useState(false);
  const run = useQuery({ queryKey: qk.agentRun(id), queryFn: () => api.agentRun(id), enabled: open });
  return (
    <li className="rounded-md border border-border p-2">
      <button type="button" aria-expanded={open} className="flex w-full flex-wrap items-center gap-2 text-left text-sm" onClick={() => setOpen(!open)}>
        <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")} aria-hidden="true" />
        {label}
      </button>
      {open ? (
        <div className="mt-2">
          {run.isPending ? <LoadingBlock rows={2} /> : run.isError ? <ErrorBanner error={run.error} /> : <AgentTrace steps={traceOf(run.data)} />}
        </div>
      ) : null}
    </li>
  );
}

export function HistoryStep() {
  const { project } = useWorkspace();
  const history = useQuery({ queryKey: qk.history(project.id), queryFn: () => api.history(project.id) });

  if (history.isPending) return <LoadingBlock rows={6} label="Loading history" />;
  if (history.isError) return <ErrorBanner error={history.error} onRetry={() => void history.refetch()} title="Could not load history" />;
  const h = history.data;

  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card className="xl:col-span-2">
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
          <CardDescription>Append-only audit trail (newest first). Every approval, run, attempt, retry, rollback, agent run and reconciliation.</CardDescription>
        </CardHeader>
        <CardContent>
          {h.events.length === 0 ? (
            <EmptyState icon={HistoryIcon} message="No events yet. Actions in this project appear here." />
          ) : (
            <ol className="space-y-3 border-l border-border pl-3">
              {h.events.map((e) => (
                <EventLine key={e.id} e={e} />
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Approvals</CardTitle>
          </CardHeader>
          <CardContent>
            {h.approvals.length === 0 ? <p className="text-sm text-muted-foreground">No decisions yet.</p> : null}
            <ul className="space-y-2">
              {h.approvals.map((a) => (
                <li key={a.id} className="rounded-md border border-border p-2 text-sm">
                  <p className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={a.decision} /> version #{a.plan_version_id}
                    {a.self_approved ? <span className="rounded-full border border-warning/40 bg-warning-subtle px-2 text-xs text-warning-strong">self-approved</span> : null}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {a.actor} · {formatDateTime(a.created_at)}
                    {a.comment ? ` · "${a.comment}"` : ""}
                  </p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Runs, attempts and rollbacks</CardTitle>
          </CardHeader>
          <CardContent>
            {h.runs.length === 0 ? <p className="text-sm text-muted-foreground">No runs yet.</p> : null}
            <ul className="space-y-2">
              {h.runs.map((r) => {
                const rb = h.rollbacks.find((x) => x.run_id === r.id);
                return (
                  <li key={r.id} className="rounded-md border border-border p-2 text-sm">
                    <p className="flex flex-wrap items-center gap-2">
                      Run #{r.id} <StatusBadge status={r.status} />
                    </p>
                    <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                      {r.attempts.map((a) => (
                        <li key={a.id}>
                          Attempt {a.attempt_number} ({a.kind}): {a.status} · +{a.inserted} inserted{a.error_code ? ` · ${a.error_code}` : ""}
                        </li>
                      ))}
                      {rb ? (
                        <li>
                          Rolled back by {rb.actor}: {rb.deleted_count} rows deleted · "{rb.reason}"
                        </li>
                      ) : null}
                    </ul>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Agent runs</CardTitle>
          </CardHeader>
          <CardContent>
            {h.agent_runs.length === 0 ? <p className="text-sm text-muted-foreground">No agent runs yet.</p> : null}
            <ul className="space-y-2">
              {h.agent_runs.map((a) => (
                <AgentRunItem
                  key={a.id}
                  id={a.id}
                  label={
                    <>
                      Agent run #{a.id} <StatusBadge status={a.status} />
                      <span className="text-xs text-muted-foreground">
                        {a.kind}
                        {a.engine ? ` · ${a.engine}` : ""}
                        {a.fell_back ? " · fell back to backup" : ""}
                      </span>
                    </>
                  }
                />
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
