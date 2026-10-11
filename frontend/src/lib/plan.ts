import type { Plan, PlanMapping, Risk, TargetSchema } from "@/api/types";

export interface Buckets {
  confident: PlanMapping[];
  needsReview: PlanMapping[];
  missing: string[];
  incompatible: Plan["incompatibilities"];
}

/** Flatfile-style confidence buckets (spec §5.1). */
export function bucketize(plan: Plan, target?: TargetSchema | null): Buckets {
  const confident: PlanMapping[] = [];
  const needsReview: PlanMapping[] = [];
  for (const m of plan.mappings) {
    if (m.confidence === "high" && m.risks.length === 0) confident.push(m);
    else needsReview.push(m);
  }
  const mapped = new Set(plan.mappings.map((m) => m.target_field));
  const missing = (target?.columns ?? []).filter((c) => c.required && !mapped.has(c.name)).map((c) => c.name);
  return { confident, needsReview, missing, incompatible: plan.incompatibilities };
}

export function allRisks(plan: Plan): (Risk & { target_field: string })[] {
  return plan.mappings.flatMap((m) => m.risks.map((r) => ({ ...r, target_field: m.target_field })));
}

export function describeTransform(t: { name: string; params?: Record<string, unknown> }): string {
  const params = t.params && Object.keys(t.params).length > 0 ? JSON.stringify(t.params) : "";
  return params ? `${t.name}(${params})` : t.name;
}
