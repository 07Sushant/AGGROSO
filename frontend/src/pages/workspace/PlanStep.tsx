import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpenCheck, FileJson, GitCompare, ListChecks, Sparkles } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { api } from "@/api/endpoints";
import type { PlanMapping, PlanValidationResult, PlanVersion, Plan } from "@/api/types";
import { EmptyState } from "@/components/app/EmptyState";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { DiffView, MappingBuckets, PlanExtras, SeverityBadge } from "@/components/app/PlanViews";
import { StatusBadge } from "@/components/app/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingBlock, TableScroll } from "@/components/ui/misc";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useRefreshProject } from "@/hooks/useRefreshProject";
import { useAuth } from "@/lib/auth";
import { allRisks } from "@/lib/plan";
import { qk } from "@/lib/queryKeys";
import { cn, formatDateTime, shortHash } from "@/lib/utils";
import { useWorkspace } from "./context";

export function PlanStep() {
  const { project, versions, selectedVersion, selectVersion } = useWorkspace();
  const { user } = useAuth();
  const refresh = useRefreshProject(project.id);

  const loadReference = useMutation({
    mutationFn: () => api.loadReferencePlan(project.id),
    onSuccess: (v) => {
      toast.success(`Reference plan loaded as v${v.version_number} with reference answers`);
      selectVersion(v.id);
      refresh();
    },
  });
  const isOperator = user?.role === "operator";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Plan versions</CardTitle>
          <CardDescription>Versions are immutable. Every edit creates a new version linked to its parent.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline-primary"
              onClick={() => loadReference.mutate()}
              disabled={!isOperator}
              loading={loadReference.isPending}
              title={isOperator ? undefined : "Only the operator role can load the reference plan."}
            >
              <BookOpenCheck aria-hidden="true" /> Load reference plan
            </Button>
            <Button variant="outline" asChild>
              <Link to={`/projects/${project.id}/agent`}>
                <Sparkles aria-hidden="true" /> Revise with agent using answers
              </Link>
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Load reference plan creates a human-authored version from the reference mapping and pre-fills the reference answers (editable below). It works even when AI is unavailable.
            {!isOperator ? " Only the operator role can load it." : ""}
          </p>
          <ErrorBanner error={loadReference.error} title="Could not load the reference plan" />
          {versions.length === 0 ? (
            <EmptyState
              icon={FileJson}
              message="No plan versions yet. Run the agent or load the reference plan to create the first one."
              action={
                <Button onClick={() => loadReference.mutate()} disabled={!isOperator} loading={loadReference.isPending}>
                  <BookOpenCheck aria-hidden="true" /> Load reference plan
                </Button>
              }
            />
          ) : (
            <VersionList versions={versions} selectedId={selectedVersion?.id ?? null} onSelect={selectVersion} />
          )}
        </CardContent>
      </Card>
      {selectedVersion ? <VersionDetail key={selectedVersion.id} summary={selectedVersion} /> : null}
    </div>
  );
}

function VersionList({ versions, selectedId, onSelect }: { versions: PlanVersion[]; selectedId: number | null; onSelect: (id: number) => void }) {
  return (
    <TableScroll className="max-h-72 rounded-md border border-border">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Plan versions</caption>
        <thead className="sticky top-0 bg-muted text-xs text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2">Version</th>
            <th scope="col" className="px-3 py-2">Author</th>
            <th scope="col" className="px-3 py-2">Status</th>
            <th scope="col" className="px-3 py-2">Hash</th>
            <th scope="col" className="px-3 py-2">Note</th>
            <th scope="col" className="px-3 py-2">Created</th>
            <th scope="col" className="px-3 py-2"><span className="sr-only">Select</span></th>
          </tr>
        </thead>
        <tbody>
          {versions.map((v) => {
            const selected = v.id === selectedId;
            return (
              <tr key={v.id} className={cn("border-t border-border", selected && "bg-primary/5")}>
                <td className="px-3 py-2 font-medium">v{v.version_number}</td>
                <td className="px-3 py-2">
                  {v.author_type === "agent" ? "Agent" : (v.author_username ?? "human")}
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={v.status} />
                </td>
                <td className="px-3 py-2 font-mono text-xs">{shortHash(v.content_hash)}</td>
                <td className="max-w-xs truncate px-3 py-2 text-xs text-muted-foreground">{v.change_note ?? "-"}</td>
                <td className="whitespace-nowrap px-3 py-2 text-xs">{formatDateTime(v.created_at)}</td>
                <td className="px-3 py-2">
                  <Button size="sm" variant={selected ? "default" : "outline"} aria-pressed={selected} onClick={() => onSelect(v.id)}>
                    {selected ? "Selected" : "Select"}
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableScroll>
  );
}

function VersionDetail({ summary }: { summary: PlanVersion }) {
  const version = useQuery({ queryKey: qk.planVersion(summary.id), queryFn: () => api.planVersion(summary.id) });
  const target = useQuery({ queryKey: qk.targetSchema, queryFn: api.targetSchema, staleTime: Infinity });
  const [tab, setTab] = useState("mappings");
  const [draft, setDraft] = useState<string>("");
  const [editing, setEditing] = useState<PlanMapping | null>(null);

  useEffect(() => {
    if (version.data?.plan && draft === "") setDraft(JSON.stringify(version.data.plan, null, 2));
  }, [version.data, draft]);

  if (version.isPending) return <LoadingBlock rows={6} label="Loading version" />;
  if (version.isError) return <ErrorBanner error={version.error} onRetry={() => void version.refetch()} />;
  const v = version.data;
  const plan = v.plan!;

  const applyMapping = (m: PlanMapping) => {
    let base: Plan;
    try {
      base = JSON.parse(draft) as Plan;
    } catch {
      base = plan;
    }
    const mappings = base.mappings.map((x) => (x.id === m.id ? m : x));
    setDraft(JSON.stringify({ ...base, mappings }, null, 2));
    setEditing(null);
    setTab("edit");
    toast.info(`Mapping ${m.target_field} updated in the draft. Validate and save it as a new version.`);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Version v{v.version_number} <StatusBadge status={v.status} />
        </CardTitle>
        <CardDescription>
          {v.author_type === "agent" ? "Proposed by the agent" : `Authored by ${v.author_username ?? "a human"}`} · hash{" "}
          <span className="font-mono">{shortHash(v.content_hash, 16)}</span>
          {v.parent_version_id ? ` · parent #${v.parent_version_id}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="mappings">Mappings</TabsTrigger>
            <TabsTrigger value="questions">
              Questions & risks
              {v.unanswered_question_ids.length + v.unacknowledged_high_risk_ids.length > 0 ? (
                <span className="ml-1 rounded-full bg-warning-subtle px-1.5 text-xs text-warning-strong">
                  {v.unanswered_question_ids.length + v.unacknowledged_high_risk_ids.length} open
                </span>
              ) : null}
            </TabsTrigger>
            <TabsTrigger value="edit">Edit</TabsTrigger>
            <TabsTrigger value="diff">Diff vs parent</TabsTrigger>
          </TabsList>
          <TabsContent value="mappings" className="space-y-4">
            <MappingBuckets plan={plan} target={target.data} onEdit={setEditing} />
            <PlanExtras plan={plan} />
          </TabsContent>
          <TabsContent value="questions">
            <QuestionsAndRisks version={v} />
          </TabsContent>
          <TabsContent value="edit">
            <PlanEditor version={v} draft={draft} setDraft={setDraft} />
          </TabsContent>
          <TabsContent value="diff">
            <DiffTab version={v} />
          </TabsContent>
        </Tabs>
      </CardContent>
      <MappingSheet mapping={editing} onClose={() => setEditing(null)} onApply={applyMapping} />
    </Card>
  );
}

function QuestionsAndRisks({ version }: { version: PlanVersion }) {
  const refresh = useRefreshProject(version.project_id);
  const plan = version.plan!;
  const [answers, setAnswers] = useState<Record<string, string>>(version.answers);
  const [selectedRisks, setSelectedRisks] = useState<string[]>([]);
  const isDraft = version.status === "DRAFT";
  const risks = allRisks(plan);

  const saveAnswers = useMutation({
    mutationFn: () => {
      const body = Object.fromEntries(Object.entries(answers).filter(([, a]) => a.trim() !== ""));
      return api.saveAnswers(version.id, body);
    },
    onSuccess: () => {
      toast.success("Answers saved");
      refresh();
    },
  });
  const ack = useMutation({
    mutationFn: () => api.ackRisks(version.id, selectedRisks),
    onSuccess: () => {
      toast.success(`${selectedRisks.length} risk(s) acknowledged`);
      setSelectedRisks([]);
      refresh();
    },
  });
  const hasAnswers = Object.values(answers).some((a) => a.trim() !== "");
  const fieldErrors = saveAnswers.error instanceof ApiError ? saveAnswers.error.details : {};
  const unknownIds = Array.isArray(fieldErrors.unknown_question_ids) ? (fieldErrors.unknown_question_ids as string[]) : [];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="space-y-3" aria-labelledby="questions-h">
        <h3 id="questions-h" className="flex items-center gap-2 text-sm font-semibold">
          <ListChecks className="h-4 w-4" aria-hidden="true" /> Clarification answers
        </h3>
        {!isDraft ? <p className="text-xs text-muted-foreground">This version is {version.status}; answers can only change on a DRAFT.</p> : null}
        {plan.clarification_questions.length === 0 ? <p className="text-sm text-muted-foreground">This plan has no questions.</p> : null}
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            saveAnswers.mutate();
          }}
        >
          {plan.clarification_questions.map((q) => (
            <div key={q.id} className="space-y-1.5 rounded-md border border-border p-3">
              <Label htmlFor={`ans-${q.id}`} className="leading-5">
                <span className="font-mono text-xs">{q.id}</span> {q.question}
              </Label>
              {q.options.length ? (
                <div className="flex flex-wrap gap-1" role="group" aria-label={`Options for ${q.id}`}>
                  {q.options.map((o) => (
                    <Button
                      key={o}
                      type="button"
                      size="sm"
                      variant={answers[q.id] === o ? "default" : "outline"}
                      aria-pressed={answers[q.id] === o}
                      disabled={!isDraft}
                      onClick={() => setAnswers({ ...answers, [q.id]: o })}
                    >
                      {o}
                    </Button>
                  ))}
                </div>
              ) : null}
              <Input
                id={`ans-${q.id}`}
                value={answers[q.id] ?? ""}
                disabled={!isDraft}
                aria-invalid={unknownIds.includes(q.id) || undefined}
                onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                placeholder="Your answer"
              />
              {version.unanswered_question_ids.includes(q.id) ? <p className="text-xs text-warning-strong">Not answered yet (saved answers only).</p> : null}
            </div>
          ))}
          {plan.clarification_questions.length > 0 ? (
            <Button type="submit" disabled={!isDraft || !hasAnswers} loading={saveAnswers.isPending}>
              Save answers
            </Button>
          ) : null}
          <ErrorBanner error={saveAnswers.error} title="Could not save answers" />
        </form>
      </section>

      <section className="space-y-3" aria-labelledby="risks-h">
        <h3 id="risks-h" className="text-sm font-semibold">
          Risks
        </h3>
        <p className="text-xs text-muted-foreground">High-severity risks must be acknowledged before approval.</p>
        {risks.length === 0 ? <p className="text-sm text-muted-foreground">No risks recorded.</p> : null}
        <ul className="space-y-2">
          {risks.map((r) => {
            const acked = version.risk_acks.includes(r.id);
            return (
              <li key={r.id} className="flex items-start gap-2 rounded-md border border-border p-2 text-sm">
                <input
                  id={`risk-${r.id}`}
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]"
                  checked={acked || selectedRisks.includes(r.id)}
                  disabled={acked || !isDraft}
                  onChange={(e) => setSelectedRisks(e.target.checked ? [...selectedRisks, r.id] : selectedRisks.filter((x) => x !== r.id))}
                />
                <label htmlFor={`risk-${r.id}`} className="min-w-0 flex-1 space-y-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={r.severity} /> <span className="font-mono text-xs">{r.id}</span>
                    <span className="text-xs text-muted-foreground">on {r.target_field}</span>
                    {acked ? <span className="text-xs text-success-strong">Acknowledged</span> : null}
                  </span>
                  <span className="block">{r.text}</span>
                </label>
              </li>
            );
          })}
        </ul>
        {risks.length > 0 ? (
          <Button variant="outline-primary" onClick={() => ack.mutate()} disabled={!isDraft || selectedRisks.length === 0} loading={ack.isPending}>
            Acknowledge selected ({selectedRisks.length})
          </Button>
        ) : null}
        <ErrorBanner error={ack.error} title="Could not acknowledge risks" />
      </section>
    </div>
  );
}

function PlanEditor({ version, draft, setDraft }: { version: PlanVersion; draft: string; setDraft: (s: string) => void }) {
  const { selectVersion } = useWorkspace();
  const refresh = useRefreshProject(version.project_id);
  const [note, setNote] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [validation, setValidation] = useState<PlanValidationResult | null>(null);
  const editorId = useId();
  const noteId = useId();

  const parse = (): unknown | null => {
    try {
      const value = JSON.parse(draft);
      setParseError(null);
      return value;
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Invalid JSON");
      return null;
    }
  };

  const validate = useMutation({
    mutationFn: (plan: unknown) => api.validatePlan(version.id, plan),
    onSuccess: (res) => setValidation(res),
  });
  const save = useMutation({
    mutationFn: (plan: unknown) => api.createPlanVersion(version.project_id, { plan: plan as Plan, change_note: note.trim(), parent_version_id: version.id }),
    onSuccess: (v) => {
      toast.success(`Saved as v${v.version_number}`);
      selectVersion(v.id);
      refresh();
    },
  });

  const serverErrors = useMemo(() => {
    if (save.error instanceof ApiError) {
      const errs = save.error.details?.errors;
      return Array.isArray(errs) ? (errs as { code: string; path: string; message: string }[]) : [];
    }
    return [];
  }, [save.error]);
  const issues = serverErrors.length ? serverErrors : (validation?.errors ?? []);
  const original = JSON.stringify(version.plan, null, 2);
  const dirty = draft !== original;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Edit the plan JSON (or use Edit on a mapping), validate it against the registry and schemas, then save it as a new version. Validation errors show the exact path.
      </p>
      <div className="space-y-1.5">
        <Label htmlFor={editorId}>Plan JSON</Label>
        <Textarea
          id={editorId}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setValidation(null);
          }}
          spellCheck={false}
          aria-invalid={!!parseError || issues.length > 0}
          className="min-h-[24rem] font-mono text-xs"
        />
        {parseError ? <p className="text-xs text-danger-strong">JSON parse error: {parseError}</p> : null}
      </div>
      {validation && validation.valid && serverErrors.length === 0 ? (
        <p role="status" className="text-sm text-success-strong">
          Valid plan{validation.warnings.length ? ` with ${validation.warnings.length} warning(s)` : ""}.
        </p>
      ) : null}
      {issues.length > 0 ? (
        <div role="alert" className="rounded-md border border-danger/40 bg-danger-subtle p-3 text-sm text-danger-strong">
          <p className="font-medium">{issues.length} validation error(s)</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {issues.map((e, i) => (
              <li key={i}>
                <span className="font-mono text-xs">{e.path || "(root)"}</span> [{e.code}]: {e.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {validation?.warnings.length ? (
        <ul className="list-disc pl-5 text-xs text-warning-strong">
          {validation.warnings.map((w, i) => (
            <li key={i}>
              <span className="font-mono">{w.path}</span>: {w.message}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="space-y-1.5">
        <Label htmlFor={noteId}>Change note (required)</Label>
        <Input id={noteId} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed and why" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => {
            const p = parse();
            if (p !== null) validate.mutate(p);
          }}
          loading={validate.isPending}
        >
          Validate
        </Button>
        <Button
          onClick={() => {
            const p = parse();
            if (p !== null) save.mutate(p);
          }}
          disabled={!note.trim() || !dirty}
          loading={save.isPending}
        >
          Save as new version
        </Button>
        <Button variant="ghost" onClick={() => setDraft(original)} disabled={!dirty}>
          Reset to v{version.version_number}
        </Button>
      </div>
      {!dirty ? <p className="text-xs text-muted-foreground">Make a change before saving a new version.</p> : !note.trim() ? <p className="text-xs text-muted-foreground">A change note is required to save.</p> : null}
      <ErrorBanner error={validate.error} title="Validation request failed" />
      {save.error && serverErrors.length === 0 ? <ErrorBanner error={save.error} title="Could not save the version" /> : null}
    </div>
  );
}

function DiffTab({ version }: { version: PlanVersion }) {
  const diff = useQuery({ queryKey: qk.diff(version.id, null), queryFn: () => api.diff(version.id) });
  if (diff.isPending) return <LoadingBlock rows={4} label="Loading diff" />;
  if (diff.isError) return <ErrorBanner error={diff.error} onRetry={() => void diff.refetch()} />;
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-2 text-sm font-medium">
        <GitCompare className="h-4 w-4" aria-hidden="true" />
        {diff.data.against_version_id ? `Compared with parent #${diff.data.against_version_id}` : "First version"}
      </p>
      <DiffView diff={diff.data} />
    </div>
  );
}

function MappingSheet({ mapping, onClose, onApply }: { mapping: PlanMapping | null; onClose: () => void; onApply: (m: PlanMapping) => void }) {
  const [sources, setSources] = useState("");
  const [transforms, setTransforms] = useState("");
  const [onError, setOnError] = useState<PlanMapping["on_error"]>("quarantine");
  const [confidence, setConfidence] = useState<PlanMapping["confidence"]>("medium");
  const [err, setErr] = useState<string | null>(null);
  const transforms_ = useQuery({ queryKey: qk.transforms, queryFn: api.transforms, staleTime: Infinity, enabled: !!mapping });

  useEffect(() => {
    if (mapping) {
      setSources(mapping.source_fields.join(", "));
      setTransforms(JSON.stringify(mapping.transforms, null, 2));
      setOnError(mapping.on_error);
      setConfidence(mapping.confidence);
      setErr(null);
    }
  }, [mapping]);

  return (
    <Sheet open={!!mapping} onOpenChange={(o) => !o && onClose()}>
      <SheetContent>
        <SheetTitle>Edit mapping {mapping?.target_field}</SheetTitle>
        <SheetDescription>Changes go into the plan draft. Validate and save on the Edit tab to create a new version.</SheetDescription>
        {mapping ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              try {
                const parsed = JSON.parse(transforms) as PlanMapping["transforms"];
                if (!Array.isArray(parsed)) throw new Error("Transforms must be a JSON array.");
                onApply({
                  ...mapping,
                  source_fields: sources.split(",").map((s) => s.trim()).filter(Boolean),
                  transforms: parsed,
                  on_error: onError,
                  confidence,
                });
              } catch (ex) {
                setErr(ex instanceof Error ? ex.message : "Invalid transforms JSON");
              }
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="m-sources">Source fields (comma-separated)</Label>
              <Input id="m-sources" value={sources} onChange={(e) => setSources(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-transforms">Transform chain (JSON array of {"{name, params}"})</Label>
              <Textarea id="m-transforms" value={transforms} onChange={(e) => setTransforms(e.target.value)} className="min-h-[12rem] font-mono text-xs" aria-invalid={!!err} />
              {err ? <p className="text-xs text-danger-strong">{err}</p> : null}
              {transforms_.data ? (
                <p className="text-xs text-muted-foreground">Registry: {transforms_.data.map((t) => t.name).join(", ")}</p>
              ) : null}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="m-onerror">On error</Label>
                <NativeSelect id="m-onerror" value={onError} onChange={(e) => setOnError(e.target.value as PlanMapping["on_error"])}>
                  <option value="quarantine">quarantine</option>
                  <option value="set_null">set_null (nullable targets only)</option>
                </NativeSelect>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="m-conf">Confidence</Label>
                <NativeSelect id="m-conf" value={confidence} onChange={(e) => setConfidence(e.target.value as PlanMapping["confidence"])}>
                  <option value="high">high</option>
                  <option value="medium">medium</option>
                  <option value="low">low</option>
                </NativeSelect>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit">Apply to draft</Button>
            </div>
          </form>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
