"use client";

import { useEffect, useRef, useState } from "react";
import Badge from "@/components/Badge";
import BusinessCase from "@/components/BusinessCase";
import CaseDetail from "@/components/CaseDetail";
import {
  api,
  type Badge as BadgeKind,
  type CaseDetail as Detail,
  type CaseSummary,
  type Impact,
  type ScanSummary,
  type Toast,
  rsShort,
} from "@/lib/api";

// Biggest money leak first, then the most at stake
const byMoney = (a: CaseSummary, b: CaseSummary) =>
  b.losing_per_day - a.losing_per_day || b.daily_volume - a.daily_volume;

// Queue groups: what needs a person first, then what the agent handled, then where it chose silence
const GROUPS: { title: string; badges: BadgeKind[] }[] = [
  { title: "Needs you", badges: ["approve", "urgent", "human_only"] },
  { title: "Handled by the agent", badges: ["done", "waiting", "dismissed"] },
  { title: "Stayed silent", badges: ["silent"] },
];
const STRIPE: Record<BadgeKind, string> = {
  approve: "bg-orange",
  urgent: "bg-red",
  human_only: "bg-red",
  done: "bg-green",
  waiting: "bg-cyan",
  dismissed: "bg-line",
  silent: "bg-line",
};

export default function Home() {
  const [scan, setScan] = useState<ScanSummary | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [sarvam, setSarvam] = useState<boolean | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function notify(t: Toast) {
    setToast(t);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4500);
  }

  async function runAgent() {
    setRunning(true);
    setError("");
    try {
      const s = await api.scan();
      const [c, imp] = await Promise.all([api.cases(), api.impact()]);
      setScan(s);
      setCases(c);
      setImpact(imp);
      setSelected(c[0]?.id ?? null);
    } catch {
      setError("Can't reach the backend. Start it with start-demo.ps1, or: cd backend → uvicorn main:app --port 8000");
    } finally {
      setRunning(false);
    }
  }

  async function reset() {
    await api.reset().catch(() => {});
    setScan(null);
    setCases([]);
    setImpact(null);
    setSelected(null);
    setDetail(null);
    notify({ text: "Demo reset to day 10", tone: "info" });
  }

  // Health check for the status light; ?autorun scans immediately (?case=C-M003 opens a case)
  useEffect(() => {
    api.health().then((h) => setSarvam(h.sarvam_key_set)).catch(() => setSarvam(null));
    const params = new URLSearchParams(window.location.search);
    if (params.has("autorun")) {
      runAgent().then(() => params.get("case") && setSelected(params.get("case")));
    }
  }, []);

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    api.caseDetail(selected).then(setDetail).catch(() => setError("Could not load case"));
  }, [selected]);

  // After a chat message or a decision the backend may have changed the case, the queue and the impact
  async function refreshAll() {
    try {
      const [c, imp, d] = await Promise.all([api.cases(), api.impact(), selected ? api.caseDetail(selected) : null]);
      setCases(c);
      setImpact(imp);
      if (d) setDetail(d);
    } catch {
      setError("Lost connection to the backend");
    }
  }

  return (
    <div className="min-h-screen">
      {/* Top bar */}
      <header className="sticky top-0 z-20 bg-navy text-white shadow-[0_1px_0_rgba(255,255,255,0.06)]">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 px-4 py-3 md:px-6">
          <div className="flex items-center gap-3">
            <svg width="36" height="22" viewBox="0 0 36 22" aria-hidden>
              <polyline points="0,11 10,11 13,3 18,19 22,7 25,11 36,11" fill="none" stroke="#00b9f1" strokeWidth="2.5" strokeLinejoin="round" />
            </svg>
            <div className="leading-tight">
              <p className="text-lg font-black">MerchantPulse</p>
              <p className="text-[11px] text-white/55">AI teammate for Paytm merchant support</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <StatusPill sarvam={sarvam} />
            {scan && <span className="rounded-full bg-white/10 px-3 py-1 text-white/80">Day {scan.as_of} · simulated</span>}
            {impact && (
              <span className="hidden rounded-full bg-white/10 px-3 py-1 text-white/80 lg:inline">
                Resolved by agent <b className="text-white">{impact.auto_resolved}</b> · Waiting for you{" "}
                <b className="text-white">{impact.awaiting_human}</b>
              </span>
            )}
            {scan && (
              <button onClick={reset} className="rounded-lg px-3 py-1.5 text-white/75 hover:bg-white/10 hover:text-white">
                Reset
              </button>
            )}
            <button onClick={runAgent} disabled={running}
              className="rounded-lg bg-cyan px-4 py-2 font-bold text-navy hover:brightness-110 disabled:opacity-60">
              {running ? "Scanning 500 merchants…" : scan ? "↻ Run again" : "▶ Run agent"}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] space-y-4 px-4 py-4 md:px-6">
        {error && <p className="rounded-lg bg-red/10 px-4 py-3 text-sm font-bold text-red">{error}</p>}

        {!scan ? (
          <Landing running={running} onRun={runAgent} />
        ) : (
          <>
            <section className="grid gap-4 xl:grid-cols-[3fr_2fr]">
              <Funnel scan={scan} />
              {impact && <ImpactPanel impact={impact} />}
            </section>

            <section className="grid gap-4 lg:grid-cols-[340px_1fr]">
              <aside className="space-y-4" aria-label="Cases">
                {GROUPS.map((g, gi) => {
                  const items = cases.filter((c) => g.badges.includes(c.badge)).sort(byMoney);
                  if (!items.length) return null;
                  const leaking = items.reduce((sum, c) => sum + c.losing_per_day, 0);
                  return (
                    <div key={g.title}>
                      <p className="flex items-center justify-between px-1 text-xs font-black tracking-wider text-muted uppercase">
                        {g.title}
                        <span className="rounded-full bg-white px-2 py-0.5 tabular">{items.length}</span>
                      </p>
                      {gi === 0 && (
                        <p className="mt-0.5 mb-2 px-1 text-xs text-muted">
                          Sorted by money lost per day · <b className="text-red tabular">{rsShort(leaking)}/day</b> leaking now
                        </p>
                      )}
                      {gi !== 0 && <div className="mb-2" />}
                      <div className="space-y-2">
                        {items.map((c) => (
                          <CaseCard key={c.id} c={c} active={selected === c.id} onClick={() => setSelected(c.id)} />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </aside>
              <div className="min-h-96 min-w-0 rounded-2xl bg-white p-4 shadow-sm md:p-6">
                {detail ? (
                  <CaseDetail key={detail.id} detail={detail} asOf={scan.as_of} onChanged={refreshAll} onToast={notify} />
                ) : (
                  <DetailSkeleton />
                )}
              </div>
            </section>

            {impact && <BusinessCase scan={scan} impact={impact} />}
          </>
        )}
      </main>

      {toast && (
        <div role="status" aria-live="polite"
          className={`rise fixed right-4 bottom-4 z-30 max-w-sm rounded-xl px-4 py-3 text-sm font-bold text-white shadow-lg ${
            toast.tone === "good" ? "bg-green-ink" : toast.tone === "warn" ? "bg-red" : "bg-navy"
          }`}>
          {toast.text}
        </div>
      )}
    </div>
  );
}

function StatusPill({ sarvam }: { sarvam: boolean | null }) {
  const ok = sarvam === true;
  return (
    <span className="flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-white/85">
      <span className={`h-2 w-2 rounded-full ${sarvam === null ? "bg-red" : "live-dot bg-green"}`} />
      {sarvam === null ? "Backend offline" : ok ? "Agent live · Sarvam AI" : "Agent live · backup replies"}
    </span>
  );
}

function Landing({ running, onRun }: { running: boolean; onRun: () => void }) {
  return (
    <div className="rise overflow-hidden rounded-2xl bg-navy text-white">
      <svg viewBox="0 0 1200 120" className="block h-24 w-full md:h-28" preserveAspectRatio="none" aria-hidden>
        <polyline className="pulse-draw" pathLength={1} points="0,70 430,70 470,70 495,18 525,110 555,40 575,70 820,70 845,52 862,82 880,70 1200,70"
          fill="none" stroke="#00b9f1" strokeWidth="3" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="px-6 pt-4 pb-12 text-center md:px-12">
        <p className="text-xs font-black tracking-[0.16em] text-cyan uppercase">Paytm Build for India · Track 3: Autonomous AI Teammates</p>
        <h1 className="mx-auto mt-4 max-w-3xl text-3xl font-black text-balance md:text-5xl">
          Paytm can&apos;t call millions of merchants.
        </h1>
        <p className="mx-auto mt-3 max-w-3xl text-xl font-bold text-cyan text-balance md:text-2xl">
          MerchantPulse tells it exactly whom to call, and why.
        </p>
        <button onClick={onRun} disabled={running}
          className="mt-8 rounded-xl bg-cyan px-10 py-4 text-lg font-black text-navy shadow-[0_8px_30px_rgba(0,185,241,0.35)] hover:brightness-110 disabled:opacity-60">
          {running ? "Scanning 500 merchants…" : "▶ Run agent"}
        </button>
        <div className="mx-auto mt-10 grid max-w-3xl grid-cols-1 gap-3 text-left sm:grid-cols-3">
          {[
            ["500", "simulated merchants, 30 days of payments, Soundbox and settlement data"],
            ["Day 10", "today in the simulation; problems started on day 8"],
            ["Hindi", "chat and voice with Sarvam AI, with guardrails enforced in code"],
          ].map(([big, small]) => (
            <div key={big} className="rounded-xl bg-white/5 px-4 py-3">
              <p className="text-xl font-black">{big}</p>
              <p className="text-xs text-white/60">{small}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Funnel({ scan }: { scan: ScanSummary }) {
  const steps = [
    { n: scan.scanned, label: "merchants scanned", tone: "bg-navy" },
    { n: scan.unusual, label: "looked unusual", tone: "bg-cyan-ink" },
    { n: scan.need_action, label: "need action", tone: "bg-red" },
  ];
  return (
    <div className="rise rounded-2xl bg-white p-5 shadow-sm">
      <p className="text-xs font-black tracking-wider text-muted uppercase">Today&apos;s scan · day {scan.as_of}</p>
      <div className="mt-4 grid grid-cols-[1fr_auto_1fr_auto_1fr] items-end gap-2 sm:gap-4">
        {steps.map((s, i) => (
          <FunnelStep key={s.label} {...s} last={i === steps.length - 1} max={scan.scanned} />
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-panel px-3 py-1 text-muted">
          <b className="text-ink tabular">−{scan.ignored_noise}</b> one-off blips ignored
        </span>
        <span className="rounded-full bg-panel px-3 py-1 text-muted">
          <b className="text-ink tabular">−{scan.stayed_silent}</b> festival dip: stayed silent, 0 messages
        </span>
      </div>
    </div>
  );
}

function FunnelStep({ n, label, tone, last, max }: { n: number; label: string; tone: string; last: boolean; max: number }) {
  // Bar height shows the share of all merchants (with a floor so 4 stays visible)
  const h = Math.max(8, Math.round((n / max) * 64));
  return (
    <>
      <div className="min-w-0">
        <div className="flex h-16 items-end">
          <div className={`w-full rounded-md ${tone}`} style={{ height: h }} />
        </div>
        <p className={`mt-2 text-3xl font-black tabular ${last ? "text-red" : ""}`}>{n}</p>
        <p className="text-xs text-muted">{label}</p>
      </div>
      {!last && <span className="pb-10 text-xl text-muted" aria-hidden>→</span>}
    </>
  );
}

function ImpactPanel({ impact }: { impact: Impact }) {
  const stats: [string, string][] = [
    [`₹${impact.volume_protected_rs.toLocaleString("en-IN")}`, "volume protected (days 11–30)"],
    [`${impact.days_earlier} days`, "before a volume-drop alert"],
    [`${impact.false_alarms_avoided}`, "false alarms avoided"],
  ];
  return (
    <div className="rise flex flex-col rounded-2xl bg-navy p-5 text-white shadow-sm">
      <p className="text-xs font-black tracking-wider text-white/55 uppercase">Impact · simulated</p>
      <div className="mt-4 grid grid-cols-3 gap-3">
        {stats.map(([v, l]) => (
          <div key={l} className="min-w-0">
            {/* key on the value replays the flash whenever the number changes */}
            <p key={v} className="flash -mx-1 px-1 text-2xl font-black text-cyan tabular md:text-3xl">{v}</p>
            <p className="mt-1 text-xs text-white/60">{l}</p>
          </div>
        ))}
      </div>
      <div className="mt-auto grid grid-cols-2 gap-3 border-t border-white/10 pt-4">
        <p className="text-sm text-white/70">
          <b key={`a${impact.auto_resolved}`} className="flash mr-1 px-1 text-lg text-white tabular">{impact.auto_resolved}</b>
          resolved by the agent alone
        </p>
        <p className="text-sm text-white/70">
          <b key={`w${impact.awaiting_human}`} className="flash mr-1 px-1 text-lg text-white tabular">{impact.awaiting_human}</b>
          waiting for a person
        </p>
      </div>
    </div>
  );
}

function CaseCard({ c, active, onClick }: { c: CaseSummary; active: boolean; onClick: () => void }) {
  const initials = c.merchant_name.split(" ").slice(0, 2).map((w) => w[0]).join("");
  const silent = c.badge === "silent";
  return (
    <button onClick={onClick} aria-pressed={active}
      className={`group relative flex w-full items-center gap-3 overflow-hidden rounded-xl border bg-white py-3 pr-3 pl-5 text-left transition ${
        active ? "border-cyan shadow-[0_0_0_2px_rgba(0,185,241,0.35)]" : "border-transparent shadow-sm hover:border-cyan/50"
      }`}>
      <span className={`absolute inset-y-0 left-0 w-1.5 ${STRIPE[c.badge]}`} aria-hidden />
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-black ${silent ? "bg-panel text-muted" : "bg-navy text-white"}`}>
        {silent ? "🔇" : initials}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-bold">{c.merchant_name}</span>
        <span className="block truncate text-xs text-muted">{c.summary}</span>
        {!silent && (
          <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="flex items-center gap-1.5">
              <span className="h-1 w-12 overflow-hidden rounded-full bg-line">
                <span className="block h-full rounded-full bg-cyan" style={{ width: `${c.confidence * 100}%` }} />
              </span>
              <span className="text-[11px] text-muted tabular">{Math.round(c.confidence * 100)}%</span>
            </span>
            {c.losing_per_day > 0 ? (
              <span className="text-[11px] font-bold text-red tabular">−{rsShort(c.losing_per_day)}/day</span>
            ) : (
              <span className="text-[11px] text-muted tabular">{rsShort(c.daily_volume)}/day at stake</span>
            )}
          </span>
        )}
      </span>
      <Badge kind={c.badge} />
    </button>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading case">
      <div className="skeleton h-10 w-2/3" />
      <div className="skeleton h-14" />
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="skeleton h-72" />
        <div className="skeleton h-72" />
      </div>
    </div>
  );
}
