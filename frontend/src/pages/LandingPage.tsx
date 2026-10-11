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
      </footer>
    </div>
  );
}
