import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp, Plus, ShieldCheck, Trash2, Upload } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { api } from "@/api/endpoints";
import type { ImportedField, SchemaImport, SourceSchema } from "@/api/types";
import { AiBanner } from "@/components/app/AiBanner";
import { EmptyState } from "@/components/app/EmptyState";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { StatusBadge } from "@/components/app/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingBlock, TableScroll } from "@/components/ui/misc";
import { useHealth } from "@/hooks/useServerStatus";
import { useAuth } from "@/lib/auth";
import { qk } from "@/lib/queryKeys";
import { cn, formatDateTime, shortHash } from "@/lib/utils";

const MAX_BYTES = 2 * 1024 * 1024;
const ACCEPT = ["image/png", "image/jpeg", "image/webp"];
const TYPES = ["string", "integer", "decimal", "date", "datetime", "boolean", "unknown"];
const SETTLED = new Set(["PROPOSED", "APPROVED", "REJECTED", "FAILED"]);

function compare(fields: ImportedField[], source: SourceSchema | undefined) {
  const src = new Map((source?.fields ?? []).map((f) => [f.name, f.type]));
  const imported = new Map(fields.map((f) => [f.name, f.type]));
  const matched: string[] = [];
  const mismatch: { field: string; expected: string; actual: string }[] = [];
  for (const [name, type] of imported) {
    if (!src.has(name)) continue;
    if (src.get(name) === type) matched.push(name);
    else mismatch.push({ field: name, expected: src.get(name)!, actual: String(type) });
  }
  return {
    matched,
    mismatch,
    missing: [...src.keys()].filter((n) => !imported.has(n)),
    extra: [...imported.keys()].filter((n) => !src.has(n)),
  };
}

export function SchemaImportPage() {
  const { user } = useAuth();
  const health = useHealth();
  const fileId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [importId, setImportId] = useState<number | null>(null);

  const upload = useMutation({
    mutationFn: (f: File) => api.createSchemaImport(f),
    onSuccess: (imp) => {
      setImportId(imp.id);
      toast.success(`Screenshot uploaded (import #${imp.id})`);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 422) setFileError(err.message);
    },
  });
  const current = useQuery({
    queryKey: qk.schemaImport(importId ?? 0),
    queryFn: () => api.schemaImport(importId!),
    enabled: importId !== null,
    refetchInterval: (q) => (q.state.data && !SETTLED.has(q.state.data.status) ? 1000 : false),
  });
  const list = useQuery({ queryKey: qk.schemaImports, queryFn: api.schemaImports, retry: false });
  const items = Array.isArray(list.data) ? list.data : (list.data?.items ?? []);

  const onPick = (f: File | null) => {
    setFileError(null);
    setFile(null);
    if (!f) return;
    if (!ACCEPT.includes(f.type)) return setFileError("Use a PNG, JPG or WebP image.");
    if (f.size > MAX_BYTES) return setFileError("The image must be 2 MB or smaller.");
    setFile(f);
  };
  const isOperator = user?.role === "operator";

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Schema import</h1>
        <p className="text-sm text-muted-foreground">
          Upload a screenshot of a table definition. AI proposes a schema, deterministic checks normalise and flag it, and a human edits and approves what is used. The image is not stored, only its hash.
        </p>
      </div>
      <AiBanner status={undefined} fellBack={!!current.data?.fell_back && health.data?.ai.status !== "backup"} />

      <Card>
        <CardHeader>
          <CardTitle>Upload</CardTitle>
          <CardDescription>PNG, JPG or WebP, 2 MB at most. Text inside the image is treated as data, never as instructions.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (file) upload.mutate(file);
            }}
          >
            <div className="min-w-0 space-y-1.5">
              <Label htmlFor={fileId}>Screenshot</Label>
              <Input
                id={fileId}
                type="file"
                accept={ACCEPT.join(",")}
                aria-invalid={!!fileError}
                aria-describedby={`${fileId}-err`}
                onChange={(e) => onPick(e.target.files?.[0] ?? null)}
                className="h-auto py-1.5"
              />
              {fileError ? (
                <p id={`${fileId}-err`} role="alert" className="text-xs text-danger-strong">
                  {fileError}
                </p>
              ) : null}
            </div>
            <Button type="submit" disabled={!file || !isOperator} loading={upload.isPending}>
              <Upload aria-hidden="true" /> Extract schema
            </Button>
          </form>
          {!isOperator ? <p className="mt-2 text-xs text-muted-foreground">Only the operator role can upload; the approver approves.</p> : null}
          {upload.error && !(upload.error instanceof ApiError && upload.error.status === 422) ? <ErrorBanner className="mt-3" error={upload.error} title="Upload failed" /> : null}
        </CardContent>
      </Card>

      {importId === null ? (
        <Card>
          <CardHeader>
            <CardTitle>Previous imports</CardTitle>
          </CardHeader>
          <CardContent>
            {list.isPending ? (
              <LoadingBlock rows={2} />
            ) : list.isError ? (
              <ErrorBanner error={list.error} onRetry={() => void list.refetch()} title="Could not load imports" />
            ) : items.length === 0 ? (
              <EmptyState icon={ImageUp} message="No schema imports yet. Upload a screenshot to propose a source schema." />
            ) : (
              <ul className="space-y-2">
                {items.map((imp) => (
                  <li key={imp.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <Button variant="link" className="h-auto p-0" onClick={() => setImportId(imp.id)}>
                      Import #{imp.id}
                    </Button>
                    <StatusBadge status={imp.status} />
                    <span className="text-xs text-muted-foreground">
                      {formatDateTime(imp.created_at)} · image {shortHash(imp.image_sha256)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : current.isPending ? (
        <LoadingBlock rows={5} label="Loading import" />
      ) : current.isError ? (
        <ErrorBanner error={current.error} onRetry={() => void current.refetch()} />
      ) : (
        <ImportReview key={`${current.data.id}-${current.data.status}`} imp={current.data} onBack={() => setImportId(null)} />
      )}
    </div>
  );
}

function ImportReview({ imp, onBack }: { imp: SchemaImport; onBack: () => void }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const source = useQuery({ queryKey: qk.sourceSchema, queryFn: api.sourceSchema, staleTime: Infinity });
  const proposal = imp.normalized ?? imp.extracted;
  const [fields, setFields] = useState<ImportedField[]>(proposal?.fields ?? []);
  useEffect(() => setFields(proposal?.fields ?? []), [proposal]);
  const cmp = useMemo(() => compare(fields, source.data), [fields, source.data]);
  const duplicates = useMemo(() => {
    const seen = new Set<string>();
    const dup = new Set<string>();
    for (const f of fields) (seen.has(f.name) ? dup : seen).add(f.name);
    return dup;
  }, [fields]);

  const approve = useMutation({
    mutationFn: () => api.approveSchemaImport(imp.id, { ...(proposal ?? {}), fields }),
    onSuccess: () => {
      toast.success(`Schema import #${imp.id} approved`);
      void qc.invalidateQueries({ queryKey: qk.schemaImports });
    },
  });
  const settled = SETTLED.has(imp.status);
  const editable = imp.status === "PROPOSED";
  const update = (i: number, patch: Partial<ImportedField>) => setFields(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            Import #{imp.id} <StatusBadge status={imp.status} />
          </CardTitle>
          <CardDescription>
            Image {shortHash(imp.image_sha256, 16)} · {formatDateTime(imp.created_at)}
            {imp.engine ? ` · engine ${imp.engine}` : ""}
            {proposal?.table_name ? ` · table ${proposal.table_name}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button variant="outline" size="sm" onClick={onBack}>
            Back to imports
          </Button>
          {!settled ? (
            <LoadingBlock rows={3} label="Extracting the schema" />
          ) : imp.status === "FAILED" ? (
            <div role="alert" className="rounded-md border border-danger/40 bg-danger-subtle p-3 text-sm text-danger-strong">
              <span className="font-mono text-xs">[{imp.error_code ?? "FAILED"}]</span> {imp.error_message ?? "Extraction failed."}
            </div>
          ) : (
            <>
              <TableScroll className="rounded-md border border-border">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Extracted fields (editable)</caption>
                  <thead className="bg-muted text-xs text-muted-foreground">
                    <tr>
                      {["Name", "Type", "Nullable", "Primary key", "Notes", "Confidence", ""].map((h, i) => (
                        <th key={i} scope="col" className="px-3 py-2">
                          {h || <span className="sr-only">Actions</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {fields.map((f, i) => {
                      const review = f.needs_review || (typeof f.confidence === "number" && f.confidence < 0.6) || f.type === "unknown" || duplicates.has(f.name);
                      return (
                        <tr key={i} className={cn("border-t border-border", review && "bg-warning-subtle")}>
                          <td className="px-3 py-2">
                            <Input aria-label={`Field ${i + 1} name`} value={f.name} disabled={!editable} onChange={(e) => update(i, { name: e.target.value })} className="h-8 min-w-[9rem] font-mono text-xs" aria-invalid={duplicates.has(f.name) || undefined} />
                          </td>
                          <td className="px-3 py-2">
                            <NativeSelect aria-label={`Field ${i + 1} type`} value={TYPES.includes(String(f.type)) ? String(f.type) : "unknown"} disabled={!editable} onChange={(e) => update(i, { type: e.target.value })} className="h-8 min-w-[7rem]">
                              {TYPES.map((t) => (
                                <option key={t}>{t}</option>
                              ))}
                            </NativeSelect>
                          </td>
                          <td className="px-3 py-2">
                            <input type="checkbox" aria-label={`Field ${i + 1} nullable`} className="h-4 w-4" checked={!!f.nullable} disabled={!editable} onChange={(e) => update(i, { nullable: e.target.checked })} />
                          </td>
                          <td className="px-3 py-2">
                            <input type="checkbox" aria-label={`Field ${i + 1} primary key`} className="h-4 w-4" checked={!!f.primary_key} disabled={!editable} onChange={(e) => update(i, { primary_key: e.target.checked })} />
                          </td>
                          <td className="px-3 py-2">
                            <Input aria-label={`Field ${i + 1} notes`} value={f.notes ?? ""} disabled={!editable} onChange={(e) => update(i, { notes: e.target.value })} className="h-8 min-w-[10rem]" />
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-xs">
                            {typeof f.confidence === "number" ? f.confidence.toFixed(2) : "-"}
                            {review ? <span className="ml-1 text-warning-strong">needs review</span> : null}
                          </td>
                          <td className="px-3 py-2">
                            <Button variant="ghost" size="icon" aria-label={`Remove field ${f.name}`} disabled={!editable} onClick={() => setFields(fields.filter((_, j) => j !== i))}>
                              <Trash2 aria-hidden="true" />
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </TableScroll>
              {editable ? (
                <Button variant="outline" size="sm" onClick={() => setFields([...fields, { name: "new_field", type: "string", nullable: true, primary_key: false, notes: "", confidence: null }])}>
                  <Plus aria-hidden="true" /> Add field
                </Button>
              ) : null}

              <div className="grid gap-4 lg:grid-cols-2">
                <section className="space-y-2">
                  <h3 className="text-sm font-semibold">Findings</h3>
                  {imp.findings && imp.findings.length ? (
                    <ul className="space-y-1 text-sm">
                      {imp.findings.map((f, i) => (
                        <li key={i} className="rounded-md border border-border p-2">
                          {f.code ? <span className="font-mono text-xs">[{f.code}]</span> : null} {f.field ? <span className="font-mono text-xs">{f.field}</span> : null} {f.message}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">No findings.</p>
                  )}
                  {duplicates.size ? <p className="text-sm text-danger-strong">Duplicate names: {[...duplicates].join(", ")}</p> : null}
                </section>
                <section className="space-y-2" aria-label="Comparison with the provided source schema">
                  <h3 className="text-sm font-semibold">Comparison with the provided source schema</h3>
                  {source.isPending ? (
                    <LoadingBlock rows={2} />
                  ) : (
                    <dl className="space-y-1 text-sm">
                      <div>
                        <dt className="inline font-medium text-success-strong">Matched ({cmp.matched.length}): </dt>
                        <dd className="inline font-mono text-xs">{cmp.matched.join(", ") || "none"}</dd>
                      </div>
                      <div>
                        <dt className="inline font-medium text-danger-strong">Missing ({cmp.missing.length}): </dt>
                        <dd className="inline font-mono text-xs">{cmp.missing.join(", ") || "none"}</dd>
                      </div>
                      <div>
                        <dt className="inline font-medium text-warning-strong">Extra ({cmp.extra.length}): </dt>
                        <dd className="inline font-mono text-xs">{cmp.extra.join(", ") || "none"}</dd>
                      </div>
                      <div>
                        <dt className="inline font-medium text-warning-strong">Type mismatch ({cmp.mismatch.length}): </dt>
                        <dd className="inline font-mono text-xs">{cmp.mismatch.map((m) => `${m.field} (${m.actual} vs ${m.expected})`).join(", ") || "none"}</dd>
                      </div>
                    </dl>
                  )}
                </section>
              </div>

              {editable ? (
                <div className="space-y-2">
                  <Button onClick={() => approve.mutate()} disabled={user?.role !== "approver" || duplicates.size > 0 || fields.length === 0} loading={approve.isPending}>
                    <ShieldCheck aria-hidden="true" /> Approve schema
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    {user?.role !== "approver" ? "Only the approver role can approve." : duplicates.size ? "Fix duplicate field names first." : "Approving stores this edited schema with an audit event."}
                  </p>
                  <ErrorBanner error={approve.error} title="Approval failed" />
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
