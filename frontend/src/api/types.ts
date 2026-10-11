/**
 * API DTOs, mirrored from backend/app/schemas/api.py and the service `*_out` helpers.
 * Agent-run and schema-import shapes follow final.md §9 / the ORM models; keep every
 * client-side type in this one file so contract changes are easy to adjust.
 */

export type Role = "operator" | "approver";

export interface User {
  id: number;
  username: string;
  role: Role;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id: string | null;
  };
}

export type AiStatus = "primary" | "backup" | "degraded" | "down" | "mock";

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  env: string;
  db: { status: "ok" | "down"; latency_ms: number | null };
  ai: { status: AiStatus; primary: string; backup: string; checked_at: string | null };
}

export interface ConfigResponse {
  app_env: string;
  version: string;
  max_source_records: number;
  fault_injection_enabled: boolean;
  llm_mode: "live" | "mock";
  demo_accounts: { username: string; role: string }[];
}

export interface DatasetSummary {
  key: string;
  name: string;
  description: string;
  record_count: number;
  within_limit: boolean;
}

export interface TransformInfo {
  name: string;
  description: string;
  input_type: string;
  output_type: string;
  params_schema: Record<string, unknown>;
}

export interface SourceField {
  name: string;
  type: string;
  nullable?: boolean;
  description?: string;
}

export interface SourceSchema {
  entity: string;
  description?: string;
  primary_key: string;
  fields: SourceField[];
}

export interface TargetColumn {
  name: string;
  type: string;
  required?: boolean;
  nullable?: boolean;
  unique?: boolean;
  description?: string;
  enum?: string[];
  regex?: string;
  [key: string]: unknown;
}

export interface TargetSchema {
  entity: string;
  description?: string;
  key: string;
  columns: TargetColumn[];
}

// ---------------------------------------------------------------- projects

export type PlanStatus = "DRAFT" | "APPROVED" | "REJECTED" | "SUPERSEDED";
export type RunStatus = "RUNNING" | "COMPLETED" | "FAILED" | "ROLLING_BACK" | "ROLLED_BACK";

export interface ProjectSummary {
  id: number;
  name: string;
  dataset_key: string;
  record_count: number;
  source_checksum: string;
  created_by: number;
  created_at: string;
  created_by_username?: string;
}

export interface ProjectDetail extends ProjectSummary {
  version_count: number;
  latest_version: { id: number; version_number: number; status: PlanStatus } | null;
  approved_version: { id: number; version_number: number } | null;
  latest_dry_run_id: number | null;
  active_run: { id: number; status: RunStatus } | null;
}

export interface SourceRecordsPage {
  total: number;
  items: { id: number; row_number: number; source_key: string | null; payload: Record<string, string> }[];
}

// ---------------------------------------------------------------- plan contract

export type Severity = "low" | "medium" | "high";
export type Confidence = "high" | "medium" | "low";

export interface TransformStep {
  name: string;
  params?: Record<string, unknown>;
}

export interface Risk {
  id: string;
  severity: Severity;
  text: string;
}

export interface PlanMapping {
  id: string;
  target_field: string;
  source_fields: string[];
  transforms: TransformStep[];
  on_error: "quarantine" | "set_null";
  confidence: Confidence;
  rationale: string;
  risks: Risk[];
}

export interface ClarificationQuestion {
  id: string;
  question: string;
  related_fields: string[];
  options: string[];
}

export interface Plan {
  key: { source_field: string; target_field: string };
  mappings: PlanMapping[];
  unmapped_source_fields: { field: string; reason: string; decision: string }[];
  unmapped_target_fields: { field: string; reason: string; proposed: TransformStep | null }[];
  incompatibilities: { field: string; issue: string; severity: Severity }[];
  clarification_questions: ClarificationQuestion[];
  risk_summary: string;
}

export interface PlanVersion {
  id: number;
  project_id: number;
  version_number: number;
  parent_version_id: number | null;
  author_type: "agent" | "human";
  author_id: number | null;
  author_username: string | null;
  status: PlanStatus;
  content_hash: string;
  change_note: string | null;
  agent_run_id: number | null;
  created_at: string;
  answers: Record<string, string>;
  risk_acks: string[];
  unanswered_question_ids: string[];
  unacknowledged_high_risk_ids: string[];
  plan?: Plan;
}

export interface ValidationIssue {
  code: string;
  path: string;
  message: string;
}

export interface PlanValidationResult {
  valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  [key: string]: unknown;
}

export interface PlanDiff {
  version_id: number;
  against_version_id: number | null;
  mappings: {
    target_field: string;
    change: "added" | "removed" | "changed";
    to?: PlanMapping;
    from?: PlanMapping;
    fields?: Record<string, { from: unknown; to: unknown }>;
  }[];
  sections: Record<string, { from: unknown; to: unknown }>;
  summary: { added: number; removed: number; changed: number; unchanged: number };
}

// ---------------------------------------------------------------- dry runs

export interface Counts {
  source: number;
  transformed: number;
  accepted: number;
  rejected: number;
}

export interface DryRun {
  id: number;
  plan_version_id: number;
  source_checksum: string;
  counts: Counts;
  rejected_by_code: Record<string, number>;
  rejected_by_field: Record<string, number>;
  result_hash: string;
  code_version: string;
  duration_ms: number;
  created_by: number | null;
  created_at: string;
}

export interface FieldError {
  target_field: string | null;
  source_fields: string[] | null;
  source_value: unknown;
  transform: string | null;
  rule: string | null;
  code: string;
  message: string;
  stage: string;
}

export interface DryRunRecord {
  row_number: number;
  source_record_id: number;
  source_key: string | null;
  outcome: "ACCEPTED" | "REJECTED";
  source: Record<string, string>;
  transformed: Record<string, unknown> | null;
  row_hash: string | null;
  errors: FieldError[];
}

export interface Page<T> {
  total: number;
  items: T[];
}

export interface DeterminismResult {
  plan_version_id: number;
  runs: number;
  hashes: string[];
  deterministic: boolean;
  latest_dry_run_id: number | null;
  matches_latest_dry_run: boolean | null;
}

// ---------------------------------------------------------------- approval

export interface ChecklistItem {
  id: string;
  label: string;
  ok: boolean;
  blocking: boolean;
  detail: string | null;
  missing?: string[];
}

export interface ApprovalChecklist {
  plan_version_id: number;
  content_hash: string;
  dry_run: { id: number; result_hash: string; counts: Counts } | null;
  items: ChecklistItem[];
  blockers: string[];
  can_approve: boolean;
  self_approval: boolean;
  unanswered_question_ids: string[];
  unacknowledged_high_risk_ids: string[];
}

export interface Approval {
  id: number;
  plan_version_id: number;
  decision: "APPROVED" | "REJECTED" | "REVOKED";
  actor_id: number;
  comment: string | null;
  content_hash: string;
  dry_run_id: number | null;
  dry_run_result_hash: string | null;
  source_checksum: string | null;
  self_approved: boolean;
  created_at: string;
}

export interface ApprovalDecisionResponse {
  approval: Approval;
  version: PlanVersion;
}

// ---------------------------------------------------------------- runs

export interface RunAttempt {
  id: number;
  attempt_number: number;
  kind: "EXECUTE" | "RETRY";
  status: "RUNNING" | "COMPLETED" | "FAILED";
  inserted: number;
  skipped_existing: number;
  quarantined: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface Reconciliation {
  run_id: number;
  run_status: RunStatus;
  status: "PASS" | "FAIL";
  totals: {
    source: number;
    transformed: number;
    accepted: number;
    rejected: number;
    quarantined_dry_run: number;
    quarantined_execute: number;
    quarantined_total: number;
    inserted: number;
    skipped_existing: number;
    target_rows: number;
  };
  missing_in_target: string[];
  unexpected_in_target: string[];
  value_mismatches: { legacy_id: string; field: string; expected: unknown; actual: unknown }[];
  value_mismatch_rows: number;
  invariants: { id: string; label: string; ok: boolean; expected: unknown; actual: unknown }[];
  discrepancies: { code: string; message: string; count?: number; invariant?: string }[];
}

export interface MigrationRun {
  id: number;
  project_id: number;
  plan_version_id: number;
  approval_id: number;
  idempotency_key: string;
  status: RunStatus;
  inserted: number;
  skipped_existing: number;
  quarantined: number;
  created_by: number;
  created_at: string;
  updated_at: string | null;
  finished_at: string | null;
  attempts: RunAttempt[];
  last_error: { code: string | null; message: string | null } | null;
  replayed: boolean;
  reconciliation?: Reconciliation;
  rollback?: { id: number; deleted_count: number; reason: string };
}

export interface RunResult {
  row_number: number;
  source_key: string | null;
  legacy_id: string | null;
  outcome: "INSERTED" | "SKIPPED_EXISTING" | "QUARANTINED";
  attempt_number: number;
  errors: FieldError[];
}

export type TargetRecord = Record<string, unknown> & {
  legacy_id: string;
  migration_run_id: number;
  row_hash: string;
};

// ---------------------------------------------------------------- history

export interface AuditEvent {
  id: number;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_id: number | null;
  actor: string | null;
  request_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface HistoryResponse {
  events: AuditEvent[];
  approvals: {
    id: number;
    plan_version_id: number;
    decision: Approval["decision"];
    actor: string | null;
    comment: string | null;
    self_approved: boolean;
    dry_run_id: number | null;
    created_at: string;
  }[];
  runs: MigrationRun[];
  rollbacks: { id: number; run_id: number; actor: string | null; reason: string; deleted_count: number; created_at: string }[];
  agent_runs: {
    id: number;
    kind: string;
    status: AgentRunStatus;
    engine: Engine | null;
    fell_back: boolean;
    result_version_id: number | null;
    created_at: string;
  }[];
}

// ---------------------------------------------------------------- agent (phase 3; §9 contract)

export type AgentRunStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
export type Engine = "primary" | "backup" | "mock";

export interface AgentStep {
  step_no: number;
  kind: "llm_call" | "tool_call" | "validation" | "fallback" | string;
  tool_name: string | null;
  args: unknown;
  result: unknown;
  ok: boolean;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  engine: Engine | null;
  error: string | null;
  /** "model" or "runner" (compact mode: tools the runner invoked on the model's behalf). */
  invoked_by?: string;
  created_at?: string;
}

export interface AgentRun {
  id: number;
  project_id: number;
  base_version_id: number | null;
  kind: "propose" | "revise" | string;
  status: AgentRunStatus;
  mode?: string | null;
  engine: Engine | null;
  steps?: AgentStep[] | number;
  trace?: AgentStep[];
  step_count?: number;
  tokens_in?: number;
  tokens_out?: number;
  latency_ms?: number;
  fell_back: boolean;
  error_code: string | null;
  error_message: string | null;
  result_version_id: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AgentRunCreate {
  base_version_id?: number;
  use_answers?: boolean;
}

// ---------------------------------------------------------------- logs

export interface LogLine {
  ts?: string;
  timestamp?: string;
  level?: string;
  event?: string;
  logger?: string;
  request_id?: string;
  [key: string]: unknown;
}

export interface LogsResponse {
  items: LogLine[];
  count: number;
}

// ---------------------------------------------------------------- schema import (stretch; §7.6)

export type SchemaFieldType = "string" | "integer" | "decimal" | "date" | "datetime" | "boolean" | "unknown";

export interface ImportedField {
  name: string;
  type: SchemaFieldType | string;
  nullable?: boolean;
  primary_key?: boolean;
  notes?: string | null;
  confidence?: number | null;
  needs_review?: boolean;
  original_name?: string;
}

export interface ImportedSchema {
  table_name?: string;
  fields: ImportedField[];
  relationships?: { from_field: string; to_table: string; to_field: string }[];
}

export interface SchemaComparison {
  matched?: string[];
  missing?: string[];
  extra?: string[];
  type_mismatch?: { field: string; expected?: string; actual?: string; [k: string]: unknown }[];
  [key: string]: unknown;
}

export interface SchemaImport {
  id: number;
  project_id: number | null;
  image_sha256: string;
  status: "PROCESSING" | "PROPOSED" | "APPROVED" | "REJECTED" | "FAILED" | string;
  extracted: ImportedSchema | null;
  normalized: ImportedSchema | null;
  findings: { code?: string; field?: string | null; message: string; severity?: string; [k: string]: unknown }[] | null;
  comparison?: SchemaComparison | null;
  engine: Engine | null;
  fell_back?: boolean;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  reviewed_at?: string | null;
}
