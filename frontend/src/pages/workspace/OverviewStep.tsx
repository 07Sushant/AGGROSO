import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/endpoints";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { StatusBadge } from "@/components/app/StatusBadge";
import { Skeleton } from "@/components/ui/misc";
import { bucketize } from "@/lib/plan";
import { qk } from "@/lib/queryKeys";
import { cn, shortHash } from "@/lib/utils";
import { EventLine } from "./HistoryStep";
import { useWorkspace } from "./context";

function Tile({ title, className, children, cta, to, loading, error }: { title: string; className?: string; children: ReactNode; cta: string; to: string; loading?: boolean; error?: unknown }) {
  return (
    <section className={cn("flex min-w-0 flex-col rounded-lg border border-border bg-surface p-5 shadow-sm", className)} aria-label={title}>
      <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h2>
      <div className="mt-2 flex-1">{loading ? <Skeleton className="h-16 w-full" /> : error ? <ErrorBanner error={error} /> : children}</div>
      <Link to={to} className="mt-3 inline-flex items-center gap-1 self-start text-sm font-medium text-primary hover:underline">
        {cta} <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
      </Link>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number | string | undefined }) {
  return (
    <div>
      <p className="text-xl font-semibold tabular-nums">{value ?? "-"}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

/** Bento overview (spec §8.0): 4-column grid; each tile links to its step. */
export function OverviewStep() {
  const { project, selectedVersion } = useWorkspace();
  const base = `/projects/${project.id}`;
  const latest = project.latest_version;
  const dryRun = useQuery({ queryKey: qk.dryRun(project.latest_dry_run_id ?? 0), queryFn: () => api.dryRun(project.latest_dry_run_id!), enabled: !!project.latest_dry_run_id });
  const version = useQuery({ queryKey: qk.planVersion(latest?.id ?? 0), queryFn: () => api.planVersion(latest!.id), enabled: !!latest });
  const target = useQuery({ queryKey: qk.targetSchema, queryFn: api.targetSchema, staleTime: Infinity });
  const checklist = useQuery({ queryKey: qk.checklist(selectedVersion?.id ?? 0), queryFn: () => api.checklist(selectedVersion!.id), enabled: !!selectedVersion });
  const history = useQuery({ queryKey: qk.history(project.id), queryFn: () => api.history(project.id) });
  const lastRun = history.data?.runs[0];
  const recon = useQuery({ queryKey: qk.reconciliation(lastRun?.id ?? 0), queryFn: () => api.reconciliation(lastRun!.id), enabled: !!lastRun });
  const buckets = version.data?.plan ? bucketize(version.data.plan, target.data) : null;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      <Tile title="Current version" className="md:col-span-2" cta={latest ? "Review the plan" : "Create a plan"} to={`${base}/plan`}>
        {latest ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xl font-semibold">v{latest.version_number}</p>
            <StatusBadge status={latest.status} />
            <p className="text-sm text-muted-foreground">
              {project.version_count} version(s){project.approved_version ? ` · v${project.approved_version.version_number} approved` : " · none approved"}
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No plan yet. Run the agent or load the reference plan.</p>
        )}
      </Tile>

      <Tile title="Last dry run" className="md:col-span-2" cta={project.latest_dry_run_id ? "Open dry run" : "Run a dry run"} to={`${base}/dry-run`} loading={dryRun.isLoading} error={dryRun.error}>
        {dryRun.data ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Source" value={dryRun.data.counts.source} />
            <Stat label="Transformed" value={dryRun.data.counts.transformed} />
            <Stat label="Accepted" value={dryRun.data.counts.accepted} />
            <Stat label="Rejected" value={dryRun.data.counts.rejected} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No dry run of the latest version yet.</p>
        )}
      </Tile>

      <Tile title="Proposal buckets" cta="Open the agent" to={`${base}/agent`} loading={version.isLoading} error={version.error}>
        {buckets ? (
          <ul className="space-y-1 text-sm">
            <li>Confident: {buckets.confident.length}</li>
            <li>Needs review: {buckets.needsReview.length}</li>
            <li>Missing: {buckets.missing.length}</li>
            <li>Incompatible: {buckets.incompatible.length}</li>
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No proposal yet.</p>
        )}
      </Tile>

      <Tile title="Approval checklist" cta="Open approval" to={`${base}/approve`} loading={checklist.isLoading} error={checklist.error}>
        {checklist.data ? (
          <div>
            <p className="text-xl font-semibold tabular-nums">
              {checklist.data.items.filter((i) => i.ok).length}/{checklist.data.items.length}
            </p>
            <p className="text-xs text-muted-foreground">
              checks pass for v{selectedVersion?.version_number}
              {checklist.data.blockers.length ? ` · ${checklist.data.blockers.length} blocking` : ""}
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Needs a plan version.</p>
        )}
      </Tile>

      <Tile title="Last run" className="md:col-span-2 xl:order-last" cta={lastRun ? "Open execution" : "Go to execute"} to={`${base}/execute`} loading={history.isLoading} error={history.error}>
        {lastRun ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium">Run #{lastRun.id}</span>
            <StatusBadge status={lastRun.status} />
            <span className="tabular-nums">
              {lastRun.inserted} inserted · {lastRun.skipped_existing} skipped · {lastRun.quarantined} quarantined
            </span>
            {recon.data ? (
              <span className="flex items-center gap-1">
                Reconciliation <StatusBadge status={recon.data.status} />
              </span>
            ) : null}
            <span className="font-mono text-xs text-muted-foreground">key {shortHash(lastRun.idempotency_key, 14)}</span>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Nothing executed yet.</p>
        )}
      </Tile>

      <Tile title="Recent history" className="md:col-span-2 xl:row-span-2" cta="Full history" to={`${base}/history`} loading={history.isLoading} error={history.error}>
        {history.data && history.data.events.length ? (
          <ol className="space-y-2 border-l border-border pl-3">
            {history.data.events.slice(0, 5).map((e) => (
              <EventLine key={e.id} e={e} compact />
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">No events yet.</p>
        )}
      </Tile>
    </div>
  );
}
