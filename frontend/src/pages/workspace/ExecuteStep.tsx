import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { createColumnHelper } from "@tanstack/react-table";
import { Database, RefreshCw, RotateCw, Scale, Undo2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/endpoints";
import type { MigrationRun, Reconciliation, RunResult, TargetRecord } from "@/api/types";
import { ConfirmDialog } from "@/components/app/ConfirmDialog";
import { COUNT_DEFINITIONS, CountCard } from "@/components/app/CountCard";
import { DataTable } from "@/components/app/DataTable";
import { EmptyState } from "@/components/app/EmptyState";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { ExecutePanel } from "@/components/app/ExecutePanel";
import { StatusBadge } from "@/components/app/StatusBadge";
import { LockedNotice } from "@/components/app/Stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingBlock, TableScroll } from "@/components/ui/misc";
import { useConfig } from "@/hooks/useServerStatus";
import { useRefreshProject } from "@/hooks/useRefreshProject";
import { useAuth } from "@/lib/auth";
import { qk } from "@/lib/queryKeys";
import { formatDateTime, formatValue } from "@/lib/utils";
import { useWorkspace } from "./context";

const ACTIVE_RUN = new Set(["RUNNING", "ROLLING_BACK"]);

export function ExecuteStep() {
  const { project, selectedVersion, steps } = useWorkspace();
  const { user } = useAuth();
  const config = useConfig();
  const qc = useQueryClient();
  const refresh = useRefreshProject(project.id);
  const lock = steps.find((s) => s.id === "execute")!;
  const history = useQuery({ queryKey: qk.history(project.id), queryFn: () => api.history(project.id) });
  const [runId, setRunId] = useState<number | null>(null);
  const currentRunId = runId ?? project.active_run?.id ?? history.data?.runs[0]?.id ?? null;

  const afterRunChange = (run: MigrationRun) => {
    qc.setQueryData(qk.run(run.id), run);
    if (run.reconciliation) qc.setQueryData(qk.reconciliation(run.id), run.reconciliation);
    void qc.invalidateQueries({ queryKey: ["runs", run.id] });
    void qc.invalidateQueries({ queryKey: ["projects", project.id, "target-records"] });
    refresh();
  };

  const execute = useMutation({
    mutationFn: ({ key, failAfter }: { key: string; failAfter: number | null }) => api.execute(project.approved_version!.id, key, failAfter),
    onSuccess: (run) => {
      setRunId(run.id);
      afterRunChange(run);
      if (run.replayed) toast.info(`Same request replayed: run #${run.id} (no new work)`);
      else if (run.status === "FAILED") toast.error(`Run #${run.id} failed: ${run.last_error?.code ?? "error"}. Retry is available.`);
      else toast.success(`Run #${run.id} completed: ${run.inserted} inserted`);
    },
  });

  const approvedVersion = project.approved_version
    ? { id: project.approved_version.id, version_number: project.approved_version.version_number, status: "APPROVED" as const }
    : selectedVersion
      ? { id: selectedVersion.id, version_number: selectedVersion.version_number, status: selectedVersion.status }
      : null;

  return (
    <div className="space-y-4">
      <LockedNotice reason={lock.lockReason} />
      <ExecutePanel
        version={approvedVersion}
        isOperator={user?.role === "operator"}
        activeRun={project.active_run}
        faultInjectionEnabled={!!config.data?.fault_injection_enabled}
        pending={execute.isPending}
        error={<ErrorBanner error={execute.error} title="Execute failed" />}
        onExecute={(key, failAfter) => execute.mutate({ key, failAfter })}
      />
      {currentRunId === null ? (
        history.isPending ? (
          <LoadingBlock rows={3} label="Loading runs" />
        ) : (
          <EmptyState icon={Database} message="Nothing has been executed for this project yet. Execute the approved version to load the target store." />
        )
      ) : (
        <RunDetail runId={currentRunId} onChanged={afterRunChange} />
      )}
    </div>
  );
}

function RunDetail({ runId, onChanged }: { runId: number; onChanged: (r: MigrationRun) => void }) {
  const { user } = useAuth();
  const [rollbackOpen, setRollbackOpen] = useState(false);
  const run = useQuery({
    queryKey: qk.run(runId),
    queryFn: () => api.run(runId),
    refetchInterval: (q) => (q.state.data && ACTIVE_RUN.has(q.state.data.status) ? 1000 : false),
  });
  const recon = useQuery({ queryKey: qk.reconciliation(runId), queryFn: () => api.reconciliation(runId) });

  const retry = useMutation({
    mutationFn: () => api.retry(runId),
    onSuccess: (r) => {
      onChanged(r);
      if (r.status === "COMPLETED") toast.success(`Retry completed run #${r.id}: ${r.inserted} inserted in total`);
      else toast.error(`Retry failed: ${r.last_error?.code ?? "error"}`);
    },
  });
  const rollback = useMutation({
    mutationFn: (reason: string) => api.rollback(runId, reason),
    onSuccess: (r) => {
      setRollbackOpen(false);
      onChanged(r);
      toast.success(`Run #${r.id} rolled back: ${r.rollback?.deleted_count ?? 0} target rows deleted`);
    },
  });

  if (run.isPending) return <LoadingBlock rows={5} label="Loading run" />;
  if (run.isError) return <ErrorBanner error={run.error} onRetry={() => void run.refetch()} title="Could not load the run" />;
  const r = run.data;
  const isOperator = user?.role === "operator";
  const isApprover = user?.role === "approver";
  const t = recon.data?.totals;
  const canRollback = r.status === "COMPLETED" || r.status === "FAILED";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            Run #{r.id} <StatusBadge status={r.status} />
            {r.replayed ? <span className="text-xs font-normal text-muted-foreground">(replayed)</span> : null}
          </CardTitle>
          <CardDescription>
            Plan version #{r.plan_version_id} · approval #{r.approval_id} · started {formatDateTime(r.created_at)}
            {r.finished_at ? ` · finished ${formatDateTime(r.finished_at)}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div aria-live="polite" className="sr-only">
            Run {r.id} is {r.status}
          </div>
          {r.status === "FAILED" && r.last_error ? (
            <div role="alert" className="rounded-md border border-danger/40 bg-danger-subtle p-3 text-sm text-danger-strong">
              <span className="font-mono text-xs">[{r.last_error.code}]</span> {r.last_error.message}. Committed chunks are kept; Retry processes only the remaining records.
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {r.status === "FAILED" ? (
              <Button onClick={() => retry.mutate()} disabled={!isOperator} loading={retry.isPending}>
                <RotateCw aria-hidden="true" /> Retry
              </Button>
            ) : null}
            <Button variant="destructive" onClick={() => setRollbackOpen(true)} disabled={!isApprover || !canRollback}>
              <Undo2 aria-hidden="true" /> Rollback
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {r.status === "FAILED" && !isOperator ? "Only the operator role can retry. " : ""}
            {!canRollback ? `Rollback is possible for COMPLETED or FAILED runs; this run is ${r.status}.` : !isApprover ? "Only the approver role can roll back." : "Rollback deletes only the rows this run inserted."}
          </p>
          <ErrorBanner error={retry.error} title="Retry failed" />

          <section aria-label="Run counts" className="space-y-2">
            <h3 className="text-sm font-semibold">Approved dry run</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <CountCard label="Source" value={t?.source} definition={COUNT_DEFINITIONS.source} />
              <CountCard label="Transformed" value={t?.transformed} definition={COUNT_DEFINITIONS.transformed} tone="info" />
              <CountCard label="Accepted" value={t?.accepted} definition={COUNT_DEFINITIONS.accepted} tone="success" />
              <CountCard label="Rejected" value={t?.rejected} definition={COUNT_DEFINITIONS.rejected} tone="danger" />
            </div>
            <h3 className="pt-2 text-sm font-semibold">This run</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <CountCard label="Inserted" value={r.inserted} definition={COUNT_DEFINITIONS.inserted} tone="success" />
              <CountCard label="Skipped existing" value={r.skipped_existing} definition={COUNT_DEFINITIONS.skipped} />
              <CountCard label="Quarantined (execute)" value={r.quarantined} definition={COUNT_DEFINITIONS.quarantined} tone="danger" />
              <CountCard label="Target rows" value={t?.target_rows} definition={COUNT_DEFINITIONS.target} tone="info" />
            </div>
          </section>

          <section aria-label="Attempts" className="space-y-2">
            <h3 className="text-sm font-semibold">Attempts</h3>
            <TableScroll className="rounded-md border border-border">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Run attempts</caption>
                <thead className="bg-muted text-xs text-muted-foreground">
                  <tr>
                    {["#", "Kind", "Status", "Inserted", "Skipped", "Quarantined", "Error", "Finished"].map((h) => (
                      <th key={h} scope="col" className="px-3 py-2">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.attempts.map((a) => (
                    <tr key={a.id} className="border-t border-border">
                      <td className="px-3 py-2">{a.attempt_number}</td>
                      <td className="px-3 py-2">{a.kind}</td>
                      <td className="px-3 py-2">
                        <StatusBadge status={a.status} />
                      </td>
                      <td className="px-3 py-2 tabular-nums">{a.inserted}</td>
                      <td className="px-3 py-2 tabular-nums">{a.skipped_existing}</td>
                      <td className="px-3 py-2 tabular-nums">{a.quarantined}</td>
                      <td className="px-3 py-2 font-mono text-xs">{a.error_code ?? "-"}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs">{formatDateTime(a.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
          </section>
        </CardContent>
      </Card>

      <ReconciliationPanel query={recon} />
      <ExecuteResults runId={r.id} />
      <TargetRecords projectId={r.project_id} runId={r.id} />

      <ConfirmDialog
        open={rollbackOpen}
        onOpenChange={setRollbackOpen}
        title={`Roll back run #${r.id}?`}
        description="Deletes every target row this run inserted, in one transaction, then re-runs reconciliation (it should report 0 target rows). A rollback cannot be undone."
        confirmLabel="Roll back run"
        typeToConfirm={String(r.id)}
        loading={rollback.isPending}
        error={<ErrorBanner error={rollback.error} />}
        onConfirm={(reason) => rollback.mutate(reason)}
      />
    </div>
  );
}

function ReconciliationPanel({ query }: { query: UseQueryResult<Reconciliation> }) {
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Scale className="h-4 w-4" aria-hidden="true" /> Reconciliation {query.data ? <StatusBadge status={query.data.status} /> : null}
          </CardTitle>
          <CardDescription>Read-only comparison of the approved dry run, the run ledger and the target rows (counts, key sets and row hashes).</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()} loading={query.isFetching}>
          <RefreshCw aria-hidden="true" /> Reconcile now
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {query.isPending ? (
          <LoadingBlock rows={4} label="Loading reconciliation" />
        ) : query.isError ? (
          <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <>
            <ul className="grid gap-2 md:grid-cols-2" aria-label="Invariants">
              {query.data.invariants.map((inv) => (
                <li key={inv.id} className="flex items-start gap-2 rounded-md border border-border p-2 text-sm">
                  <StatusBadge status={inv.ok ? "PASS" : "FAIL"} />
                  <span>
                    <span className="font-mono text-xs">{inv.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      expected {formatValue(inv.expected)}, actual {formatValue(inv.actual)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            {query.data.discrepancies.length ? (
              <div role="alert" className="rounded-md border border-danger/40 bg-danger-subtle p-3 text-sm text-danger-strong">
                <p className="font-medium">Discrepancies</p>
                <ul className="list-disc pl-5">
                  {query.data.discrepancies.map((d, i) => (
                    <li key={i}>
                      <span className="font-mono text-xs">{d.code}</span>: {d.message}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-sm text-success-strong">No discrepancies.</p>
            )}
            {query.data.missing_in_target.length || query.data.unexpected_in_target.length ? (
              <div className="grid gap-2 text-sm md:grid-cols-2">
                <p>
                  Missing in target: <span className="font-mono text-xs">{query.data.missing_in_target.join(", ") || "none"}</span>
                </p>
                <p>
                  Unexpected in target: <span className="font-mono text-xs">{query.data.unexpected_in_target.join(", ") || "none"}</span>
                </p>
              </div>
            ) : null}
            {query.data.value_mismatches.length ? (
              <TableScroll className="rounded-md border border-border">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Value mismatches</caption>
                  <thead className="bg-muted text-xs text-muted-foreground">
                    <tr>
                      <th scope="col" className="px-3 py-2">Legacy id</th>
                      <th scope="col" className="px-3 py-2">Field</th>
                      <th scope="col" className="px-3 py-2">Expected (dry run)</th>
                      <th scope="col" className="px-3 py-2">Actual (target)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {query.data.value_mismatches.map((m, i) => (
                      <tr key={i} className="border-t border-border font-mono text-xs">
                        <td className="px-3 py-2">{m.legacy_id}</td>
                        <td className="px-3 py-2">{m.field}</td>
                        <td className="px-3 py-2">{formatValue(m.expected)}</td>
                        <td className="px-3 py-2 text-danger-strong">{formatValue(m.actual)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

const rcol = createColumnHelper<RunResult>();
const resultColumns = [
  rcol.accessor("row_number", { header: "Row" }),
  rcol.accessor("legacy_id", { header: "Legacy id", cell: (c) => <span className="font-mono text-xs">{c.getValue() ?? "-"}</span> }),
  rcol.accessor("outcome", { header: "Outcome", cell: (c) => <StatusBadge status={c.getValue()} /> }),
  rcol.accessor("attempt_number", { header: "Attempt" }),
  rcol.accessor((r) => r.errors.map((e) => `${e.code}: ${e.message}`).join("; ") || "-", { id: "errors", header: "Evidence", cell: (c) => <span className="text-xs">{c.getValue()}</span> }),
];

function ExecuteResults({ runId }: { runId: number }) {
  const results = useQuery({ queryKey: qk.runResults(runId), queryFn: () => api.runResults(runId) });
  const notInserted = useMemo(() => (results.data?.items ?? []).filter((r) => r.outcome !== "INSERTED"), [results.data]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Execute-stage outcomes</CardTitle>
        <CardDescription>Records skipped because they already exist, or quarantined by a target constraint, with evidence.</CardDescription>
      </CardHeader>
      <CardContent>
        {results.isPending ? (
          <LoadingBlock rows={3} />
        ) : results.isError ? (
          <ErrorBanner error={results.error} onRetry={() => void results.refetch()} />
        ) : (
          <DataTable columns={resultColumns} data={notInserted} caption="Skipped and quarantined records" pageSize={10} emptyMessage="Every processed record was inserted." />
        )}
      </CardContent>
    </Card>
  );
}

function TargetRecords({ projectId, runId }: { projectId: number; runId: number }) {
  const records = useQuery({ queryKey: qk.targetRecords(projectId, runId, 0), queryFn: () => api.targetRecords(projectId, runId, 500, 0) });
  const cols = useMemo(() => {
    const first = records.data?.items[0];
    const keys = first ? Object.keys(first).filter((k) => !["row_hash", "loaded_at", "migration_run_id"].includes(k)) : [];
    const h = createColumnHelper<TargetRecord>();
    return keys.map((k) => h.accessor((r) => formatValue(r[k]), { id: k, header: k, cell: (c) => <span className="whitespace-nowrap font-mono text-xs">{c.getValue()}</span> }));
  }, [records.data]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Target records</CardTitle>
        <CardDescription>Rows in the mock target store attributed to this run{records.data ? ` (${records.data.total})` : ""}.</CardDescription>
      </CardHeader>
      <CardContent>
        {records.isPending ? (
          <LoadingBlock rows={4} />
        ) : records.isError ? (
          <ErrorBanner error={records.error} onRetry={() => void records.refetch()} />
        ) : records.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No target rows for this run (it was rolled back or has not inserted anything).</p>
        ) : (
          <DataTable columns={cols} data={records.data.items} caption="Target records" pageSize={10} />
        )}
      </CardContent>
    </Card>
  );
}
