import { zodResolver } from "@hookform/resolvers/zod";
import { LogIn, Shield, Wrench } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { WakingIndicator } from "@/components/app/AppShell";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useServerWake } from "@/hooks/useServerStatus";
import { useAuth } from "@/lib/auth";

const schema = z.object({
  username: z.string().trim().min(1, "Enter a username."),
  password: z.string().min(1, "Enter the password."),
});
type FormValues = z.infer<typeof schema>;

const DEMO_ACCOUNTS = [
  {
    username: "operator",
    password: "migrateiq-demo",
    label: "Operator",
    description: "Creates projects, runs agent, executes",
    icon: Wrench,
    color: "text-indigo-600",
    bg: "bg-indigo-50 hover:bg-indigo-100 border-indigo-200",
  },
  {
    username: "approver",
    password: "migrateiq-demo",
    label: "Approver",
    description: "Approves plans, rolls back runs",
    icon: Shield,
    color: "text-emerald-600",
    bg: "bg-emerald-50 hover:bg-emerald-100 border-emerald-200",
  },
];

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { waking } = useServerWake();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { username: "", password: "" } });

  if (user) return <Navigate to="/projects" replace />;
  const from = (location.state as { from?: string } | null)?.from ?? "/projects";

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const u = await login(values.username, values.password);
      toast.success(`Signed in as ${u.username} (${u.role})`);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "UNAUTHENTICATED") {
        form.setError("password", { message: "Invalid username or password." });
      }
      setError(err);
    }
  });

  const fillAccount = (username: string, password: string) => {
    form.setValue("username", username, { shouldValidate: false });
    form.setValue("password", password, { shouldValidate: false });
    form.clearErrors();
    setError(null);
  };

  return (
    <main id="main" className="flex min-h-screen bg-slate-50">
      {/* Left panel — branding */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-slate-900 p-12 text-white">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500 text-sm font-bold text-white">MQ</span>
          <span className="text-xl font-semibold tracking-tight">MigrateIQ</span>
        </div>
        <div className="space-y-6">
          <div>
            <p className="text-sm font-medium uppercase tracking-widest text-indigo-400 mb-3">Agentic Data Migration</p>
            <h1 className="text-4xl font-bold leading-tight text-white">
              Plan, validate and<br />execute migrations<br />with confidence.
            </h1>
          </div>
          <p className="text-slate-400 text-lg leading-relaxed max-w-sm">
            An AI agent proposes your field mappings. Your team reviews, approves and executes — with full rollback support.
          </p>
          <div className="grid grid-cols-2 gap-4 pt-4">
            {[
              { n: "12", label: "Transform rules" },
              { n: "3-layer", label: "Idempotency" },
              { n: "100%", label: "Audit trail" },
              { n: "Live AI", label: "With fallback" },
            ].map((s) => (
              <div key={s.label} className="rounded-lg bg-slate-800 p-4">
                <div className="text-2xl font-bold text-indigo-400">{s.n}</div>
                <div className="text-xs text-slate-400 mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs text-slate-500">MigrateIQ — Expert assessment demo</p>
      </div>

      {/* Right panel — login form */}
      <div className="flex w-full items-center justify-center p-6 lg:w-1/2">
        <div className="w-full max-w-sm space-y-8">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 lg:hidden">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-indigo-600 text-xs font-bold text-white">MQ</span>
            <span className="text-lg font-semibold">MigrateIQ</span>
          </div>

          <div className="space-y-1">
            <WakingIndicator waking={waking} />
            <h2 className="text-2xl font-bold text-slate-900">Sign in</h2>
            <p className="text-sm text-slate-500">Use a demo account below or enter credentials manually.</p>
          </div>

          {/* Quick-fill demo accounts */}
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Demo accounts</p>
            <div className="grid grid-cols-2 gap-3">
              {DEMO_ACCOUNTS.map((a) => {
                const Icon = a.icon;
                return (
                  <button
                    key={a.username}
                    type="button"
                    onClick={() => fillAccount(a.username, a.password)}
                  >
                    <div className={`flex items-center gap-1.5 font-semibold text-sm ${a.color}`}>
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                      {a.label}
                    </div>
                    <span className="text-xs text-slate-500 leading-tight">{a.description}</span>
                    <span className="font-mono text-[11px] text-slate-400">{a.username}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Form */}
          <form className="space-y-4" onSubmit={onSubmit} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                placeholder="operator or approver"
                aria-invalid={!!form.formState.errors.username}
                aria-describedby="username-error"
                {...form.register("username")}
              />
              {form.formState.errors.username ? (
                <p id="username-error" className="text-xs text-red-600">{form.formState.errors.username.message}</p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="migrateiq-demo"
                aria-invalid={!!form.formState.errors.password}
                aria-describedby="password-error"
                {...form.register("password")}
              />
              {form.formState.errors.password ? (
                <p id="password-error" className="text-xs text-red-600">{form.formState.errors.password.message}</p>
              ) : null}
            </div>
            {error && !(error instanceof ApiError && error.code === "UNAUTHENTICATED") ? (
              <ErrorBanner error={error} title="Sign-in failed" />
            ) : null}
            <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
              <LogIn aria-hidden="true" /> Sign in
            </Button>
          </form>
        </div>
      </div>
    </main>
  );
}
