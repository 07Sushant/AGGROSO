import { useMutation, useQuery } from "@tanstack/react-query";
import { ShieldCheck, Undo2, XCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/endpoints";
import { ApprovalChecklistView } from "@/components/app/ApprovalChecklistView";
import { ConfirmDialog } from "@/components/app/ConfirmDialog";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { StatusBadge } from "@/components/app/StatusBadge";
import { LockedNotice } from "@/components/app/Stepper";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingBlock } from "@/components/ui/misc";
import { useRefreshProject } from "@/hooks/useRefreshProject";
import { useAuth } from "@/lib/auth";
import { qk } from "@/lib/queryKeys";
import { shortHash } from "@/lib/utils";
import { useWorkspace } from "./context";

export function ApproveStep() {
  const { project, selectedVersion, steps } = useWorkspace();
  const { user } = useAuth();
  const refresh = useRefreshProject(project.id);
  const lock = steps.find((s) => s.id === "approve")!;
  const [comment, setComment] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [revokeOpen, setRevokeOpen] = useState(false);

  const checklist = useQuery({
    queryKey: qk.checklist(selectedVersion?.id ?? 0),
    queryFn: () => api.checklist(selectedVersion!.id),
    enabled: !!selectedVersion,
  });
  const diff = useQuery({
    queryKey: qk.diff(selectedVersion?.id ?? 0, null),
    queryFn: () => api.diff(selectedVersion!.id),
    enabled: !!selectedVersion?.parent_version_id,
  });

  const approve = useMutation({
    mutationFn: () => api.approve(selectedVersion!.id, comment.trim()),
    onSuccess: (r) => {
      toast.success(`v${r.version.version_number} approved${r.approval.self_approved ? " (self-approved)" : ""}`);
      setComment("");
      refresh();
    },
  });
  const reject = useMutation({
    mutationFn: (reason: string) => api.reject(selectedVersion!.id, reason),
    onSuccess: (r) => {
      toast.success(`v${r.version.version_number} rejected`);
      setRejectOpen(false);
      refresh();
    },
  });
  const revoke = useMutation({
    mutationFn: (reason: string) => api.revoke(selectedVersion!.id, reason),
    onSuccess: (r) => {
      toast.success(`Approval of v${r.version.version_number} revoked`);
      setRevokeOpen(false);
      refresh();
    },
  });

  if (!selectedVersion) return <LockedNotice reason={lock.lockReason} />;
  const isApprover = user?.role === "approver";
  const v = selectedVersion;

  return (
    <div className="space-y-4">
      <LockedNotice reason={lock.lockReason} />
      {/* Decision panel: indigo outline + ShieldCheck (visually distinct from the Execute operation panel). */}
      <section aria-labelledby="decision-h" className="rounded-lg border-2 border-primary bg-surface p-5 shadow-sm">
        <h2 id="decision-h" className="flex flex-wrap items-center gap-2 text-base font-semibold text-primary">
          <ShieldCheck className="h-5 w-5" aria-hidden="true" /> Approval decision for v{v.version_number} <StatusBadge status={v.status} />
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Approval binds to this exact plan hash, its dry run result and the source checksum. If any of them change, execution is blocked until it is approved again.
        </p>

        {checklist.isPending ? (
          <div className="mt-4">
            <LoadingBlock rows={5} label="Loading checklist" />
          </div>
        ) : checklist.isError ? (
          <ErrorBanner className="mt-4" error={checklist.error} onRetry={() => void checklist.refetch()} />
        ) : (
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            <ApprovalChecklistView checklist={checklist.data} />
            <div className="space-y-3">
              <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 rounded-md bg-muted p-3 text-sm">
                <dt className="text-muted-foreground">Version</dt>
                <dd>
                  v{v.version_number} ({v.author_type === "agent" ? "agent" : (v.author_username ?? "human")})
                </dd>
                <dt className="text-muted-foreground">Plan hash</dt>
                <dd className="break-all font-mono text-xs">{shortHash(checklist.data.content_hash, 24)}</dd>
                <dt className="text-muted-foreground">Dry run</dt>
                <dd className="break-all font-mono text-xs">
                  {checklist.data.dry_run ? `#${checklist.data.dry_run.id} · ${shortHash(checklist.data.dry_run.result_hash, 16)}` : "none"}
                </dd>
                {checklist.data.dry_run ? (
                  <>
                    <dt className="text-muted-foreground">Counts</dt>
                    <dd className="tabular-nums">
                      {checklist.data.dry_run.counts.source} source / {checklist.data.dry_run.counts.transformed} transformed / {checklist.data.dry_run.counts.accepted} accepted /{" "}
                      {checklist.data.dry_run.counts.rejected} rejected
                    </dd>
                  </>
                ) : null}
                {diff.data ? (
                  <>
                    <dt className="text-muted-foreground">Changes vs parent</dt>
                    <dd>
                      {diff.data.summary.changed + diff.data.summary.added + diff.data.summary.removed} of{" "}
                      {diff.data.summary.changed + diff.data.summary.unchanged + diff.data.summary.removed} mappings changed
                    </dd>
                  </>
                ) : null}
              </dl>
              {checklist.data.unanswered_question_ids.length || checklist.data.unacknowledged_high_risk_ids.length ? (
                <p className="text-xs">
                  <Link className="text-primary hover:underline" to={`/projects/${project.id}/plan`}>
                    Answer questions and acknowledge risks on the Plan step
                  </Link>
                </p>
              ) : null}

              {v.status === "DRAFT" ? (
                <form
                  className="space-y-3"
                  onSubmit={(e) => {
                    e.preventDefault();
                    approve.mutate();
                  }}
                >
                  <div className="space-y-1.5">
                    <Label htmlFor="approve-comment">Comment (optional)</Label>
                    <Textarea id="approve-comment" value={comment} onChange={(e) => setComment(e.target.value)} disabled={!isApprover} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button type="submit" disabled={!isApprover || !checklist.data.can_approve} loading={approve.isPending}>
                      <ShieldCheck aria-hidden="true" /> Approve v{v.version_number}
                    </Button>
                    <Button type="button" variant="destructive" disabled={!isApprover} onClick={() => setRejectOpen(true)}>
                      <XCircle aria-hidden="true" /> Reject
                    </Button>
                  </div>
                  {!isApprover ? (
                    <p className="text-xs text-muted-foreground">Only the approver role can approve or reject. Sign in as approver.</p>
                  ) : !checklist.data.can_approve ? (
                    <p className="text-xs text-muted-foreground">Approve is disabled until every blocking check passes.</p>
                  ) : null}
                </form>
              ) : v.status === "APPROVED" ? (
                <div className="space-y-2">
                  <p className="text-sm">
                    This version is approved.{" "}
                    <Link className="text-primary hover:underline" to={`/projects/${project.id}/execute`}>
                      Go to Execute
                    </Link>
                  </p>
                  <Button variant="destructive" disabled={!isApprover} onClick={() => setRevokeOpen(true)}>
                    <Undo2 aria-hidden="true" /> Revoke approval
                  </Button>
                  {!isApprover ? <p className="text-xs text-muted-foreground">Only the approver role can revoke.</p> : null}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">This version is {v.status}; no decision is possible.</p>
              )}
              <ErrorBanner error={approve.error} title="Approval failed" />
            </div>
          </div>
        )}
      </section>

      <ConfirmDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        title={`Reject v${v.version_number}?`}
        description="The version becomes REJECTED and can no longer be approved. Create a new version to continue."
        confirmLabel="Reject version"
        reasonLabel="Comment"
        reasonMinLength={1}
        loading={reject.isPending}
        error={<ErrorBanner error={reject.error} />}
        onConfirm={(reason) => reject.mutate(reason)}
      />
      <ConfirmDialog
        open={revokeOpen}
        onOpenChange={setRevokeOpen}
        title={`Revoke approval of v${v.version_number}?`}
        description="The version returns to DRAFT and cannot be executed until it is approved again. Not possible while a run is active."
        confirmLabel="Revoke approval"
        reasonLabel="Comment"
        reasonMinLength={1}
        loading={revoke.isPending}
        error={<ErrorBanner error={revoke.error} />}
        onConfirm={(reason) => revoke.mutate(reason)}
      />
    </div>
  );
}
