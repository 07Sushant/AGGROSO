import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Loader2, Play, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/endpoints";
import type { AgentRun } from "@/api/types";
import { AgentTrace, traceOf } from "@/components/app/AgentTrace";
import { AiBanner } from "@/components/app/AiBanner";
import { EmptyState } from "@/components/app/EmptyState";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { MappingBuckets, PlanExtras } from "@/components/app/PlanViews";
import { StatusBadge } from "@/components/app/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingBlock } from "@/components/ui/misc";
import { useHealth } from "@/hooks/useServerStatus";
import { useRefreshProject } from "@/hooks/useRefreshProject";
import { useAuth } from "@/lib/auth";
import { qk } from "@/lib/queryKeys";
import { formatDateTime } from "@/lib/utils";
import { useWorkspace } from "./context";

const ACTIVE = new Set(["QUEUED", "RUNNING"]);

export function useAgentRun(runId: number | null) {
  return useQuery({
    queryKey: qk.agentRun(runId ?? 0),
    queryFn: () => api.agentRun(runId!),
    enabled: runId !== null,
    // Poll at 1 s only while the run is active (spec §8.3).
    refetchInterval: (q) => (q.state.data && ACTIVE.has(q.state.data.status) ? 1000 : false),
  });
}

export function AgentStep() {
  const { project, selectedVersion } = useWorkspace();
  const { user } = useAuth();
  const health = useHealth();
  const refresh = useRefreshProject(project.id);
  const history = useQuery({ queryKey: qk.history(project.id), queryFn: () => api.history(project.id) });
  const [runId, setRunId] = useState<number | null>(null);
  const latestId = history.data?.agent_runs[0]?.id ?? null;
  const effectiveId = runId ?? latestId;
  const run = useAgentRun(effectiveId);

  const start = useMutation({
    mutationFn: (revise: boolean) =>
      api.startAgentRun(project.id, revise && selectedVersion ? { base_version_id: selectedVersion.id, use_answers: true } : {}),
    onSuccess: (r) => {
      setRunId(r.id);
      toast.success(`Agent run #${r.id} queued`);
    },
  });

  // When an active run finishes, refresh the workspace once.
  const prevStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    const s = run.data?.status;
    if (prevStatus.current && ACTIVE.has(prevStatus.current) && s && !ACTIVE.has(s)) {
      refresh();
      void history.refetch();
      if (s === "SUCCEEDED") toast.success("The agent proposed a new draft version");
      else toast.error(`Agent run failed: ${run.data?.error_code ?? "error"}`);
    }
    prevStatus.current = s;
  }, [run.data?.status, run.data?.error_code, refresh, history]);

  const isOperator = user?.role === "operator";
  const active = !!run.data && ACTIVE.has(run.data.status);
  const aiDown = health.data?.ai.status === "down";
  const canRevise = !!selectedVersion && Object.keys(selectedVersion.answers).length > 0;
  const disabledReason = !isOperator
    ? "Only the operator role can run the agent."
    : active
      ? "An agent run is already in progress."
      : aiDown
        ? "AI services are unavailable; use Load reference plan or edit a plan manually."
        : null;

  return (
    <div className="space-y-4">
      {/* The shell already shows the health-based banner; this one covers a run that fell back. */}
      <AiBanner status={undefined} fellBack={!!run.data?.fell_back && health.data?.ai.status !== "backup" && health.data?.ai.status !== "down"} />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-4 w-4" aria-hidden="true" /> Migration agent
          </CardTitle>
          <CardDescription>
            The agent inspects the schemas and data through read-only tools, then submits a plan. It can never approve or execute; its proposal becomes a DRAFT version for you to review.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => start.mutate(false)} disabled={!!disabledReason} loading={start.isPending && start.variables === false}>
              <Play aria-hidden="true" /> Run agent
            </Button>
            <Button
              variant="outline-primary"
              onClick={() => start.mutate(true)}
              disabled={!!disabledReason || !canRevise}
              loading={start.isPending && start.variables === true}
              title={!canRevise ? "Answer the clarification questions on the Plan step first." : undefined}
            >
              <Sparkles aria-hidden="true" /> Revise v{selectedVersion?.version_number ?? "-"} with answers
            </Button>
          </div>
          {disabledReason ? <p className="text-xs text-muted-foreground">{disabledReason}</p> : null}
          {!disabledReason && !canRevise ? <p className="text-xs text-muted-foreground">Revising needs a selected version with answered questions.</p> : null}
          <ErrorBanner error={start.error} title="Could not start the agent" />
        </CardContent>
      </Card>

      {effectiveId === null ? (
        history.isPending ? (
          <LoadingBlock rows={3} label="Loading agent runs" />
        ) : (
          <EmptyState icon={Bot} message="The agent has not run for this project yet. Run it to get a proposed plan, or load the reference plan on the Plan step." />
        )
      ) : run.isPending ? (
        <LoadingBlock rows={4} label="Loading agent run" />
      ) : run.isError ? (
        <ErrorBanner error={run.error} onRetry={() => void run.refetch()} title="Could not load the agent run" />
      ) : (
        <AgentRunPanel run={run.data} />
      )}
    </div>
  );
}

function AgentRunPanel({ run }: { run: AgentRun }) {
  const steps = traceOf(run);
  const active = ACTIVE.has(run.status);
  const currentTool = [...steps].reverse().find((s) => s.tool_name)?.tool_name;
  const version = useQuery({
    queryKey: qk.planVersion(run.result_version_id ?? 0),
    queryFn: () => api.planVersion(run.result_version_id!),
    enabled: !!run.result_version_id,
  });
  const target = useQuery({ queryKey: qk.targetSchema, queryFn: api.targetSchema, staleTime: Infinity });

  return (
    <div className="grid gap-4 xl:grid-cols-5">
      <Card className="xl:col-span-2">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            Run #{run.id} <StatusBadge status={run.status} />
          </CardTitle>
          <CardDescription>
            {run.kind} · started {formatDateTime(run.started_at ?? run.created_at)}
            {run.engine ? ` · engine ${run.engine}` : ""}
            {run.mode ? ` · ${run.mode} mode` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {active ? (
            <p role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-info-strong">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              {currentTool ? (
                <>
                  Working: <span className="font-mono text-xs">{currentTool}</span>
                </>
              ) : (
                "Starting..."
              )}
            </p>
          ) : null}
          {run.status === "FAILED" ? (
            <div role="alert" className="rounded-md border border-danger/40 bg-danger-subtle p-3 text-sm text-danger-strong">
              <span className="font-mono text-xs">[{run.error_code}]</span> {run.error_message}
            </div>
          ) : null}
          <p className="text-xs text-muted-foreground">
            {steps.length} steps · {run.latency_ms ?? 0} ms · tokens {run.tokens_in ?? 0}/{run.tokens_out ?? 0}
          </p>
          <AgentTrace steps={steps} live={active} />
        </CardContent>
      </Card>

      <Card className="xl:col-span-3">
        <CardHeader>
          <CardTitle>Proposal</CardTitle>
          <CardDescription>Grouped into confidence buckets, with incompatibilities, risks and questions.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!run.result_version_id ? (
            <p className="text-sm text-muted-foreground">{active ? "The proposal appears here when the agent submits a valid plan." : "This run did not produce a plan version."}</p>
          ) : version.isPending ? (
            <LoadingBlock rows={5} label="Loading proposal" />
          ) : version.isError ? (
            <ErrorBanner error={version.error} onRetry={() => void version.refetch()} />
          ) : version.data.plan ? (
            <>
              <p className="text-sm">
                Created draft <span className="font-medium">v{version.data.version_number}</span>.{" "}
                <Link className="text-primary hover:underline" to={`/projects/${run.project_id}/plan`}>
                  Review it on the Plan step
                </Link>
              </p>
              <MappingBuckets plan={version.data.plan} target={target.data} />
              <PlanExtras plan={version.data.plan} />
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
