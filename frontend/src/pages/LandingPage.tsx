import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Database,
  FlaskConical,
  GitBranch,
  History,
  RefreshCw,
  Shield,
  ShieldCheck,
  Shuffle,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";

/* ─── Inline SVG hero illustration ─── */
function HeroIllustration() {
  return (
    <svg viewBox="0 0 420 260" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full max-w-md mx-auto opacity-90">
      {/* Source table */}
      <rect x="8" y="40" width="120" height="180" rx="10" fill="#1e293b" stroke="#334155" strokeWidth="1.5" />
      <rect x="8" y="40" width="120" height="32" rx="10" fill="#4338ca" />
      <rect x="8" y="60" width="120" height="12" rx="0" fill="#4338ca" />
      <text x="68" y="62" textAnchor="middle" fill="white" fontSize="10" fontWeight="600">Source Table</text>
      {["cust_id","full_name","email_addr","signup_dt","credit_limit","status_cd"].map((f, i) => (
        <g key={f}>
          <rect x="18" y={84 + i * 22} width="100" height="16" rx="4" fill="#0f172a" />
          <text x="28" y={96 + i * 22} fill="#94a3b8" fontSize="8" fontFamily="monospace">{f}</text>
        </g>
      ))}
      {/* AI Agent box */}
      <rect x="150" y="80" width="120" height="100" rx="12" fill="#312e81" stroke="#4338ca" strokeWidth="1.5" />
      <circle cx="210" cy="112" r="18" fill="#4338ca" />
      <text x="210" y="116" textAnchor="middle" fill="white" fontSize="11" fontWeight="700">AI</text>
      <text x="210" y="152" textAnchor="middle" fill="#a5b4fc" fontSize="9" fontWeight="600">The Architect</text>
      <text x="210" y="166" textAnchor="middle" fill="#6366f1" fontSize="8">Proposes mappings</text>
      {/* Arrows left → agent */}
      <path d="M128 130 L150 130" stroke="#6366f1" strokeWidth="1.5" strokeDasharray="4 2" markerEnd="url(#ah)" />
      {/* Arrows agent → right */}
      <path d="M270 130 L292 130" stroke="#6366f1" strokeWidth="1.5" strokeDasharray="4 2" markerEnd="url(#ah)" />
      {/* Target table */}
      <rect x="292" y="40" width="120" height="180" rx="10" fill="#1e293b" stroke="#334155" strokeWidth="1.5" />
      <rect x="292" y="40" width="120" height="32" rx="10" fill="#059669" />
      <rect x="292" y="60" width="120" height="12" rx="0" fill="#059669" />
      <text x="352" y="62" textAnchor="middle" fill="white" fontSize="10" fontWeight="600">Target Table</text>
      {["legacy_id","first_name","last_name","email","phone_e164","signup_date","status"].map((f, i) => (
        <g key={f}>
          <rect x="302" y={84 + i * 22} width="100" height="16" rx="4" fill="#0f172a" />
          <text x="312" y={96 + i * 22} fill="#94a3b8" fontSize="8" fontFamily="monospace">{f}</text>
        </g>
      ))}
      {/* Approval badge */}
      <rect x="158" y="195" width="104" height="24" rx="12" fill="#064e3b" stroke="#10b981" strokeWidth="1" />
      <text x="210" y="211" textAnchor="middle" fill="#34d399" fontSize="9" fontWeight="600">✓ Approved &amp; Executed</text>
      {/* Arrowhead marker */}
      <defs>
        <marker id="ah" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0 0 L6 3 L0 6 Z" fill="#6366f1" />
        </marker>
      </defs>
    </svg>
  );
}

/* ─── Step cards ─── */
const STEPS = [
  {
    icon: Bot,
    badge: "Step 1",
    emoji: "🏗️",
    title: "The Architect",
    subtitle: "AI Agent",
    desc: "Looks at the old table format and the new table format. It proposes a plan: &ldquo;Hey, we should split full_name into first_name and last_name, convert currency to cents, and convert dates to ISO standard.&rdquo; It also spots risks and asks questions when it's unsure.",
    color: "from-indigo-500 to-violet-600",
    border: "border-indigo-200",
    bg: "bg-indigo-50",
    iconColor: "text-indigo-600",
    pill: "bg-indigo-100 text-indigo-700",
  },
  {
    icon: FlaskConical,
    badge: "Step 2",
    emoji: "🎭",
    title: "The Rehearsal",
    subtitle: "Deterministic Dry Run",
    desc: "Deterministic code tests all 60 records against the plan without touching the real database. It quarantines bad rows and shows evidence for why each was rejected — before a single byte is written.",
    color: "from-sky-500 to-cyan-600",
    border: "border-sky-200",
    bg: "bg-sky-50",
    iconColor: "text-sky-600",
    pill: "bg-sky-100 text-sky-700",
  },
  {
    icon: Shield,
    badge: "Step 3",
    emoji: "🛡️",
    title: "The Security Guard",
    subtitle: "Human Approval Gate",
    desc: "In enterprise companies, developers aren't allowed to push data straight to production. An Approver (different person) must review the checklist and approve the cryptographic hash of the plan. The server blocks execution with HTTP 403 until they do.",
    color: "from-emerald-500 to-teal-600",
    border: "border-emerald-200",
    bg: "bg-emerald-50",
    iconColor: "text-emerald-600",
    pill: "bg-emerald-100 text-emerald-700",
  },
  {
    icon: Database,
    badge: "Step 4",
    emoji: "✈️",
    title: "The Move & Audit",
    subtitle: "Execution & Reconciliation",
    desc: "Rows are inserted safely. If the server crashes midway, a Retry will never insert duplicate rows. Afterwards, Reconciliation mathematically proves that Source (60) = Accepted (45) + Rejected (15). Full rollback is always available.",
    color: "from-orange-500 to-amber-600",
    border: "border-orange-200",
    bg: "bg-orange-50",
    iconColor: "text-orange-600",
    pill: "bg-orange-100 text-orange-700",
  },
];

/* ─── Feature pills ─── */
const FEATURES = [
  { icon: GitBranch, text: "Immutable plan versions + SHA-256 hashing" },
  { icon: ShieldCheck, text: "Server-side approval gate (403 without sign-off)" },
  { icon: RefreshCw, text: "Idempotent retry — 3 layers of duplicate prevention" },
  { icon: Shuffle, text: "12 typed, pure transformation rules" },
  { icon: History, text: "Append-only audit log with Postgres trigger" },
  { icon: CheckCircle2, text: "Per-row content hash reconciliation" },
  { icon: Zap, text: "AI failover with visible backup banner" },
  { icon: Database, text: "Field-level quarantine evidence on every rejection" },
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-white font-sans antialiased text-slate-900">

      {/* ── Nav ── */}
      <header className="sticky top-0 z-50 border-b border-slate-100 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-xs font-bold text-white select-none">MQ</span>
            <span className="text-base font-semibold">MigrateIQ</span>
          </div>
          <nav className="hidden items-center gap-6 md:flex">
            {["How it works", "Features"].map((l) => (
              <a key={l} href={`#${l.toLowerCase().replace(/ /g, "-")}`} className="text-sm text-slate-500 hover:text-slate-900 transition-colors">{l}</a>
            ))}
          </nav>
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors shadow-sm"
          >
            Open app <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative overflow-hidden bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 py-24 md:py-32">
        {/* Grid pattern */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,1) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,1) 1px,transparent 1px)",
            backgroundSize: "44px 44px",
          }}
        />
        {/* Glow blobs */}
        <div aria-hidden="true" className="pointer-events-none absolute -top-40 left-1/4 h-96 w-96 rounded-full bg-indigo-600/20 blur-3xl" />
        <div aria-hidden="true" className="pointer-events-none absolute bottom-0 right-1/4 h-72 w-72 rounded-full bg-violet-600/20 blur-3xl" />

        <div className="relative mx-auto max-w-6xl px-6">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <div className="text-center lg:text-left">
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-xs font-semibold text-indigo-300">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400" />
                Airport Security for Database Migrations
              </div>
              <h1 className="text-5xl font-extrabold leading-[1.1] tracking-tight text-white md:text-6xl">
                Move data like a<br />
                <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-sky-400 bg-clip-text text-transparent">
                  control tower
                </span>
              </h1>
              <p className="mt-6 text-lg leading-relaxed text-slate-400 max-w-xl mx-auto lg:mx-0">
                MigrateIQ is an agentic migration workbench. The <strong className="text-white">AI Architect</strong> proposes the plan. The <strong className="text-white">Rehearsal</strong> proves it works. The <strong className="text-white">Security Guard</strong> approves it. The <strong className="text-white">Move & Audit</strong> executes it — with full rollback.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4 lg:justify-start">
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 rounded-xl bg-indigo-500 px-6 py-3.5 text-sm font-bold text-white shadow-lg shadow-indigo-500/40 hover:bg-indigo-400 transition-all hover:shadow-indigo-500/50 hover:-translate-y-0.5"
                >
                  Try live demo <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
                <a
                  href="#how-it-works"
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-600 px-6 py-3.5 text-sm font-semibold text-slate-300 hover:border-slate-400 hover:text-white transition-colors"
                >
                  See how it works
                </a>
              </div>
              {/* Social proof row */}
              <div className="mt-10 flex flex-wrap items-center justify-center gap-5 lg:justify-start">
                {[
                  { n: "139", l: "Tests passing" },
                  { n: "500", l: "Max records" },
                  { n: "3-layer", l: "Idempotency" },
                  { n: "Live AI", l: "With failover" },
                ].map((s) => (
                  <div key={s.l} className="text-center">
                    <div className="text-xl font-bold text-indigo-400">{s.n}</div>
                    <div className="text-xs text-slate-500">{s.l}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="hidden lg:block">
              <HeroIllustration />
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how-it-works" className="py-24 bg-slate-50">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mb-14 text-center">
            <p className="text-xs font-bold uppercase tracking-widest text-indigo-600">How it works</p>
            <h2 className="mt-2 text-3xl font-extrabold text-slate-900 md:text-4xl">
              Think of it as airport security<br className="hidden md:block" /> for your data
            </h2>
            <p className="mt-3 text-slate-500 max-w-xl mx-auto">Every row goes through the full pipeline: proposed, rehearsed, approved, moved and audited.</p>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              return (
                <div
                  key={s.title}
                  className={`group relative overflow-hidden rounded-2xl border ${s.border} bg-white p-8 shadow-sm hover:shadow-lg transition-all duration-300 hover:-translate-y-1`}
                >
                  {/* Number watermark */}
                  <div className="absolute right-6 top-4 text-7xl font-black text-slate-100 select-none leading-none">
                    {String(i + 1).padStart(2, "0")}
                  </div>
                  <div className="relative">
                    <div className="flex items-center gap-3 mb-4">
                      <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${s.bg}`}>
                        <Icon className={`h-5 w-5 ${s.iconColor}`} aria-hidden="true" />
                      </div>
                      <div>
                        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.pill}`}>
                          {s.badge}
                        </span>
                        <p className="text-xs text-slate-400 mt-0.5">{s.subtitle}</p>
                      </div>
                    </div>
                    <h3 className="text-xl font-bold text-slate-900 mb-2">
                      {s.emoji} {s.title}
                    </h3>
                    <p className="text-sm text-slate-600 leading-relaxed">{s.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Math proof banner */}
          <div className="mt-10 rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-700 p-8 text-center text-white shadow-xl shadow-indigo-200">
            <p className="text-sm font-semibold uppercase tracking-widest text-indigo-200 mb-3">Mathematical guarantee</p>
            <div className="flex flex-wrap items-center justify-center gap-3 text-3xl font-extrabold tracking-tight md:gap-5 md:text-4xl">
              <span>Source (60)</span>
              <span className="text-indigo-300">=</span>
              <span>Accepted (45)</span>
              <span className="text-indigo-300">+</span>
              <span>Rejected (15)</span>
            </div>
            <p className="mt-3 text-indigo-200 text-sm">Reconciliation verifies this invariant on every run — with per-row content hashing.</p>
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="py-24">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mb-14 text-center">
            <p className="text-xs font-bold uppercase tracking-widest text-indigo-600">Features</p>
            <h2 className="mt-2 text-3xl font-extrabold text-slate-900">Built for correctness first, speed second</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.text} className="flex items-start gap-3 rounded-xl border border-slate-100 bg-white p-5 shadow-sm hover:border-indigo-200 hover:shadow-md transition-all">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50">
                    <Icon className="h-4 w-4 text-indigo-600" aria-hidden="true" />
                  </div>
                  <p className="text-sm text-slate-700 leading-snug font-medium">{f.text}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Demo accounts quick-start ── */}
      <section className="bg-slate-950 py-20">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <p className="text-xs font-bold uppercase tracking-widest text-indigo-400 mb-3">Live demo</p>
          <h2 className="text-3xl font-extrabold text-white">Two roles, one workflow</h2>
          <p className="mt-4 text-slate-400 max-w-lg mx-auto text-sm leading-relaxed">
            Open the app in two tabs side by side — one logged in as operator, one as approver — to feel the separation of duties live.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-slate-700 bg-slate-800/60 p-6 text-left">
              <div className="flex items-center gap-2 mb-3">
                <div className="h-8 w-8 rounded-lg bg-indigo-600/20 flex items-center justify-center">
                  <Bot className="h-4 w-4 text-indigo-400" aria-hidden="true" />
                </div>
                <span className="font-bold text-white text-sm">Operator</span>
              </div>
              <p className="text-slate-400 text-xs leading-relaxed mb-4">Creates projects, runs the AI agent, answers clarification questions, edits mappings, dry runs, executes and retries.</p>
              <div className="font-mono text-xs bg-slate-900 rounded-lg p-3 text-emerald-400">
                username: <span className="text-white">operator</span><br />
                password: <span className="text-white">migrateiq-demo</span>
              </div>
            </div>
            <div className="rounded-2xl border border-slate-700 bg-slate-800/60 p-6 text-left">
              <div className="flex items-center gap-2 mb-3">
                <div className="h-8 w-8 rounded-lg bg-emerald-600/20 flex items-center justify-center">
                  <Shield className="h-4 w-4 text-emerald-400" aria-hidden="true" />
                </div>
                <span className="font-bold text-white text-sm">Approver</span>
              </div>
              <p className="text-slate-400 text-xs leading-relaxed mb-4">Reviews the approval checklist, approves or rejects specific plan versions, performs rollbacks and signs off risk acknowledgements.</p>
              <div className="font-mono text-xs bg-slate-900 rounded-lg p-3 text-emerald-400">
                username: <span className="text-white">approver</span><br />
                password: <span className="text-white">migrateiq-demo</span>
              </div>
            </div>
          </div>
          <Link
            to="/login"
            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-indigo-500 px-8 py-4 text-sm font-bold text-white shadow-lg shadow-indigo-500/30 hover:bg-indigo-400 hover:-translate-y-0.5 transition-all"
          >
            Open the app <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-slate-100 py-8 bg-white">
        <div className="mx-auto max-w-6xl px-6 flex flex-col items-center justify-between gap-4 text-xs text-slate-400 sm:flex-row">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded bg-indigo-600 text-[9px] font-bold text-white select-none">MQ</span>
            <span className="font-medium text-slate-600">MigrateIQ</span>
            <span>·</span>
            <span>Expert assessment submission</span>
          </div>
          <div className="flex items-center gap-4">
            <a href="https://github.com/07Sushant/AGGROSO" target="_blank" rel="noopener noreferrer" className="hover:text-slate-600 transition-colors">
              GitHub
            </a>
            <Link to="/login" className="hover:text-slate-600 transition-colors">Sign in</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
