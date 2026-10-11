import { CheckCircle2, Circle, Lock } from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { NativeSelect } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { StepState } from "@/pages/workspace/context";

/** Horizontal stepper; below 768 px it becomes a select (spec §8.0). Keyboard-operable links. */
export function Stepper({ basePath, steps }: { basePath: string; steps: StepState[] }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const current = steps.find((s) => pathname.startsWith(`${basePath}/${s.id}`))?.id ?? "";

  return (
    <>
      <div className="md:hidden">
        <label htmlFor="step-select" className="sr-only">
          Workflow step
        </label>
        <NativeSelect id="step-select" value={current} onChange={(e) => navigate(e.target.value ? `${basePath}/${e.target.value}` : basePath)}>
          <option value="">Overview</option>
          {steps.map((s, i) => (
            <option key={s.id} value={s.id}>
              {i + 1}. {s.label}
              {s.done ? " (done)" : s.locked ? " (locked)" : ""}
            </option>
          ))}
        </NativeSelect>
      </div>
      <nav aria-label="Workflow steps" className="hidden md:block">
        <ol className="flex w-full items-stretch gap-1 overflow-x-auto rounded-lg border border-border bg-surface p-1 shadow-sm">
          {steps.map((s, i) => {
            const isCurrent = s.id === current;
            const Icon = s.done ? CheckCircle2 : s.locked ? Lock : Circle;
            const state = s.done ? "done" : s.locked ? "locked" : isCurrent ? "current" : "available";
            const link = (
              <NavLink
                to={`${basePath}/${s.id}`}
                aria-current={isCurrent ? "step" : undefined}
                aria-label={`Step ${i + 1}: ${s.label} (${state})${s.lockReason ? `. ${s.lockReason}` : ""}`}
                className={cn(
                  "flex min-w-[7rem] flex-1 items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  isCurrent ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                  s.locked && !isCurrent && "text-muted-foreground",
                )}
              >
                <Icon
                  className={cn("h-4 w-4 shrink-0", s.done && !isCurrent && "text-success")}
                  aria-hidden="true"
                />
                <span className="truncate">
                  <span className="mr-1 tabular-nums opacity-70">{i + 1}</span>
                  {s.label}
                </span>
              </NavLink>
            );
            return (
              <li key={s.id} className="flex flex-1">
                {s.lockReason ? (
                  <Tooltip>
                    <TooltipTrigger asChild>{link}</TooltipTrigger>
                    <TooltipContent>{s.lockReason}</TooltipContent>
                  </Tooltip>
                ) : (
                  link
                )}
              </li>
            );
          })}
        </ol>
      </nav>
    </>
  );
}

/** The lock reason is also shown as visible text on the page (spec §8.0). */
export function LockedNotice({ reason }: { reason: string | null }) {
  if (!reason) return null;
  return (
    <div role="status" className="flex items-start gap-2 rounded-lg border border-border bg-muted p-3 text-sm">
      <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <p>
        <span className="font-medium">This step is locked.</span> {reason}
      </p>
    </div>
  );
}
