import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createColumnHelper } from "@tanstack/react-table";
import { AlertTriangle, FolderPlus, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { api } from "@/api/endpoints";
import type { ProjectSummary } from "@/api/types";
import { DataTable } from "@/components/app/DataTable";
import { EmptyState } from "@/components/app/EmptyState";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingBlock } from "@/components/ui/misc";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import { qk } from "@/lib/queryKeys";
import { formatDateTime } from "@/lib/utils";

const col = createColumnHelper<ProjectSummary>();
const columns = [
  col.accessor("name", {
    header: "Name",
    cell: (c) => (
      <Link className="font-medium text-primary hover:underline" to={`/projects/${c.row.original.id}`}>
        {c.getValue()}
      </Link>
    ),
  }),
  col.accessor("dataset_key", { header: "Dataset", cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> }),
  col.accessor("record_count", { header: "Records" }),
  col.accessor("created_by_username", { header: "Created by", cell: (c) => c.getValue() ?? "-" }),
  col.accessor("created_at", { header: "Created", cell: (c) => formatDateTime(c.getValue()) }),
];

export function ProjectsPage() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const projects = useQuery({ queryKey: qk.projects, queryFn: api.projects });
  const canCreate = user?.role === "operator";

  const createButton = (
    <Button onClick={() => setOpen(true)} disabled={!canCreate} title={canCreate ? undefined : "Only the operator role can create projects."}>
      <Plus aria-hidden="true" /> New project
    </Button>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Projects</h1>
          <p className="text-sm text-muted-foreground">Each project is one migration workspace with a frozen source snapshot.</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          {createButton}
          {!canCreate ? <p className="text-xs text-muted-foreground">Only the operator role can create projects.</p> : null}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Migrations</CardTitle>
          <CardDescription>Create your own project; data is isolated per project.</CardDescription>
        </CardHeader>
        <CardContent>
          {projects.isPending ? (
            <LoadingBlock rows={4} label="Loading projects" />
          ) : projects.isError ? (
            <ErrorBanner error={projects.error} onRetry={() => void projects.refetch()} title="Could not load projects" />
          ) : projects.data.length === 0 ? (
            <EmptyState icon={FolderPlus} message="No migrations yet. Create one from a provided dataset." action={createButton} />
          ) : (
            <DataTable columns={columns} data={projects.data} caption="Projects" />
          )}
        </CardContent>
      </Card>

      <NewProjectDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

const projectSchema = z.object({
  name: z.string().trim().min(1, "Give the project a name.").max(120, "120 characters at most."),
  dataset_key: z.string().min(1, "Pick a dataset."),
});
type ProjectForm = z.infer<typeof projectSchema>;

function NewProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const datasets = useQuery({ queryKey: qk.datasets, queryFn: api.datasets, enabled: open });
  const form = useForm<ProjectForm>({ resolver: zodResolver(projectSchema), defaultValues: { name: "", dataset_key: "baseline_60" } });

  const create = useMutation({
    mutationFn: api.createProject,
    onSuccess: (project) => {
      toast.success(`Project "${project.name}" created with ${project.record_count} records`);
      void queryClient.invalidateQueries({ queryKey: qk.projects });
      onOpenChange(false);
      navigate(`/projects/${project.id}`);
    },
    onError: (err) => {
      // Map 422s onto fields (spec §8.4 validation state).
      if (err instanceof ApiError && err.code === "LIMIT_EXCEEDED") {
        form.setError("dataset_key", { type: "LIMIT_EXCEEDED", message: err.message });
      } else if (err instanceof ApiError) {
        for (const fe of err.fieldErrors) {
          const field = fe.path.split(".").pop();
          if (field === "name" || field === "dataset_key") form.setError(field, { message: fe.message });
        }
      }
    },
  });

  useEffect(() => {
    if (open) {
      form.reset({ name: "", dataset_key: "baseline_60" });
      create.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const selectedKey = form.watch("dataset_key");
  const selected = datasets.data?.find((d) => d.key === selectedKey);
  const errors = form.formState.errors;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>Pick a provided dataset. Its records are frozen as this project's source snapshot.</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" noValidate onSubmit={form.handleSubmit((v) => create.mutate(v))}>
          <div className="space-y-1.5">
            <Label htmlFor="project-name">Project name</Label>
            <Input id="project-name" aria-invalid={!!errors.name} aria-describedby="project-name-error" {...form.register("name")} />
            {errors.name ? (
              <p id="project-name-error" className="text-xs text-danger-strong">
                {errors.name.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dataset">Dataset</Label>
            {datasets.isPending ? (
              <LoadingBlock rows={1} label="Loading datasets" />
            ) : datasets.isError ? (
              <ErrorBanner error={datasets.error} onRetry={() => void datasets.refetch()} />
            ) : (
              <Controller
                control={form.control}
                name="dataset_key"
                render={({ field }) => (
                  <Select
                    value={field.value}
                    onValueChange={(v) => {
                      field.onChange(v);
                      form.clearErrors("dataset_key");
                    }}
                  >
                    <SelectTrigger id="dataset" aria-invalid={!!errors.dataset_key} aria-describedby="dataset-help">
                      <SelectValue placeholder="Choose a dataset" />
                    </SelectTrigger>
                    <SelectContent>
                      {datasets.data.map((d) => (
                        <SelectItem key={d.key} value={d.key}>
                          {d.name} ({d.record_count} records{d.within_limit ? "" : ", over the limit"})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            )}
            <div id="dataset-help" className="space-y-1">
              {selected ? <p className="text-xs text-muted-foreground">{selected.description}</p> : null}
              {selected && !selected.within_limit && !errors.dataset_key ? (
                <p className="flex items-center gap-1 text-xs text-warning-strong">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> This dataset exceeds the maximum sample size; the server will reject it.
                </p>
              ) : null}
              {errors.dataset_key ? (
                <p role="alert" className="flex items-center gap-1 text-xs text-danger-strong">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                  {errors.dataset_key.type === "LIMIT_EXCEEDED" ? <span className="font-mono">LIMIT_EXCEEDED:</span> : null} {errors.dataset_key.message}
                </p>
              ) : null}
            </div>
          </div>
          {create.isError && !(create.error instanceof ApiError && ["LIMIT_EXCEEDED", "VALIDATION_ERROR"].includes(create.error.code)) ? (
            <ErrorBanner error={create.error} />
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create project
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
