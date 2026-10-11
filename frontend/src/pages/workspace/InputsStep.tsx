import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api } from "@/api/endpoints";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { JsonViewer } from "@/components/app/JsonViewer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingBlock, TableScroll } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { qk } from "@/lib/queryKeys";
import { useWorkspace } from "./context";

const PAGE = 20;

export function SimpleTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: ReactNode[][] }) {
  return (
    <TableScroll className="max-h-[28rem] rounded-md border border-border">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 bg-muted text-xs text-muted-foreground">
          <tr>
            {headers.map((h) => (
              <th key={h} scope="col" className="whitespace-nowrap px-3 py-2 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border align-top">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}

export function InputsStep() {
  const { project } = useWorkspace();
  const [offset, setOffset] = useState(0);
  const source = useQuery({ queryKey: qk.sourceSchema, queryFn: api.sourceSchema, staleTime: Infinity });
  const target = useQuery({ queryKey: qk.targetSchema, queryFn: api.targetSchema, staleTime: Infinity });
  const transforms = useQuery({ queryKey: qk.transforms, queryFn: api.transforms, staleTime: Infinity });
  const records = useQuery({
    queryKey: qk.sourceRecords(project.id, offset, PAGE),
    queryFn: () => api.sourceRecords(project.id, PAGE, offset),
    placeholderData: keepPreviousData,
  });

  const fieldNames = source.data?.fields.map((f) => f.name) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Inputs</CardTitle>
        <CardDescription>The fixed source and target schemas, this project's frozen sample records and the transform registry.</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="source">
          <TabsList>
            <TabsTrigger value="source">Source schema</TabsTrigger>
            <TabsTrigger value="target">Target schema</TabsTrigger>
            <TabsTrigger value="records">Sample records</TabsTrigger>
            <TabsTrigger value="transforms">Transforms</TabsTrigger>
          </TabsList>

          <TabsContent value="source">
            {source.isPending ? <LoadingBlock /> : source.isError ? <ErrorBanner error={source.error} onRetry={() => void source.refetch()} /> : (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  <span className="font-mono text-foreground">{source.data.entity}</span>: {source.data.description} Primary key{" "}
                  <span className="font-mono">{source.data.primary_key}</span>.
                </p>
                <SimpleTable
                  caption="Source schema fields"
                  headers={["Field", "Type", "Nullable", "Description"]}
                  rows={source.data.fields.map((f) => [<span className="font-mono text-xs">{f.name}</span>, f.type, f.nullable ? "yes" : "no", f.description ?? ""])}
                />
              </div>
            )}
          </TabsContent>

          <TabsContent value="target">
            {target.isPending ? <LoadingBlock /> : target.isError ? <ErrorBanner error={target.error} onRetry={() => void target.refetch()} /> : (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  <span className="font-mono text-foreground">{target.data.entity}</span>: {target.data.description}
                </p>
                <SimpleTable
                  caption="Target schema columns"
                  headers={["Column", "Type", "Required", "Unique", "Rules", "Description"]}
                  rows={target.data.columns.map((c) => [
                    <span className="font-mono text-xs">{c.name}</span>,
                    c.type,
                    c.required ? "yes" : "no",
                    c.unique ? "yes" : "no",
                    <span className="font-mono text-[11px]">
                      {[
                        Array.isArray(c.enum) ? `enum: ${c.enum.join(", ")}` : null,
                        c.regex ? `regex: ${c.regex}` : null,
                        typeof c.minimum === "number" ? `min: ${c.minimum}` : null,
                        typeof c.max_length === "number" ? `max length: ${c.max_length}` : null,
                      ]
                        .filter(Boolean)
                        .join("; ") || "-"}
                    </span>,
                    c.description ?? "",
                  ])}
                />
              </div>
            )}
          </TabsContent>

          <TabsContent value="records">
            {records.isPending ? <LoadingBlock rows={6} /> : records.isError ? <ErrorBanner error={records.error} onRetry={() => void records.refetch()} /> : (
              <div className="space-y-2">
                <SimpleTable
                  caption="Sample source records"
                  headers={["Row", ...fieldNames]}
                  rows={records.data.items.map((r) => [r.row_number, ...fieldNames.map((f) => <span className="whitespace-nowrap font-mono text-[11px]">{r.payload[f] ?? ""}</span>)])}
                />
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>
                    Rows {offset + 1}-{Math.min(offset + PAGE, records.data.total)} of {records.data.total}
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                      Previous
                    </Button>
                    <Button variant="outline" size="sm" disabled={offset + PAGE >= records.data.total} onClick={() => setOffset(offset + PAGE)}>
                      Next
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="transforms">
            {transforms.isPending ? <LoadingBlock /> : transforms.isError ? <ErrorBanner error={transforms.error} onRetry={() => void transforms.refetch()} /> : (
              <div className="grid gap-3 md:grid-cols-2">
                {transforms.data.map((t) => (
                  <div key={t.name} className="min-w-0 rounded-md border border-border p-3">
                    <p className="font-mono text-sm font-medium">{t.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {t.input_type} → {t.output_type}
                    </p>
                    <p className="mt-1 text-sm">{t.description}</p>
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-muted-foreground">Parameter schema</summary>
                      <JsonViewer value={t.params_schema} maxHeight="10rem" className="mt-1" />
                    </details>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
