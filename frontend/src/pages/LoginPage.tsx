import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { WakingIndicator } from "@/components/app/AppShell";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { useServerWake } from "@/hooks/useServerStatus";
import { useAuth } from "@/lib/auth";

const schema = z.object({
  username: z.string().trim().min(1, "Enter a username."),
  password: z.string().min(1, "Enter the password."),
});
type FormValues = z.infer<typeof schema>;

function BrandIcon({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={Math.round(size * 22 / 24)} viewBox="0 0 24 22" aria-hidden="true" focusable="false">
      <rect x="1" y="3" width="8" height="16" rx="1" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <rect x="15" y="3" width="8" height="16" rx="1" fill="var(--miq-accent)" stroke="var(--miq-accent)" strokeWidth="1.5" />
      <path d="M10.5 11h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none" />
    </svg>
  );
}

const DEMO_ACCOUNTS = [
  {
    username: "operator",
    password: "migrateiq-demo",
    label: "Operator",
    desc: "Creates projects, runs agent, executes and retries.",
  },
  {
    username: "approver",
    password: "migrateiq-demo",
    label: "Approver",
    desc: "Approves plans, rolls back runs.",
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

  const fill = (username: string, password: string) => {
    form.setValue("username", username);
    form.setValue("password", password);
    form.clearErrors();
    setError(null);
  };

  return (
    <div className="miq-root">
      {/* Minimal header */}
      <header className="miq-top miq-wrap">
        <Link className="miq-brand" to="/" aria-label="MigrateIQ home">
          <BrandIcon />
          <span>MigrateIQ</span>
        </Link>
        <Link to="/" className="miq-link" style={{ fontSize: "0.9375rem" }}>← Back to overview</Link>
      </header>

      <main className="miq-wrap">
        <div className="miq-login-wrap">
          <div className="miq-login-head">
            <WakingIndicator waking={waking} />
            <h1 className="miq-login-h">Sign in</h1>
            <p className="miq-login-sub">Use a demo account below, or enter credentials manually.</p>
          </div>

          {/* Quick-fill demo cards */}
          <div className="miq-demo-accounts">
            <p className="miq-demo-label">Demo accounts — click to fill</p>
            <div className="miq-demo-cards">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.username}
                  type="button"
                  className="miq-demo-card"
                  onClick={() => fill(a.username, a.password)}
                  aria-label={`Fill credentials for ${a.label}`}
                >
                  <span className="miq-demo-card-title">{a.label}</span>
                  <span className="miq-demo-card-desc">{a.desc}</span>
                  <span className="miq-demo-card-cred">{a.username} / {a.password}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Form */}
          <form
            style={{ marginTop: "2rem", paddingTop: "1.75rem", borderTop: "1px solid var(--miq-rule)" }}
            onSubmit={onSubmit}
            noValidate
          >
            <div className="miq-field">
              <label className="miq-label" htmlFor="username">Username</label>
              <input
                id="username"
                className="miq-input"
                autoComplete="username"
                placeholder="operator or approver"
                aria-invalid={!!form.formState.errors.username}
                aria-describedby={form.formState.errors.username ? "username-error" : undefined}
                {...form.register("username")}
              />
              {form.formState.errors.username ? (
                <span id="username-error" className="miq-field-err">{form.formState.errors.username.message}</span>
              ) : null}
            </div>

            <div className="miq-field">
              <label className="miq-label" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                className="miq-input"
                autoComplete="current-password"
                placeholder="migrateiq-demo"
                aria-invalid={!!form.formState.errors.password}
                aria-describedby={form.formState.errors.password ? "password-error" : undefined}
                {...form.register("password")}
              />
              {form.formState.errors.password ? (
                <span id="password-error" className="miq-field-err">{form.formState.errors.password.message}</span>
              ) : null}
            </div>

            {error && !(error instanceof ApiError && error.code === "UNAUTHENTICATED") ? (
              <div style={{ marginBottom: "1rem" }}>
                <ErrorBanner error={error} title="Sign-in failed" />
              </div>
            ) : null}

            <button
              type="submit"
              className="miq-btn miq-login-btn"
              disabled={form.formState.isSubmitting}
              aria-busy={form.formState.isSubmitting}
            >
              {form.formState.isSubmitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </main>

      <footer className="miq-foot miq-wrap">
        <div className="miq-foot-l">
          <span className="miq-brand" style={{ fontSize: "1rem" }}>
            <BrandIcon size={20} />
            <span>MigrateIQ</span>
          </span>
          <span>Expert assessment submission</span>
        </div>
        <div className="miq-foot-r">
          <a href="https://github.com/07Sushant/AGGROSO" target="_blank" rel="noopener noreferrer">GitHub</a>
        </div>
      </footer>
    </div>
  );
}
