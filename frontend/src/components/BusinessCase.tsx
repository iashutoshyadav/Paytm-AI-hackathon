"use client";

import { useState } from "react";
import type { Impact, ScanSummary } from "@/lib/api";

// Paytm's subscription merchants (Soundbox / card machine), Q4 FY26 results
const FLEET = 15_000_000;
// Sarvam cost per flagged merchant: a few chat messages + one voice note
const AI_COST_PER_CASE = 2;

/** ₹4,63,00,000 → "₹4.6 Cr", ₹54,00,000 → "₹54 L" */
const rsCrore = (n: number) =>
  n >= 1e7 ? `₹${(n / 1e7).toFixed(n >= 1e9 ? 0 : 1)} Cr` : n >= 1e5 ? `₹${(n / 1e5).toFixed(0)} L` : `₹${Math.round(n).toLocaleString("en-IN")}`;
const count = (n: number) => Math.round(n).toLocaleString("en-IN");

type Knob = { key: string; label: string; hint: string; min: number; max: number; step: number; unit: "%" | "₹" };

// Assumptions: not measured, so each one is a slider the audience can challenge
const KNOBS: Knob[] = [
  { key: "leave", label: "Of those, would leave without help", hint: "churn if nobody acts", min: 5, max: 50, step: 5, unit: "%" },
  { key: "saved", label: "Of those, saved by acting early", hint: "measure in the pilot", min: 5, max: 60, step: 5, unit: "%" },
  { key: "revenue", label: "Paytm revenue per merchant / month", hint: "rental + payment income", min: 100, max: 600, step: 25, unit: "₹" },
  { key: "support", label: "Cost of one case handled by a person", hint: "call centre time", min: 20, max: 300, step: 10, unit: "₹" },
];
const DEFAULTS: Record<string, number> = { leave: 20, saved: 25, revenue: 200, support: 80 };

export default function BusinessCase({ scan, impact }: { scan: ScanSummary; impact: Impact }) {
  const [a, setA] = useState(DEFAULTS);

  // Measured in this run of the agent
  const problemRate = scan.need_action / scan.scanned;
  const agentAloneRate = scan.need_action ? impact.auto_resolved / scan.need_action : 0;

  // Per year, at Paytm's scale
  const problemsPerMonth = FLEET * problemRate;
  const savedPerMonth = problemsPerMonth * (a.leave / 100) * (a.saved / 100);
  const retention = savedPerMonth * 12 * a.revenue * 12; // a saved merchant pays for at least another year
  const support = problemsPerMonth * agentAloneRate * a.support * 12;
  const cost = problemsPerMonth * 12 * AI_COST_PER_CASE;
  const net = retention + support - cost;
  const levers = [
    { label: "Revenue kept: merchants who would have left", value: retention, tone: "bg-cyan" },
    { label: "Support cost saved: cases closed by the agent alone", value: support, tone: "bg-green" },
  ];
  const biggest = Math.max(...levers.map((l) => l.value), 1);

  return (
    <section className="rise rounded-2xl bg-white p-5 shadow-sm md:p-6" aria-labelledby="bc-title">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-black tracking-wider text-muted uppercase">Business case · at Paytm scale</p>
          <h2 id="bc-title" className="mt-1 text-xl font-black">What MerchantPulse is worth per year</h2>
        </div>
        <button onClick={() => setA(DEFAULTS)} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-panel hover:text-ink">
          Reset assumptions
        </button>
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-[1fr_1fr]">
        {/* Inputs */}
        <div className="space-y-4">
          <div className="rounded-xl bg-cyan-soft p-4">
            <p className="text-xs font-black tracking-wider text-cyan-ink uppercase">Measured in this demo</p>
            <dl className="mt-2 grid grid-cols-3 gap-3 text-sm">
              <Fact value="1.5 Cr" label="Paytm subscription merchants (Q4 FY26)" />
              <Fact value={`${(problemRate * 100).toFixed(1)}%`} label={`need action (${scan.need_action} of ${scan.scanned})`} />
              <Fact value={`${Math.round(agentAloneRate * 100)}%`} label="closed by the agent with no person" />
            </dl>
          </div>

          <div>
            <p className="text-xs font-black tracking-wider text-muted uppercase">Assumptions · drag to challenge them</p>
            <div className="mt-3 space-y-3">
              {KNOBS.map((k) => (
                <label key={k.key} className="block">
                  <span className="flex items-baseline justify-between gap-3 text-sm">
                    <span>
                      {k.label} <span className="text-xs text-muted">· {k.hint}</span>
                    </span>
                    <b className="tabular">{k.unit === "₹" ? `₹${a[k.key]}` : `${a[k.key]}%`}</b>
                  </span>
                  <input type="range" min={k.min} max={k.max} step={k.step} value={a[k.key]}
                    onChange={(e) => setA({ ...a, [k.key]: Number(e.target.value) })}
                    className="mt-1 w-full accent-[#0089b8]" />
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Result */}
        <div className="flex flex-col rounded-xl bg-navy p-5 text-white">
          <p className="text-xs font-black tracking-wider text-white/55 uppercase">Net value per year</p>
          <p key={Math.round(net / 1e6)} className="flash -mx-1 mt-1 px-1 text-4xl font-black text-cyan tabular md:text-5xl">
            {rsCrore(net)}
          </p>
          <p className="mt-1 text-sm text-white/70">
            <b className="text-white tabular">{count(savedPerMonth)}</b> merchants saved every month ·{" "}
            <b className="text-white tabular">{Math.round((retention + support) / Math.max(cost, 1))}×</b> the AI cost
          </p>

          <div className="mt-5 space-y-3">
            {levers.map((l) => (
              <div key={l.label}>
                <p className="flex justify-between gap-3 text-sm">
                  <span className="text-white/80">{l.label}</span>
                  <b className="tabular">{rsCrore(l.value)}</b>
                </p>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/10">
                  <div className={`h-full rounded-full ${l.tone}`} style={{ width: `${(l.value / biggest) * 100}%` }} />
                </div>
              </div>
            ))}
            <p className="flex justify-between gap-3 border-t border-white/10 pt-3 text-sm">
              <span className="text-white/80">Minus AI running cost (₹{AI_COST_PER_CASE} per flagged merchant)</span>
              <b className="tabular">−{rsCrore(cost)}</b>
            </p>
          </div>

          <p className="mt-auto pt-5 text-xs text-white/55">
            An estimate, not a promise. Not counted: payment volume kept, fewer device replacements, cross-sell.
            A pilot with a control group in one city turns these assumptions into measured numbers.
          </p>
        </div>
      </div>
    </section>
  );
}

function Fact({ value, label }: { value: string; label: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xl font-black tabular">{value}</dt>
      <dd className="text-xs text-muted">{label}</dd>
    </div>
  );
}
