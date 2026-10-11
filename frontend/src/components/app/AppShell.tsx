import { Bot, ChevronRight, FolderKanban, ImageUp, Loader2, LogOut, ScrollText } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import type { AiStatus } from "@/api/types";
import { AiBanner } from "@/components/app/AiBanner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHealth, useServerWake } from "@/hooks/useServerStatus";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/schema-import", label: "Schema import", icon: ImageUp },
  { to: "/logs", label: "Logs", icon: ScrollText },
];

const PILL: Record<AiStatus, { label: string; cls: string; hint: string }> = {
  primary: { label: "AI: Primary", cls: "bg-success-subtle text-success-strong border-success/30", hint: "The main AI service is answering." },
  backup: { label: "AI: Backup", cls: "bg-warning-subtle text-warning-strong border-warning/30", hint: "A backup AI is answering; responses may be slower." },
  degraded: { label: "AI: Degraded", cls: "bg-warning-subtle text-warning-strong border-warning/30", hint: "AI status is being re-checked." },
  down: { label: "AI: Down", cls: "bg-danger-subtle text-danger-strong border-danger/30", hint: "No AI is available; the deterministic workflow still works." },
  mock: { label: "AI: Mock", cls: "bg-muted text-foreground border-border", hint: "Scripted test AI (mock mode)." },
};

export function AiStatusPill({ status }: { status: AiStatus | undefined }) {
  if (!status) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
        <Bot className="h-3.5 w-3.5" aria-hidden="true" /> AI: checking
      </span>
    );
  }
  const p = PILL[status];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", p.cls)}>
          <Bot className="h-3.5 w-3.5" aria-hidden="true" /> {p.label}
        </span>
      </TooltipTrigger>
      <TooltipContent>{p.hint}</TooltipContent>
    </Tooltip>
  );
}

function Breadcrumb() {
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);
  const crumbs: { label: string; to: string }[] = [];
  let acc = "";
  for (const part of parts) {
    acc += `/${part}`;
    const label = /^\d+$/.test(part) ? `#${part}` : part.replace(/-/g, " ");
    crumbs.push({ label: label.charAt(0).toUpperCase() + label.slice(1), to: acc });
  }
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1 text-sm text-muted-foreground">
        {crumbs.map((c, i) => (
          <Fragment key={c.to}>
            {i > 0 ? <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" /> : null}
            <li className="truncate">
              {i === crumbs.length - 1 ? (
                <span aria-current="page" className="font-medium text-foreground">
                  {c.label}
                </span>
              ) : (
                <Link to={c.to} className="hover:text-foreground">
                  {c.label}
                </Link>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}

export function WakingIndicator({ waking }: { waking: boolean }) {
  if (!waking) return null;
  return (
    <span role="status" aria-live="polite" className="inline-flex items-center gap-1.5 rounded-full border border-info/30 bg-info-subtle px-2 py-0.5 text-xs text-info-strong">
      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      Waking the server, this can take up to a minute
    </span>
  );
}

function NavItems({ compact }: { compact?: boolean }) {
  return (
    <>
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          title={label}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground",
              compact && "px-2",
            )
          }
        >
          <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className={cn(compact ? "sr-only" : "hidden xl:inline")}>{label}</span>
        </NavLink>
      ))}
    </>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth();
  const health = useHealth();
  const { waking } = useServerWake();
  const aiStatus = health.data?.ai.status;

  return (
    <div className="flex min-h-screen w-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-screen w-16 shrink-0 flex-col border-r border-border bg-surface md:flex xl:w-60">
        <Link to="/projects" className="flex h-14 items-center gap-2 border-b border-border px-4 font-semibold">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs text-primary-foreground">MQ</span>
          <span className="hidden xl:inline">MigrateIQ</span>
        </Link>
        <nav aria-label="Main" className="flex flex-1 flex-col gap-1 p-2">
          <NavItems />
        </nav>
        <div className="border-t border-border p-3">
          <p className="hidden truncate text-sm font-medium xl:block">{user?.username}</p>
          <p className="hidden text-xs capitalize text-muted-foreground xl:block">Role: {user?.role}</p>
          <Button variant="ghost" size="sm" className="mt-2 w-full justify-start px-2" onClick={logout} title="Sign out">
            <LogOut aria-hidden="true" />
            <span className="hidden xl:inline">Sign out</span>
            <span className="sr-only xl:hidden">Sign out</span>
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass sticky top-0 z-40 flex min-h-14 flex-wrap items-center gap-3 border-x-0 border-t-0 px-4 py-2 md:px-6">
          <nav aria-label="Main" className="flex gap-1 md:hidden">
            <NavItems compact />
          </nav>
          <div className="min-w-0 flex-1">
            <Breadcrumb />
          </div>
          <WakingIndicator waking={waking} />
          <AiStatusPill status={aiStatus} />
          <span className="hidden text-xs text-muted-foreground sm:inline md:hidden">
            {user?.username} ({user?.role})
          </span>
          <Button variant="ghost" size="icon" className="md:hidden" onClick={logout} aria-label="Sign out">
            <LogOut aria-hidden="true" />
          </Button>
        </header>
        <main id="main" className="mx-auto w-full min-w-0 max-w-[1440px] flex-1 space-y-4 p-4 md:p-6">
          <AiBanner status={aiStatus} />
          {children ?? <Outlet />}
        </main>
      </div>
    </div>
  );
}
