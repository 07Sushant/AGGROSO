import { useQuery } from "@tanstack/react-query";
import { Database, FileStack } from "lucide-react";
import { useMemo, useState } from "react";
import { Outlet, useParams } from "react-router-dom";
import { api } from "@/api/endpoints";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { StatusBadge } from "@/components/app/StatusBadge";
import { Stepper } from "@/components/app/Stepper";
import { Skeleton } from "@/components/ui/misc";
import { qk } from "@/lib/queryKeys";
import { computeSteps, type WorkspaceContext } from "./context";

export function ProjectLayout() {
  const projectId = Number(useParams().projectId);
  const project = useQuery({ queryKey: qk.project(projectId), queryFn: () => api.project(projectId), enabled: Number.isFinite(projectId) });
  const versions = useQuery({ queryKey: qk.planVersions(projectId), queryFn: () => api.planVersions(projectId), enabled: Number.isFinite(projectId) });
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const selectedVersion = useMemo(() => {
    const list = versions.data ?? [];
    return list.find((v) => v.id === selectedId) ?? list[0] ?? null;
  }, [versions.data, selectedId]);

  const checklist = useQuery({
    queryKey: qk.checklist(selectedVersion?.id ?? 0),
    queryFn: () => api.checklist(selectedVersion!.id),
    enabled: !!selectedVersion,
  });

  if (project.isPending || versions.isPending) {
    return (
      <div className="space-y-3" role="status" aria-live="polite">
        <span className="sr-only">Loading project</span>
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (project.isError || versions.isError) {
    return (
      <ErrorBanner
        error={project.error ?? versions.error}
        title="Could not load the project"
        onRetry={() => {
          void project.refetch();
          void versions.refetch();
        }}
      />
    );
  }

  const p = project.data;
  const steps = computeSteps(p, selectedVersion, !!checklist.data?.dry_run);
  const ctx: WorkspaceContext = { project: p, versions: versions.data, selectedVersion, selectVersion: setSelectedId, steps };
  const activeVersion = p.approved_version ?? p.latest_version;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold">{p.name}</h1>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Database className="h-4 w-4" aria-hidden="true" /> Dataset <span className="font-mono text-xs text-foreground">{p.dataset_key}</span>
            </span>
            <span className="inline-flex items-center gap-1">
              <FileStack className="h-4 w-4" aria-hidden="true" /> {p.record_count} source records
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Active version</span>
          {activeVersion ? (
            <>
              <span className="font-medium">v{activeVersion.version_number}</span>
              <StatusBadge status={p.approved_version ? "APPROVED" : (p.latest_version?.status ?? "DRAFT")} />
            </>
          ) : (
            <span className="text-muted-foreground">none yet</span>
          )}
        </div>
      </header>
      <Stepper basePath={`/projects/${p.id}`} steps={steps} />
      <Outlet context={ctx} />
    </div>
  );
}
