import { AlertTriangle, Bot, CheckCircle2, ChevronRight, RefreshCcw, ShieldCheck, Wrench, XCircle } from "lucide-react";
import type { AgentRun, AgentStep } from "@/api/types";
import { JsonViewer } from "@/components/app/JsonViewer";
import { cn } from "@/lib/utils";

export function traceOf(run: AgentRun | undefined | null): AgentStep[] {
  if (!run) return [];
  if (Array.isArray(run.trace)) return run.trace;
  if (Array.isArray(run.steps)) return run.steps;
  return [];
}

const KIND_ICON = { llm_call: Bot, tool_call: Wrench, validation: ShieldCheck, fallback: RefreshCcw } as const;

function stepTitle(s: AgentStep): string {
  if (s.kind === "fallback") return "Switched to backup";
  if (s.kind === "llm_call") return "Model call";
  if (s.kind === "validation") return `Validation${s.tool_name ? `: ${s.tool_name}` : ""}`;
  return s.tool_name ?? s.kind;
}

/** Vertical timeline of agent steps: tool, args, ok/error, latency, tokens, engine alias. */
export function AgentTrace({ steps, live = false }: { steps: AgentStep[]; live?: boolean }) {
  if (steps.length === 0) {
    return <p className="text-sm text-muted-foreground">{live ? "Waiting for the first step..." : "No steps recorded."}</p>;
  }
  return (
    <ol className="relative space-y-2 border-l border-border pl-5" aria-live={live ? "polite" : undefined}>
      {steps.map((s) => {
        const Icon = KIND_ICON[s.kind as keyof typeof KIND_ICON] ?? Wrench;
        const fallback = s.kind === "fallback";
        return (
          <li
            key={s.step_no}
            className={cn(
              "relative rounded-md border p-2 text-sm",
              fallback ? "border-warning/40 bg-warning-subtle" : s.ok ? "border-border bg-surface" : "border-danger/30 bg-danger-subtle",
            )}
          >
            <span className="absolute -left-[27px] top-2.5 flex h-4 w-4 items-center justify-center rounded-full border border-border bg-surface">
              <Icon className="h-2.5 w-2.5" aria-hidden="true" />
            </span>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-xs tabular-nums text-muted-foreground">#{s.step_no}</span>
              <span className={cn("font-medium", fallback && "text-warning-strong")}>{stepTitle(s)}</span>
              {fallback ? (
                <span className="inline-flex items-center gap-1 text-xs text-warning-strong">
                  <AlertTriangle className="h-3 w-3" aria-hidden="true" /> fallback
                </span>
              ) : s.ok ? (
                <span className="inline-flex items-center gap-1 text-xs text-success-strong">
                  <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> ok
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-xs text-danger-strong">
                  <XCircle className="h-3 w-3" aria-hidden="true" /> error
                </span>
              )}
              <span className="text-xs text-muted-foreground">{s.latency_ms} ms</span>
              {s.tokens_in || s.tokens_out ? (
                <span className="text-xs text-muted-foreground">
                  tokens {s.tokens_in}/{s.tokens_out}
                </span>
              ) : null}
              {s.engine ? <span className="rounded bg-muted px-1.5 text-xs">engine: {s.engine}</span> : null}
              {s.invoked_by === "runner" ? <span className="rounded bg-muted px-1.5 text-xs">runner-invoked</span> : null}
            </div>
            {s.error ? <p className="mt-1 break-words text-xs text-danger-strong">{s.error}</p> : null}
            {s.args !== null && s.args !== undefined ? (
              <details className="mt-1">
                <summary className="flex cursor-pointer items-center gap-1 text-xs text-muted-foreground">
                  <ChevronRight className="h-3 w-3" aria-hidden="true" /> Arguments
                </summary>
                <JsonViewer value={s.args} maxHeight="12rem" className="mt-1" />
              </details>
            ) : null}
            {s.result !== null && s.result !== undefined ? (
              <details className="mt-1">
                <summary className="flex cursor-pointer items-center gap-1 text-xs text-muted-foreground">
                  <ChevronRight className="h-3 w-3" aria-hidden="true" /> Result
                </summary>
                <JsonViewer value={s.result} maxHeight="12rem" className="mt-1" />
              </details>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
