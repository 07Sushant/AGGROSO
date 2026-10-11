import { useCallback, useRef, useState } from "react";
import { Link } from "react-router-dom";

function BrandIcon({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={Math.round(size * 22 / 24)} viewBox="0 0 24 22" aria-hidden="true" focusable="false">
      <rect x="1" y="3" width="8" height="16" rx="1" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <rect x="15" y="3" width="8" height="16" rx="1" fill="var(--miq-accent)" stroke="var(--miq-accent)" strokeWidth="1.5" />
      <path d="M10.5 11h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none" />
    </svg>
  );
}

const AUTHOR_LINKS = [
  {
    href: "https://sushant.enally.in/",
    label: "sushant.enally.in",
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/>
      </svg>
    ),
  },
  {
    href: "https://github.com/07Sushant",
    label: "07Sushant",
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"/>
      </svg>
    ),
  },
  {
    href: "https://www.linkedin.com/in/07sushant/",
    label: "07sushant",
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
      </svg>
    ),
  },
];

function AuthorCredit({ neon = false }: { neon?: boolean }) {
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback(() => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpen(true);
  }, []);

  const hide = useCallback(() => {
    closeTimer.current = setTimeout(() => setOpen(false), 180);
  }, []);

  return (
    <div
      className={`miq-author-credit${neon ? " miq-author-credit-neon" : ""}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <img
        src="https://avatars.githubusercontent.com/u/93951120?v=4"
        alt="Sushant Kumar — hover to see profiles"
        className="miq-author-avatar"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && setOpen((v) => !v)}
      />
      {open && (
        <div className="miq-author-popup" role="tooltip" onMouseEnter={show} onMouseLeave={hide}>
          <span className="miq-author-name">Built by Sushant Kumar</span>
          {AUTHOR_LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              target="_blank"
              rel="noopener noreferrer"
              className="miq-author-link"
            >
              {l.icon}
              {l.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="miq-root">
      {/* Header */}
      <header className="miq-top miq-wrap">
        <a className="miq-brand" href="#top" aria-label="MigrateIQ home">
          <BrandIcon />
          <span>MigrateIQ</span>
        </a>
        <nav className="miq-nav" aria-label="Primary">
          <a href="#how">How it works</a>
          <a href="#features">Features</a>
        </nav>
        <Link className="miq-btn miq-btn-sm" to="/login">Open app</Link>
        <AuthorCredit neon />
      </header>

      <main id="top">
        {/* Hero */}
        <section className="miq-hero miq-wrap" aria-labelledby="hero-h">
          <h1 className="miq-h1" id="hero-h">Move data like a control tower</h1>

          <div className="miq-hero-grid">
            <div>
              <p className="miq-lede">
                MigrateIQ is an agentic migration workbench. The <strong>AI Architect</strong> proposes the plan. The <strong>Rehearsal</strong> proves it works. The <strong>Security Guard</strong> approves it. The <strong>Move &amp; Audit</strong> executes it, with full rollback.
              </p>
              <div className="miq-actions">
                <Link className="miq-btn" to="/login">Try live demo</Link>
                <a className="miq-link" href="#how">See how it works</a>
              </div>
            </div>

            {/* Flow figure */}
            <figure className="miq-flow">
              <div className="miq-flow-grid">
                <div className="miq-tbl">
                  <p className="miq-tbl-h">Source table</p>
                  <ul>
                    {["cust_id", "full_name", "email_addr", "signup_dt", "credit_limit", "status_cd"].map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </div>
                <div className="miq-arch" aria-hidden="true">
                  <div className="miq-arch-inner">
                    <span className="miq-node">AI</span>
                    <span className="miq-arch-t">The Architect</span>
                    <span className="miq-arch-s">Proposes mappings</span>
                  </div>
                </div>
                <div className="miq-tbl">
                  <p className="miq-tbl-h">Target table</p>
                  <ul>
                    {["legacy_id", "first_name", "last_name", "email", "phone_e164", "signup_date", "status"].map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </div>
              </div>
              <div className="miq-flow-foot">
                <span className="miq-chip">Approved &amp; Executed</span>
              </div>
              <figcaption className="miq-flow-cap">Airport security for database migrations</figcaption>
            </figure>
          </div>

          {/* Stats */}
          <dl className="miq-stats">
            {[
              { n: "139", l: "Tests passing" },
              { n: "500", l: "Max records" },
              { n: "3-layer", l: "Idempotency" },
              { n: "Live AI", l: "With failover" },
            ].map((s) => (
              <div className="miq-stat" key={s.l}>
                <dt>{s.l}</dt>
                <dd>{s.n}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* How it works */}
        <section className="miq-band miq-wrap" id="how" aria-labelledby="how-h">
          <div className="miq-sec">
            <p className="miq-rail">How it works</p>
            <div>
              <h2 className="miq-h2" id="how-h">Think of it as airport security for your data</h2>
              <p className="miq-sub">Every row goes through the full pipeline: proposed, rehearsed, approved, moved and audited.</p>

              <ol className="miq-steps">
                {[
                  {
                    n: "Step 1", k: "AI Agent", title: "The Architect",
                    body: (
                      <p>Looks at the old table format and the new table format. It proposes a plan: &ldquo;Hey, we should split <code className="miq-code">full_name</code> into <code className="miq-code">first_name</code> and <code className="miq-code">last_name</code>, convert currency to cents, and convert dates to ISO standard.&rdquo; It also spots risks and asks questions when it&rsquo;s unsure.</p>
                    ),
                  },
                  {
                    n: "Step 2", k: "Deterministic Dry Run", title: "The Rehearsal",
                    body: <p>Deterministic code tests all 60 records against the plan without touching the real database. It quarantines bad rows and shows evidence for why each was rejected, before a single byte is written.</p>,
                  },
                  {
                    n: "Step 3", k: "Human Approval Gate", title: "The Security Guard",
                    body: <p>In enterprise companies, developers aren&rsquo;t allowed to push data straight to production. An Approver (different person) must review the checklist and approve the cryptographic hash of the plan. The server blocks execution with HTTP 403 until they do.</p>,
                  },
                  {
                    n: "Step 4", k: "Execution & Reconciliation", title: "The Move & Audit",
                    body: <p>Rows are inserted safely. If the server crashes midway, a Retry will never insert duplicate rows. Afterwards, Reconciliation mathematically proves that Source (60) = Accepted (45) + Rejected (15). Full rollback is always available.</p>,
                  },
                ].map((s) => (
                  <li key={s.n}>
                    <div>
                      <span className="miq-step-n">{s.n}</span>
                      <span className="miq-step-k">{s.k}</span>
                    </div>
                    <div className="miq-step-body">
                      <h3 className="miq-h3">{s.title}</h3>
                      {s.body}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        {/* Guarantee */}
        <section className="miq-band miq-wrap" aria-labelledby="g-h">
          <div className="miq-sec">
            <p className="miq-rail">Mathematical guarantee</p>
            <div>
              <p className="miq-eq" id="g-h">
                Source (60){" "}
                <span className="miq-eq-op">=</span>{" "}
                <span className="miq-ok">Accepted (45)</span>{" "}
                <span className="miq-eq-op">+</span>{" "}
                <span className="miq-bad">Rejected (15)</span>
              </p>
              <div className="miq-bar" role="img" aria-label="Of 60 source records, 45 are accepted and 15 are rejected">
                <span className="miq-bar-ok" />
                <span className="miq-bar-bad" />
              </div>
              <div className="miq-bar-labels" aria-hidden="true">
                <span>Accepted 45</span>
                <span>Rejected 15</span>
              </div>
              <p className="miq-note">Reconciliation verifies this invariant on every run, with per-row content hashing.</p>
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="miq-band miq-wrap" id="features" aria-labelledby="f-h">
          <div className="miq-sec">
            <p className="miq-rail">Features</p>
            <div>
              <h2 className="miq-h2" id="f-h">Built for correctness first, speed second</h2>
              <ul className="miq-features">
                {[
                  "Immutable plan versions + SHA-256 hashing",
                  "Server-side approval gate (403 without sign-off)",
                  "Idempotent retry, with 3 layers of duplicate prevention",
                  "12 typed, pure transformation rules",
                  "Append-only audit log with Postgres trigger",
                  "Per-row content hash reconciliation",
                  "AI failover with visible backup banner",
                  "Field-level quarantine evidence on every rejection",
                ].map((f) => <li key={f}>{f}</li>)}
              </ul>
            </div>
          </div>
        </section>

        {/* Demo / roles */}
        <section className="miq-band miq-wrap" id="demo" aria-labelledby="d-h">
          <div className="miq-sec">
            <p className="miq-rail">Live demo</p>
            <div>
              <h2 className="miq-h2" id="d-h">Two roles, one workflow</h2>
              <p className="miq-sub">Open the app in two tabs side by side, one logged in as operator, one as approver, to feel the separation of duties live.</p>

              <div className="miq-roles">
                <div className="miq-role">
                  <h3 className="miq-h3">Operator</h3>
                  <p>Creates projects, runs the AI agent, answers clarification questions, edits mappings, dry runs, executes and retries.</p>
                  <dl className="miq-creds">
                    <dt>username</dt><dd>operator</dd>
                    <dt>password</dt><dd>migrateiq-demo</dd>
                  </dl>
                </div>
                <div className="miq-role">
                  <h3 className="miq-h3">Approver</h3>
                  <p>Reviews the approval checklist, approves or rejects specific plan versions, performs rollbacks and signs off risk acknowledgements.</p>
                  <dl className="miq-creds">
                    <dt>username</dt><dd>approver</dd>
                    <dt>password</dt><dd>migrateiq-demo</dd>
                  </dl>
                </div>
              </div>

              <div className="miq-demo-cta">
                <Link className="miq-btn" to="/login">Open the app</Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
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
          <Link to="/login">Sign in</Link>
        </div>
        {/* Author credit — footer */}
        <AuthorCredit />
      </footer>
    </div>
  );
}
