import { AlertTriangle, ArrowLeft, CheckCircle2, CircleHelp, HelpCircle, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import type { Plan, PlanDiff, PlanMapping, Severity, TargetSchema } from "@/api/types";
import { TableScroll } from "@/components/ui/misc";
import { bucketize, describeTransform } from "@/lib/plan";
import { cn, formatValue } from "@/lib/utils";

const SEVERITY: Record<Severity, string> = {
  low: "bg-muted text-foreground border-border",
  medium: "bg-warning-subtle text-warning-strong border-warning/30",
  high: "bg-danger-subtle text-danger-strong border-danger/30",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const Icon = severity === "high" ? ShieldAlert : AlertTriangle;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", SEVERITY[severity])}>
      <Icon className="h-3 w-3" aria-hidden="true" /> {severity}
    </span>
  );
}

function BucketSection({ title, icon, count, children, hint }: { title: string; icon: ReactNode; count: number; children: ReactNode; hint: string }) {
  return (
    <section className="space-y-2" aria-label={title}>
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        {icon} {title} <span className="rounded-full bg-muted px-2 text-xs font-medium tabular-nums">{count}</span>
      </h3>
      <p className="text-xs text-muted-foreground">{hint}</p>
      {children}
    </section>
  );
}

export function MappingRows({ mappings, onEdit }: { mappings: PlanMapping[]; onEdit?: (m: PlanMapping) => void }) {
  if (mappings.length === 0) return <p className="text-xs text-muted-foreground">None.</p>;
  return (
    <TableScroll className="rounded-md border border-border">
      <table className="w-full text-left text-sm">
        <thead className="bg-muted text-xs text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2">Target ← source</th>
            <th scope="col" className="px-3 py-2">Transforms</th>
            <th scope="col" className="px-3 py-2">Confidence</th>
            <th scope="col" className="px-3 py-2">Risks</th>
            {onEdit ? <th scope="col" className="px-3 py-2"><span className="sr-only">Actions</span></th> : null}
          </tr>
        </thead>
        <tbody>
          {mappings.map((m) => (
            <tr key={m.id} className="border-t border-border align-top">
              <td className="px-3 py-2">
                <span className="font-mono text-xs font-medium">{m.target_field}</span>
                <span className="mx-1 text-muted-foreground" aria-label="from">
                  <ArrowLeft className="inline h-3 w-3" aria-hidden="true" />
                </span>
                <span className="font-mono text-xs">{m.source_fields.length ? m.source_fields.join(", ") : "(none)"}</span>
                {m.rationale ? <p className="mt-1 max-w-sm text-xs text-muted-foreground">{m.rationale}</p> : null}
              </td>
              <td className="px-3 py-2">
                <div className="flex flex-wrap gap-1">
                  {m.transforms.length === 0 ? <span className="text-xs text-muted-foreground">copy</span> : null}
                  {m.transforms.map((t, i) => (
                    <span key={i} className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px]">
                      {describeTransform(t)}
                    </span>
                  ))}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">on error: {m.on_error}</p>
              </td>
              <td className="px-3 py-2 text-xs capitalize">{m.confidence}</td>
              <td className="px-3 py-2">
                <ul className="space-y-1">
                  {m.risks.map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center gap-1 text-xs">
                      <SeverityBadge severity={r.severity} /> <span className="font-mono">{r.id}</span> {r.text}
                    </li>
                  ))}
                  {m.risks.length === 0 ? <li className="text-xs text-muted-foreground">none</li> : null}
                </ul>
              </td>
              {onEdit ? (
                <td className="px-3 py-2">
                  <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={() => onEdit(m)}>
                    Edit
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}

/** Mappings grouped as Confident / Needs review / Missing / Incompatible (spec §5.1). */
export function MappingBuckets({ plan, target, onEdit }: { plan: Plan; target?: TargetSchema | null; onEdit?: (m: PlanMapping) => void }) {
  const b = bucketize(plan, target);
  return (
    <div className="space-y-5">
      <BucketSection title="Needs review" icon={<HelpCircle className="h-4 w-4 text-warning" aria-hidden="true" />} count={b.needsReview.length} hint="Medium or low confidence, or carries risks.">
        <MappingRows mappings={b.needsReview} onEdit={onEdit} />
      </BucketSection>
      <BucketSection title="Confident" icon={<CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />} count={b.confident.length} hint="High confidence and no risks.">
        <MappingRows mappings={b.confident} onEdit={onEdit} />
      </BucketSection>
      <BucketSection title="Missing" icon={<CircleHelp className="h-4 w-4 text-danger" aria-hidden="true" />} count={b.missing.length} hint="Required target fields with no mapping.">
        {b.missing.length ? (
          <ul className="flex flex-wrap gap-1">
            {b.missing.map((f) => (
              <li key={f} className="rounded border border-danger/30 bg-danger-subtle px-2 py-0.5 font-mono text-xs text-danger-strong">
                {f}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">Every required target field is covered.</p>
        )}
      </BucketSection>
      <BucketSection title="Incompatible" icon={<AlertTriangle className="h-4 w-4 text-danger" aria-hidden="true" />} count={b.incompatible.length} hint="Type or format conflicts the plan has to handle.">
        {b.incompatible.length ? (
          <ul className="space-y-1">
            {b.incompatible.map((inc, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                <SeverityBadge severity={inc.severity} /> <span className="font-mono text-xs">{inc.field}</span> {inc.issue}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">None reported.</p>
        )}
      </BucketSection>
    </div>
  );
}

export function PlanExtras({ plan }: { plan: Plan }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Clarification questions</h3>
        {plan.clarification_questions.length === 0 ? <p className="text-xs text-muted-foreground">None.</p> : null}
        <ul className="space-y-2">
          {plan.clarification_questions.map((q) => (
            <li key={q.id} className="rounded-md border border-border p-2 text-sm">
              <span className="font-mono text-xs font-medium">{q.id}</span> {q.question}
              {q.options.length ? <p className="mt-1 text-xs text-muted-foreground">Options: {q.options.join(" / ")}</p> : null}
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Unmapped fields and risk summary</h3>
        <ul className="space-y-1 text-sm">
          {plan.unmapped_source_fields.map((u) => (
            <li key={`s-${u.field}`}>
              Source <span className="font-mono text-xs">{u.field}</span>: {u.decision} ({u.reason || "no reason"})
            </li>
          ))}
          {plan.unmapped_target_fields.map((u) => (
            <li key={`t-${u.field}`}>
              Target <span className="font-mono text-xs">{u.field}</span>: {u.reason || "no source"}
              {u.proposed ? <> (proposed <span className="font-mono text-xs">{describeTransform(u.proposed)}</span>)</> : null}
            </li>
          ))}
        </ul>
        {plan.risk_summary ? <p className="rounded-md bg-muted p-2 text-sm">{plan.risk_summary}</p> : null}
      </section>
    </div>
  );
}

/** Side-by-side diff, changes highlighted per field (spec §8.0 DiffView). */
export function DiffView({ diff }: { diff: PlanDiff }) {
  const { summary } = diff;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        {diff.against_version_id === null ? "No parent version: everything is new. " : null}
        {summary.added} added, {summary.removed} removed, {summary.changed} changed, {summary.unchanged} unchanged mappings.
      </p>
      {diff.mappings.length === 0 && Object.keys(diff.sections).length === 0 ? <p className="text-sm">No differences.</p> : null}
      {diff.mappings.map((c) => (
        <div key={c.target_field} className="rounded-md border border-border">
          <p className="border-b border-border bg-muted px-3 py-1.5 text-xs font-medium">
            <span className="font-mono">{c.target_field}</span> <span className="ml-1 uppercase text-muted-foreground">{c.change}</span>
          </p>
          <div className="grid grid-cols-1 gap-px bg-border sm:grid-cols-2">
            <div className="min-w-0 bg-surface p-2">
              <p className="mb-1 text-xs text-muted-foreground">Before</p>
              {c.change === "changed" && c.fields ? (
                Object.entries(c.fields).map(([k, v]) => (
                  <p key={k} className="break-words rounded bg-danger-subtle px-1 font-mono text-[11px] text-danger-strong">
                    {k}: {formatValue(v.from)}
                  </p>
                ))
              ) : c.from ? (
                <pre className="overflow-x-auto rounded bg-danger-subtle p-1 font-mono text-[11px] text-danger-strong">{JSON.stringify(c.from, null, 2)}</pre>
              ) : (
                <p className="text-xs text-muted-foreground">(absent)</p>
              )}
            </div>
            <div className="min-w-0 bg-surface p-2">
              <p className="mb-1 text-xs text-muted-foreground">After</p>
              {c.change === "changed" && c.fields ? (
                Object.entries(c.fields).map(([k, v]) => (
                  <p key={k} className="break-words rounded bg-success-subtle px-1 font-mono text-[11px] text-success-strong">
                    {k}: {formatValue(v.to)}
                  </p>
                ))
              ) : c.to ? (
                <pre className="overflow-x-auto rounded bg-success-subtle p-1 font-mono text-[11px] text-success-strong">{JSON.stringify(c.to, null, 2)}</pre>
              ) : (
                <p className="text-xs text-muted-foreground">(absent)</p>
              )}
            </div>
          </div>
        </div>
      ))}
      {Object.entries(diff.sections).map(([name, v]) => (
        <div key={name} className="rounded-md border border-border">
          <p className="border-b border-border bg-muted px-3 py-1.5 text-xs font-medium">
            Section <span className="font-mono">{name}</span> changed
          </p>
          <div className="grid grid-cols-1 gap-px bg-border sm:grid-cols-2">
            <pre className="min-w-0 overflow-x-auto bg-danger-subtle p-2 font-mono text-[11px] text-danger-strong">{JSON.stringify(v.from, null, 2)}</pre>
            <pre className="min-w-0 overflow-x-auto bg-success-subtle p-2 font-mono text-[11px] text-success-strong">{JSON.stringify(v.to, null, 2)}</pre>
          </div>
        </div>
      ))}
    </div>
  );
}
