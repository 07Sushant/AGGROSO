import { useQuery } from "@tanstack/react-query";
import { RefreshCw, ScrollText, Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/api/endpoints";
import type { LogLine } from "@/api/types";
import { EmptyState } from "@/components/app/EmptyState";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { JsonViewer } from "@/components/app/JsonViewer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingBlock, TableScroll } from "@/components/ui/misc";
import { qk } from "@/lib/queryKeys";
import { cn, formatDateTime } from "@/lib/utils";

const LEVEL: Record<string, string> = {
  error: "text-danger-strong",
  critical: "text-danger-strong",
  warning: "text-warning-strong",
  info: "text-foreground",
  debug: "text-muted-foreground",
};

/** Ring-buffer logs (same lines as stdout, redacted, alias-only), filterable by request id / event. */
export function LogsPage() {
  const [params, setParams] = useSearchParams();
  const requestId = params.get("request_id") ?? "";
  const event = params.get("event") ?? "";
  const [draftRequestId, setDraftRequestId] = useState(requestId);
  const [draftEvent, setDraftEvent] = useState(event);
  const logs = useQuery({ queryKey: qk.logs(requestId, event), queryFn: () => api.logs({ request_id: requestId || undefined, event: event || undefined }) });

  const apply = (rid: string, ev: string) => {
    const next = new URLSearchParams();
    if (rid.trim()) next.set("request_id", rid.trim());
    if (ev.trim()) next.set("event", ev.trim());
    setParams(next);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Logs</h1>
        <p className="text-sm text-muted-foreground">Recent structured log lines from the backend (newest first). Every error banner links here by its request ID.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Filter</CardTitle>
          <CardDescription>Request ID matches exactly; event matches by prefix or name, as the server defines.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              apply(draftRequestId, draftEvent);
            }}
          >
            <div className="min-w-0 flex-1 space-y-1.5 sm:max-w-sm">
              <Label htmlFor="f-rid">Request ID</Label>
              <Input id="f-rid" value={draftRequestId} onChange={(e) => setDraftRequestId(e.target.value)} className="font-mono text-xs" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5 sm:max-w-xs">
              <Label htmlFor="f-event">Event</Label>
              <Input id="f-event" value={draftEvent} onChange={(e) => setDraftEvent(e.target.value)} placeholder="e.g. request.error" />
            </div>
            <Button type="submit">
              <Search aria-hidden="true" /> Apply
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDraftRequestId("");
                setDraftEvent("");
                apply("", "");
              }}
            >
              Clear
            </Button>
            <Button type="button" variant="ghost" onClick={() => void logs.refetch()} loading={logs.isFetching}>
              <RefreshCw aria-hidden="true" /> Refresh
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-5">
          {logs.isPending ? (
            <LoadingBlock rows={8} label="Loading logs" />
          ) : logs.isError ? (
            <ErrorBanner error={logs.error} onRetry={() => void logs.refetch()} title="Could not load logs" />
          ) : logs.data.items.length === 0 ? (
            <EmptyState
              icon={ScrollText}
              message={requestId || event ? "No log lines match this filter. The buffer keeps only the most recent lines." : "No log lines yet."}
              action={
                requestId || event ? (
                  <Button variant="outline" onClick={() => apply("", "")}>
                    Clear filter
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <LogTable items={logs.data.items} onFilterRequest={(rid) => {
              setDraftRequestId(rid);
              apply(rid, draftEvent);
            }} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function LogTable({ items, onFilterRequest }: { items: LogLine[]; onFilterRequest: (rid: string) => void }) {
  return (
    <TableScroll className="max-h-[36rem] rounded-md border border-border">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Log lines</caption>
        <thead className="sticky top-0 bg-muted text-xs text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2">Time</th>
            <th scope="col" className="px-3 py-2">Level</th>
            <th scope="col" className="px-3 py-2">Logger</th>
            <th scope="col" className="px-3 py-2">Event</th>
            <th scope="col" className="px-3 py-2">Request</th>
            <th scope="col" className="px-3 py-2">Details</th>
          </tr>
        </thead>
        <tbody>
          {items.map((line, i) => {
            const { ts, timestamp, level, logger, event, request_id, ...rest } = line;
            const time = (ts ?? timestamp) as string | undefined;
            const summary = [rest.method, rest.path, rest.status, rest.duration_ms !== undefined ? `${String(rest.duration_ms)} ms` : null, rest.code].filter(Boolean).join(" ");
            return (
              <tr key={i} className="border-t border-border align-top">
                <td className="whitespace-nowrap px-3 py-2 text-xs">{formatDateTime(time)}</td>
                <td className={cn("px-3 py-2 text-xs font-medium uppercase", LEVEL[(level ?? "").toLowerCase()] ?? "")}>{level ?? "-"}</td>
                <td className="px-3 py-2 text-xs">{logger ?? "-"}</td>
                <td className="px-3 py-2 font-mono text-xs">{event ?? "-"}</td>
                <td className="px-3 py-2">
                  {request_id ? (
                    <button type="button" className="font-mono text-xs text-primary hover:underline" onClick={() => onFilterRequest(String(request_id))} title="Filter by this request">
                      {String(request_id).slice(0, 12)}
                    </button>
                  ) : (
                    "-"
                  )}
                </td>
                <td className="px-3 py-2">
                  <details>
                    <summary className="cursor-pointer text-xs text-muted-foreground">{summary || "fields"}</summary>
                    <JsonViewer value={line} maxHeight="14rem" className="mt-1 min-w-[18rem]" />
                  </details>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableScroll>
  );
}
