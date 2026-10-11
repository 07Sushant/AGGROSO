import { Play } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import type { PlanStatus, RunStatus } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { newIdempotencyKey } from "@/lib/utils";

export interface ExecutePanelProps {
  version: { id: number; version_number: number; status: PlanStatus } | null;
  isOperator: boolean;
  activeRun: { id: number; status: RunStatus } | null;
  faultInjectionEnabled: boolean;
  pending?: boolean;
  error?: ReactNode;
  onExecute: (idempotencyKey: string, simulateFailureAfter: number | null) => void;
}

export function executeBlockReason({ version, isOperator, activeRun }: Pick<ExecutePanelProps, "version" | "isOperator" | "activeRun">): string | null {
  if (!version) return "There is no plan version yet.";
  if (version.status !== "APPROVED") return `v${version.version_number} is ${version.status}. Only an APPROVED version can be executed.`;
  if (!isOperator) return "Only the operator role can execute. Sign in as operator.";
  if (activeRun) return `Run #${activeRun.id} is ${activeRun.status}. Roll it back before executing again (one active run per project).`;
  return null;
}

/** Solid primary "operation" panel with a Play icon (spec §8.0). */
export function ExecutePanel(props: ExecutePanelProps) {
  const { version, faultInjectionEnabled, pending, error, onExecute } = props;
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [failAfter, setFailAfter] = useState("");
  const failId = useId();
  const reason = executeBlockReason(props);
  const failValue = failAfter.trim() === "" ? null : Number(failAfter);
  const failInvalid = failValue !== null && (!Number.isInteger(failValue) || failValue < 1);

  return (
    <section aria-labelledby="execute-h" className="rounded-lg bg-primary p-5 text-primary-foreground shadow-sm">
      <h2 id="execute-h" className="flex items-center gap-2 text-base font-semibold">
        <Play className="h-5 w-5" aria-hidden="true" /> Execute {version ? `v${version.version_number}` : ""}
      </h2>
      <p className="mt-1 text-sm opacity-90">
        Writes the approved dry run's accepted records into the target store, in chunks of 100. Retries never create duplicates.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          className="border-primary-foreground/40 bg-primary-foreground text-primary hover:bg-primary-foreground/90"
          disabled={!!reason}
          loading={pending}
          onClick={() => {
            // A fresh Idempotency-Key once per dialog opening (spec §6.5).
            setKey(newIdempotencyKey());
            setFailAfter("");
            setOpen(true);
          }}
        >
          <Play aria-hidden="true" /> Execute
        </Button>
        {reason ? <p className="text-sm opacity-90">{reason}</p> : null}
      </div>
      {error ? <div className="mt-3">{error}</div> : null}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Execute v{version?.version_number}?</DialogTitle>
            <DialogDescription>
              This writes rows to the target store. If the request is repeated (for example a double click), the same key returns the same run instead of starting a second one.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (failInvalid) return;
              onExecute(key, failValue);
              setOpen(false);
            }}
          >
            <p className="text-xs text-muted-foreground">
              Idempotency-Key <span className="break-all font-mono text-foreground">{key}</span>
            </p>
            {faultInjectionEnabled ? (
              <div className="space-y-1.5 rounded-md border border-warning/40 bg-warning-subtle p-3">
                <Label htmlFor={failId} className="text-warning-strong">
                  Demo: simulate a failure after N records (optional)
                </Label>
                <Input id={failId} inputMode="numeric" value={failAfter} onChange={(e) => setFailAfter(e.target.value)} placeholder="e.g. 30" aria-invalid={failInvalid} />
                <p className="text-xs text-warning-strong">
                  {failInvalid ? "Enter a whole number of at least 1." : "The run fails after this many records are committed; use Retry to finish it."}
                </p>
              </div>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={failInvalid}>
                <Play aria-hidden="true" /> Execute now
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
