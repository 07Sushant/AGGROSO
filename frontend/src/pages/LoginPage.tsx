import { zodResolver } from "@hookform/resolvers/zod";
import { LogIn } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { WakingIndicator } from "@/components/app/AppShell";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
  { username: "operator", role: "Operator: creates projects, runs the agent, dry runs, executes and retries." },
  { username: "approver", role: "Approver: approves or rejects plans and rolls back runs." },
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

  return (
    <main id="main" className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-xs font-semibold text-primary-foreground">MQ</span>
            <CardTitle className="text-lg">MigrateIQ</CardTitle>
          </div>
          <CardDescription>Agentic data migration planner and reconciliation workbench.</CardDescription>
          <WakingIndicator waking={waking} />
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input id="username" autoComplete="username" aria-invalid={!!form.formState.errors.username} aria-describedby="username-error" {...form.register("username")} />
              {form.formState.errors.username ? (
                <p id="username-error" className="text-xs text-danger-strong">
                  {form.formState.errors.username.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete="current-password" aria-invalid={!!form.formState.errors.password} aria-describedby="password-error" {...form.register("password")} />
              {form.formState.errors.password ? (
                <p id="password-error" className="text-xs text-danger-strong">
                  {form.formState.errors.password.message}
                </p>
              ) : null}
            </div>
            {error && !(error instanceof ApiError && error.code === "UNAUTHENTICATED") ? <ErrorBanner error={error} title="Sign-in failed" /> : null}
            <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
              <LogIn aria-hidden="true" /> Sign in
            </Button>
          </form>
          <div className="mt-6 space-y-2 rounded-md border border-border bg-muted p-3 text-xs">
            <p className="font-medium text-foreground">Demo accounts (password in the README and submission remarks)</p>
            {DEMO_ACCOUNTS.map((a) => (
              <div key={a.username} className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-muted-foreground">
                  <span className="font-mono text-foreground">{a.username}</span> - {a.role}
                </span>
                <Button type="button" variant="outline" size="sm" onClick={() => form.setValue("username", a.username, { shouldValidate: true })}>
                  Use {a.username}
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
