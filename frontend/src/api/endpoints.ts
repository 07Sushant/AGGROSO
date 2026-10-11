import { apiRequest } from "./client";
import type {
  AgentRun,
  AgentRunCreate,
  ApprovalChecklist,
  ApprovalDecisionResponse,
  ConfigResponse,
  DatasetSummary,
  DeterminismResult,
  DryRun,
  DryRunRecord,
  HealthResponse,
  HistoryResponse,
  LoginResponse,
  LogsResponse,
  MigrationRun,
  Page,
  Plan,
  PlanDiff,
  PlanValidationResult,
  PlanVersion,
  ProjectDetail,
  ProjectSummary,
  Reconciliation,
  RunResult,
  SchemaImport,
  SourceRecordsPage,
  SourceSchema,
  TargetRecord,
  TargetSchema,
  TransformInfo,
  User,
  ImportedSchema,
} from "./types";

/** Every backend call in one place (final.md §9). */
export const api = {
  // health / config
  live: (signal?: AbortSignal) => apiRequest<{ status: "ok" }>("/health/live", { signal }),
  health: () => apiRequest<HealthResponse>("/health"),
  config: () => apiRequest<ConfigResponse>("/config"),

  // auth
  login: (username: string, password: string) =>
    apiRequest<LoginResponse>("/auth/login", { method: "POST", body: { username, password } }),
  me: () => apiRequest<User>("/auth/me"),

  // inputs
  sourceSchema: () => apiRequest<SourceSchema>("/inputs/source-schema"),
  targetSchema: () => apiRequest<TargetSchema>("/inputs/target-schema"),
  transforms: () => apiRequest<TransformInfo[]>("/inputs/transforms"),
  datasets: () => apiRequest<DatasetSummary[]>("/inputs/datasets"),

  // projects
  projects: () => apiRequest<ProjectSummary[]>("/projects"),
  project: (id: number) => apiRequest<ProjectDetail>(`/projects/${id}`),
  createProject: (body: { name: string; dataset_key: string }) =>
    apiRequest<ProjectDetail>("/projects", { method: "POST", body }),
  sourceRecords: (id: number, limit: number, offset: number) =>
    apiRequest<SourceRecordsPage>(`/projects/${id}/source-records`, { query: { limit, offset } }),
  targetRecords: (id: number, runId: number | null, limit: number, offset: number) =>
    apiRequest<Page<TargetRecord>>(`/projects/${id}/target-records`, { query: { run_id: runId, limit, offset } }),
  history: (id: number) => apiRequest<HistoryResponse>(`/projects/${id}/history`),

  // agent
  startAgentRun: (projectId: number, body: AgentRunCreate) =>
    apiRequest<AgentRun>(`/projects/${projectId}/agent-runs`, { method: "POST", body }),
  agentRun: (id: number) => apiRequest<AgentRun>(`/agent-runs/${id}`),

  // plan versions
  planVersions: (projectId: number) => apiRequest<PlanVersion[]>(`/projects/${projectId}/plan-versions`),
  planVersion: (id: number) => apiRequest<PlanVersion>(`/plan-versions/${id}`),
  createPlanVersion: (projectId: number, body: { plan: Plan | Record<string, unknown>; change_note: string; parent_version_id?: number | null }) =>
    apiRequest<PlanVersion>(`/projects/${projectId}/plan-versions`, { method: "POST", body }),
  loadReferencePlan: (projectId: number) =>
    apiRequest<PlanVersion>(`/projects/${projectId}/plan-versions/reference`, { method: "POST" }),
  diff: (id: number, against?: number | null) =>
    apiRequest<PlanDiff>(`/plan-versions/${id}/diff`, { query: { against: against ?? undefined } }),
  validatePlan: (id: number, plan?: unknown) =>
    apiRequest<PlanValidationResult>(`/plan-versions/${id}/validate`, { method: "POST", body: plan === undefined ? {} : { plan } }),
  saveAnswers: (id: number, answers: Record<string, string>) =>
    apiRequest<PlanVersion>(`/plan-versions/${id}/answers`, { method: "POST", body: { answers } }),
  ackRisks: (id: number, riskIds: string[]) =>
    apiRequest<PlanVersion>(`/plan-versions/${id}/risk-acks`, { method: "POST", body: { risk_ids: riskIds } }),

  // dry runs
  createDryRun: (versionId: number) => apiRequest<DryRun>(`/plan-versions/${versionId}/dry-runs`, { method: "POST" }),
  dryRun: (id: number) => apiRequest<DryRun>(`/dry-runs/${id}`),
  dryRunRecords: (id: number, q: { outcome?: "ACCEPTED" | "REJECTED"; code?: string; target_field?: string; limit?: number; offset?: number }) =>
    apiRequest<Page<DryRunRecord>>(`/dry-runs/${id}/records`, { query: { limit: 500, ...q } }),
  exportDryRun: (id: number, format: "csv" | "json") =>
    apiRequest<Response>(`/dry-runs/${id}/export`, { query: { format }, raw: true }),
  determinism: (versionId: number) =>
    apiRequest<DeterminismResult>(`/plan-versions/${versionId}/determinism`, { method: "POST" }),

  // approval
  checklist: (versionId: number) => apiRequest<ApprovalChecklist>(`/plan-versions/${versionId}/approval-checklist`),
  approve: (versionId: number, comment?: string) =>
    apiRequest<ApprovalDecisionResponse>(`/plan-versions/${versionId}/approve`, { method: "POST", body: { comment: comment || null } }),
  reject: (versionId: number, comment: string) =>
    apiRequest<ApprovalDecisionResponse>(`/plan-versions/${versionId}/reject`, { method: "POST", body: { comment } }),
  revoke: (versionId: number, comment: string) =>
    apiRequest<ApprovalDecisionResponse>(`/plan-versions/${versionId}/revoke`, { method: "POST", body: { comment } }),

  // runs
  execute: (versionId: number, idempotencyKey: string, simulateFailureAfter?: number | null) =>
    apiRequest<MigrationRun>(`/plan-versions/${versionId}/runs`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: simulateFailureAfter ? { simulate_failure_after: simulateFailureAfter } : {},
    }),
  run: (id: number) => apiRequest<MigrationRun>(`/runs/${id}`),
  runResults: (id: number, outcome?: RunResult["outcome"]) =>
    apiRequest<Page<RunResult>>(`/runs/${id}/results`, { query: { outcome, limit: 500 } }),
  reconciliation: (id: number) => apiRequest<Reconciliation>(`/runs/${id}/reconciliation`),
  retry: (id: number) => apiRequest<MigrationRun>(`/runs/${id}/retry`, { method: "POST" }),
  rollback: (id: number, reason: string) =>
    apiRequest<MigrationRun>(`/runs/${id}/rollback`, { method: "POST", body: { reason } }),

  // logs
  logs: (q: { request_id?: string; event?: string; limit?: number }) =>
    apiRequest<LogsResponse>("/ops/logs", { query: { limit: 200, ...q } }),

  // schema import (stretch)
  createSchemaImport: (file: File, projectId?: number | null) => {
    const form = new FormData();
    form.append("file", file);
    if (projectId) form.append("project_id", String(projectId));
    return apiRequest<SchemaImport>("/schema-imports", { method: "POST", body: form });
  },
  schemaImports: () => apiRequest<SchemaImport[] | Page<SchemaImport>>("/schema-imports"),
  schemaImport: (id: number) => apiRequest<SchemaImport>(`/schema-imports/${id}`),
  approveSchemaImport: (id: number, normalized?: ImportedSchema) =>
    apiRequest<SchemaImport>(`/schema-imports/${id}/approve`, { method: "POST", body: normalized ? { normalized } : {} }),
};
