import { useOutletContext } from "react-router-dom";
import type { PlanVersion, ProjectDetail } from "@/api/types";

export type StepId = "inputs" | "agent" | "plan" | "dry-run" | "approve" | "execute" | "history";

export interface StepState {
  id: StepId;
  label: string;
  done: boolean;
  locked: boolean;
  lockReason: string | null;
}

export interface WorkspaceContext {
  project: ProjectDetail;
  versions: PlanVersion[];
  /** The version the Plan / Dry run / Approve steps work on (defaults to the latest). */
  selectedVersion: PlanVersion | null;
  selectVersion: (id: number) => void;
  steps: StepState[];
}

export function useWorkspace(): WorkspaceContext {
  return useOutletContext<WorkspaceContext>();
}

export function computeSteps(project: ProjectDetail, selected: PlanVersion | null, hasDryRunForSelected: boolean): StepState[] {
  const hasVersion = project.version_count > 0;
  const approved = project.approved_version !== null;
  const run = project.active_run;
  return [
    { id: "inputs", label: "Inputs", done: true, locked: false, lockReason: null },
    { id: "agent", label: "Agent", done: hasVersion, locked: false, lockReason: null },
    { id: "plan", label: "Plan", done: hasVersion, locked: false, lockReason: null },
    {
      id: "dry-run",
      label: "Dry run",
      done: hasDryRunForSelected,
      locked: !selected,
      lockReason: selected ? null : "Create a plan version first: run the agent or load the reference plan.",
    },
    {
      id: "approve",
      label: "Approve",
      done: approved,
      locked: !selected || (!hasDryRunForSelected && selected.status === "DRAFT"),
      lockReason: !selected ? "Create a plan version first." : !hasDryRunForSelected && selected.status === "DRAFT" ? "Run a dry run of this version first." : null,
    },
    {
      id: "execute",
      label: "Execute",
      done: run?.status === "COMPLETED",
      locked: !approved && !run,
      lockReason: !approved && !run ? "A plan version must be approved before it can be executed." : null,
    },
    { id: "history", label: "History", done: false, locked: false, lockReason: null },
  ];
}
