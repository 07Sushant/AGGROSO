import { useEffect, useId, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Destructive confirmation (spec §8.0): always asks for a reason; optionally also asks the user
 * to type a confirmation phrase (the run number for Rollback).
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  reasonLabel = "Reason",
  reasonMinLength = 3,
  typeToConfirm,
  loading,
  error,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  reasonLabel?: string;
  reasonMinLength?: number;
  typeToConfirm?: string;
  loading?: boolean;
  error?: ReactNode;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const reasonId = useId();
  const typedId = useId();

  useEffect(() => {
    if (open) {
      setReason("");
      setTyped("");
    }
  }, [open]);

  const reasonOk = reason.trim().length >= reasonMinLength;
  const typedOk = typeToConfirm === undefined || typed.trim() === typeToConfirm;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription asChild>
            <div>{description}</div>
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (reasonOk && typedOk) onConfirm(reason.trim());
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor={reasonId}>{reasonLabel} (required)</Label>
            <Textarea id={reasonId} value={reason} onChange={(e) => setReason(e.target.value)} aria-invalid={reason.length > 0 && !reasonOk} />
            {!reasonOk ? <p className="text-xs text-muted-foreground">At least {reasonMinLength} characters.</p> : null}
          </div>
          {typeToConfirm !== undefined ? (
            <div className="space-y-1.5">
              <Label htmlFor={typedId}>
                Type <span className="font-mono">{typeToConfirm}</span> to confirm
              </Label>
              <Input id={typedId} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
            </div>
          ) : null}
          {error}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive-solid" disabled={!reasonOk || !typedOk} loading={loading}>
              {confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
