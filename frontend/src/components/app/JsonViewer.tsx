import { Copy } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function JsonViewer({ value, className, maxHeight = "20rem" }: { value: unknown; className?: string; maxHeight?: string }) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <div className={cn("relative rounded-md border border-border bg-muted", className)}>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="absolute right-1 top-1"
        onClick={() => {
          void navigator.clipboard?.writeText(text).then(
            () => toast.success("Copied to clipboard"),
            () => toast.error("Could not copy"),
          );
        }}
      >
        <Copy aria-hidden="true" /> Copy
      </Button>
      <pre className="overflow-auto p-3 pr-20 font-mono text-xs leading-5" style={{ maxHeight }}>
        {text}
      </pre>
    </div>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono text-xs", className)}>{children}</span>;
}
