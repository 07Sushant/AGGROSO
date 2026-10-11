import { useMutation, useQuery } from "@tanstack/react-query";
import { createColumnHelper } from "@tanstack/react-table";
import { Download, FlaskConical, Repeat, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/endpoints";
import type { DryRunRecord, FieldError } from "@/api/types";
import { COUNT_DEFINITIONS, CountCard } from "@/components/app/CountCard";
import { DataTable } from "@/components/app/DataTable";
import { EmptyState } from "@/components/app/EmptyState";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { StatusBadge } from "@/components/app/StatusBadge";
import { LockedNotice } from "@/components/app/Stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingBlock } from "@/components/ui/misc";
import { useRefreshProject } from "@/hooks/useRefreshProject";
import { useAuth } from "@/lib/auth";
import { qk } from "@/lib/queryKeys";
import { downloadBlob, formatDateTime, formatValue, shortHash } from "@/lib/utils";
import { useWorkspace } from "./context";

export function DryRunStep() {
  const { project, selectedVersion, steps } = useWorkspace();
  const { user } = useAuth();
  const refresh = useRefreshProject(project.id);
  const lock = steps.find((s) => s.id === "dry-run")!;
  const checklist = useQuery({
    queryKey: qk.checklist(selectedVersion?.id ?? 0),
    queryFn: () => api.checklist(selectedVersion!.id),
    enabled: !!selectedVersion,
  });
  const [createdId, setCreatedId] = useState<number | null>(null);
  const dryRunId = createdId ?? checklist.data?.dry_run?.id ?? null;
  const dryRun = useQuery({ queryKey: qk.dryRun(dryRunId ?? 0), queryFn: () => api.dryRun(dryRunId!), enabled: dryRunId !== null });

  const run = useMutation({
    mutationFn: () => api.createDryRun(selectedVersion!.id),
    onSuccess: (d) => {
      setCreatedId(d.id);
      toast.success(`Dry run #${d.id}: ${d.counts.accepted} accepted, ${d.counts.rejected} rejected`);
      refresh();
    },
  });
  const determinism = useMutation({ mutationFn: () => api.determinism(selectedVersion!.id) });

  if (!selectedVersion) return <LockedNotice reason={lock.lockReason} />;
  const isOperator = user?.role === "operator";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4" aria-hidden="true" /> Dry run of v{selectedVersion.version_number}
          </CardTitle>
          <CardDescription>A deterministic, read-only rehearsal. It never touches the target store; its result hash is what approval binds to.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => run.mutate()} disabled={!isOperator} loading={run.isPending}>
              <FlaskConical aria-hidden="true" /> Run dry run
            </Button>
            <Button variant="outline" onClick={() => determinism.mutate()} disabled={!isOperator} loading={determinism.isPending}>
              <Repeat aria-hidden="true" /> Verify determinism
            </Button>
          </div>
          {!isOperator ? <p className="text-xs text-muted-foreground">Only the operator role can run dry runs.</p> : null}
          <ErrorBanner error={run.error} title="Dry run failed" />
          <ErrorBanner error={determinism.error} title="Determinism check failed" />
          {determinism.data ? (
            <div role="status" className="rounded-md border border-border bg-muted p-3 text-sm">
              <p className="flex flex-wrap items-center gap-2">
                <StatusBadge status={determinism.data.deterministic ? "PASS" : "FAIL"} />
                {determinism.data.runs} in-memory runs produced {new Set(determinism.data.hashes).size} distinct hash(es)
                {determinism.data.matches_latest_dry_run === null
                  ? "."
                  : determinism.data.matches_latest_dry_run
                    ? "; matches the stored dry run."
                    : "; does NOT match the stored dry run."}
              </p>
              <p className="mt-1 font-mono text-xs">{determinism.data.hashes.map((h) => shortHash(h, 16)).join("  ")}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {checklist.isPending && !createdId ? (
        <LoadingBlock rows={4} label="Loading dry run" />
      ) : dryRunId === null ? (
        <EmptyState
          icon={FlaskConical}
          message="No dry run for this version yet. Run one to see counts and quarantined records."
          action={
            <Button onClick={() => run.mutate()} disabled={!isOperator} loading={run.isPending}>
              Run dry run
            </Button>
          }
        />
      ) : dryRun.isPending ? (
        <LoadingBlock rows={4} label="Loading dry run" />
      ) : dryRun.isError ? (
        <ErrorBanner error={dryRun.error} onRetry={() => void dryRun.refetch()} />
      ) : (
        <>
          <section aria-label="Dry run counts" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <CountCard label="Source" value={dryRun.data.counts.source} definition={COUNT_DEFINITIONS.source} />
            <CountCard label="Transformed" value={dryRun.data.counts.transformed} definition={COUNT_DEFINITIONS.transformed} tone="info" />
            <CountCard label="Accepted" value={dryRun.data.counts.accepted} definition={COUNT_DEFINITIONS.accepted} tone="success" />
            <CountCard label="Rejected" value={dryRun.data.counts.rejected} definition={COUNT_DEFINITIONS.rejected} tone="danger" />
          </section>
          <p className="text-xs text-muted-foreground">
            Dry run #{dryRun.data.id} · {formatDateTime(dryRun.data.created_at)} · {dryRun.data.duration_ms} ms · result hash{" "}
            <span className="font-mono">{shortHash(dryRun.data.result_hash, 16)}</span> · code {dryRun.data.code_version}
          </p>
          <QuarantineTable dryRunId={dryRun.data.id} />
          <AcceptedPreview dryRunId={dryRun.data.id} />
        </>
      )}
    </div>
  );
}

interface QuarantineRow extends FieldError {
  row_number: number;
  source_key: string | null;
}

const qcol = createColumnHelper<QuarantineRow>();
const quarantineColumns = [
  qcol.accessor("row_number", { header: "Row" }),
  qcol.accessor("source_key", { header: "Source key", cell: (c) => <span className="font-mono text-xs">{c.getValue() ?? "-"}</span> }),
  qcol.accessor("code", { header: "Code", filterFn: "equals", cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> }),
  qcol.accessor((r) => r.target_field ?? "-", { id: "target_field", header: "Target field", filterFn: "equals", cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> }),
  qcol.accessor((r) => (r.source_fields ?? []).join(", "), { id: "source_fields", header: "Source fields" }),
  qcol.accessor((r) => formatValue(r.source_value), { id: "source_value", header: "Source value", cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> }),
  qcol.accessor((r) => r.transform ?? r.rule ?? "-", { id: "rule", header: "Transform / rule" }),
  qcol.accessor("stage", { header: "Stage" }),
  qcol.accessor("message", { header: "Message", cell: (c) => <span className="text-xs">{c.getValue()}</span> }),
];

function QuarantineTable({ dryRunId }: { dryRunId: number }) {
  const records = useQuery({ queryKey: qk.dryRunRecords(dryRunId, "REJECTED"), queryFn: () => api.dryRunRecords(dryRunId, { outcome: "REJECTED" }) });
  const [code, setCode] = useState("");
  const [field, setField] = useState("");
  const exportFile = useMutation({
    mutationFn: async (format: "csv" | "json") => {
      const res = await api.exportDryRun(dryRunId, format);
      downloadBlob(await res.blob(), `dry-run-${dryRunId}-quarantine.${format}`);
    },
    onSuccess: () => toast.success("Export downloaded"),
  });

  const rows = useMemo<QuarantineRow[]>(
    () => (records.data?.items ?? []).flatMap((r) => r.errors.map((e) => ({ ...e, row_number: r.row_number, source_key: r.source_key }))),
    [records.data],
  );
  const codes = useMemo(() => [...new Set(rows.map((r) => r.code))].sort(), [rows]);
  const fields = useMemo(() => [...new Set(rows.map((r) => r.target_field ?? "-"))].sort(), [rows]);
  const filters = useMemo(
    () => [...(code ? [{ id: "code", value: code }] : []), ...(field ? [{ id: "target_field", value: field }] : [])],
    [code, field],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-danger" aria-hidden="true" /> Quarantine
        </CardTitle>
        <CardDescription>Field-level evidence for every rejected record.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="q-code">Error code</Label>
            <NativeSelect id="q-code" value={code} onChange={(e) => setCode(e.target.value)} className="w-56">
              <option value="">All codes</option>
              {codes.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="space-y-1">
            <Label htmlFor="q-field">Target field</Label>
            <NativeSelect id="q-field" value={field} onChange={(e) => setField(e.target.value)} className="w-48">
              <option value="">All fields</option>
              {fields.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" size="sm" onClick={() => exportFile.mutate("csv")} loading={exportFile.isPending && exportFile.variables === "csv"}>
              <Download aria-hidden="true" /> CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportFile.mutate("json")} loading={exportFile.isPending && exportFile.variables === "json"}>
              <Download aria-hidden="true" /> JSON
            </Button>
          </div>
        </div>
        <ErrorBanner error={exportFile.error} title="Export failed" />
        {records.isPending ? (
          <LoadingBlock rows={5} label="Loading quarantined records" />
        ) : records.isError ? (
          <ErrorBanner error={records.error} onRetry={() => void records.refetch()} />
        ) : (
          <DataTable columns={quarantineColumns} data={rows} caption="Quarantined records" columnFilters={filters} emptyMessage="No quarantined records." />
        )}
      </CardContent>
    </Card>
  );
}

function AcceptedPreview({ dryRunId }: { dryRunId: number }) {
  const records = useQuery({
    queryKey: qk.dryRunRecords(dryRunId, "ACCEPTED"),
    queryFn: () => api.dryRunRecords(dryRunId, { outcome: "ACCEPTED", limit: 20 }),
  });
  const cols = useMemo(() => {
    const first = records.data?.items[0]?.transformed;
    const keys = first ? Object.keys(first) : [];
    const h = createColumnHelper<DryRunRecord>();
    return [
      h.accessor("row_number", { header: "Row" }),
      ...keys.map((k) =>
        h.accessor((r) => formatValue(r.transformed?.[k]), { id: k, header: k, cell: (c) => <span className="whitespace-nowrap font-mono text-xs">{c.getValue()}</span> }),
      ),
    ];
  }, [records.data]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Transformed preview</CardTitle>
        <CardDescription>The first accepted records as they would be written to the target.</CardDescription>
      </CardHeader>
      <CardContent>
        {records.isPending ? (
          <LoadingBlock rows={4} />
        ) : records.isError ? (
          <ErrorBanner error={records.error} onRetry={() => void records.refetch()} />
        ) : (
          <DataTable columns={cols} data={records.data.items} caption="Transformed preview" pageSize={10} emptyMessage="No accepted records." />
        )}
      </CardContent>
    </Card>
  );
}
