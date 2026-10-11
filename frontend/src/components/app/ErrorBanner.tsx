import { AlertOctagon, RotateCw } from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Failure state (spec §8.4): code + message + request_id linking to the Logs page. */
export function ErrorBanner({
  error,
  onRetry,
  title,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  if (!error) return null;
  const apiErr = error instanceof ApiError ? error : null;
  const code = apiErr?.code ?? "CLIENT_ERROR";
  const message = apiErr?.message ?? (error instanceof Error ? error.message : "Something went wrong.");
  const requestId = apiErr?.requestId ?? null;
  const fieldErrors = apiErr?.fieldErrors ?? [];
  const blockers = Array.isArray(apiErr?.details?.blockers) ? (apiErr?.details?.blockers as string[]) : [];

  return (
    <div role="alert" className={cn("rounded-lg border border-danger/40 bg-danger-subtle p-4 text-sm text-danger-strong", className)}>
      <div className="flex flex-wrap items-start gap-3">
        <AlertOctagon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-semibold">
            {title ?? "Request failed"} <span className="font-mono text-xs">[{code}]</span>
          </p>
          <p className="break-words">{message}</p>
          {blockers.length > 0 ? <p>Blocking items: {blockers.join(", ")}</p> : null}
          {fieldErrors.length > 0 ? (
            <ul className="list-disc space-y-0.5 pl-5">
              {fieldErrors.slice(0, 8).map((e, i) => (
                <li key={i}>
                  <span className="font-mono text-xs">{e.path || "(root)"}</span>: {e.message}
                </li>
              ))}
            </ul>
          ) : null}
          {requestId ? (
            <p className="text-xs">
              Request ID:{" "}
              <Link className="font-mono underline underline-offset-2" to={`/logs?request_id=${encodeURIComponent(requestId)}`}>
                {requestId}
              </Link>
            </p>
          ) : null}
        </div>
        {onRetry ? (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RotateCw aria-hidden="true" /> Retry
          </Button>
        ) : null}
      </div>
    </div>
  );
}
