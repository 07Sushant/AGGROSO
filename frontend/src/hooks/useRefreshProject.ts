import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

/** Refresh everything a workspace action can change (project, versions, checklists, runs). */
export function useRefreshProject(projectId: number) {
  const qc = useQueryClient();
  return useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["projects", projectId] });
    void qc.invalidateQueries({ queryKey: ["projects"], exact: true });
    void qc.invalidateQueries({ queryKey: ["plan-versions"] });
    void qc.invalidateQueries({ queryKey: ["runs"] });
  }, [qc, projectId]);
}
