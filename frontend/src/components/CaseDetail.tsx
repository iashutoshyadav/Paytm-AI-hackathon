"use client";

import { useState } from "react";
import ChatPanel from "./ChatPanel";
import VolumeCharts from "./VolumeCharts";
import {
  api,
  CAUSE_LABEL,
  QUICK_REPLIES,
  type CaseDetail as Detail,
  type ChatReply,
  type Risk,
  type Toast,
} from "@/lib/api";

interface Props {
  detail: Detail;
  asOf: number;
  onChanged: () => void; // reload this case, the queue and impact from the backend
  onToast: (t: Toast) => void;
}

const SEVERITY = {
  high: { dot: "bg-red", now: "text-red" },
  medium: { dot: "bg-orange", now: "text-orange-ink" },
  normal: { dot: "bg-green", now: "text-ink" },
} as const;
const RISK_CHIP: Record<Risk, { text: string; cls: string }> = {
  low: { text: "Low risk · agent acts", cls: "bg-green/15 text-green-ink" },
  medium: { text: "Medium risk · needs approval", cls: "bg-orange/15 text-orange-ink" },
  high: { text: "High risk · person only", cls: "bg-red/10 text-red" },
  none: { text: "No action", cls: "bg-panel text-muted" },
};

const IMPACT_STYLE = {
  High: { box: "bg-red/10", bar: "bg-red", text: "text-red" },
  Medium: { box: "bg-orange/15", bar: "bg-orange", text: "text-orange-ink" },
  Low: { box: "bg-green/15", bar: "bg-green", text: "text-green-ink" },
} as const;
// Business-impact lines that describe something normal get a ✓ instead of a warning
const NORMAL_LINE = /normal range|working normally|close to this merchant's normal|status is normal/;

export default function CaseDetail({ detail, asOf, onChanged, onToast }: Props) {
  const [showFuture, setShowFuture] = useState(false);
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const silent = detail.cause === "festival_dip";
  const p = detail.proposed_action;
  const humanOnly = p?.risk === "high";
  const owner = detail.merchant_name.split(" ")[0] + " ji";
  const askedForMoney = detail.chat.some((m) => m.intent === "asks_waiver");
  const rec = detail.recovery;
  const impact = detail.impact;
  const risk: Risk = silent ? "none" : p?.risk ?? "low";
  const initials = detail.merchant_name.split(" ").slice(0, 2).map((w) => w[0]).join("");

  async function decide(decision: "approve" | "dismiss") {
    if (!p) return;
    setBusy(true);
    try {
      const r = await api.decide(detail.id, decision, note);
      setEditing(false);
      if (decision === "dismiss") onToast({ text: "Proposal dismissed", tone: "info" });
      else if (r.recovery?.verdict === "recovered")
        onToast({ text: `✓ ${p.label} → ${p.team}. Recovery verified: ${Math.round(r.recovery.ratio * 100)}% of normal`, tone: "good" });
      else onToast({ text: `✓ ${humanOnly ? "Assigned to" : "Sent to"} ${p.team}`, tone: "good" });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  function onReply(r: ChatReply) {
    if (r.intent === "asks_waiver") onToast({ text: "🛡️ Guardrail: fee waiver blocked, handed to a person", tone: "warn" });
    else if (r.action_taken.startsWith("proposed")) onToast({ text: "Simple fix failed · agent proposed the next step for approval", tone: "info" });
    else if (r.action_taken === "mark_resolved") onToast({ text: "✓ Resolved by the agent", tone: "good" });
    onChanged();
  }

  return (
    <div className="rise space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl text-lg font-black ${silent ? "bg-panel" : "bg-navy text-white"}`}>
            {silent ? "🔇" : initials}
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-2xl font-black md:text-3xl">{detail.merchant_name}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted">
                {silent ? `${detail.city} · day ${detail.detected_day}` : `${detail.city} · ${detail.merchant_id} · flagged day ${detail.detected_day}`}
              </span>
              <span className="rounded-full bg-cyan-soft px-2.5 py-0.5 text-xs font-bold text-navy">{CAUSE_LABEL[detail.cause]}</span>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${RISK_CHIP[risk].cls}`}>{RISK_CHIP[risk].text}</span>
            </div>
            {!silent && (
              <p className="mt-2 text-sm">
                <b className="tabular">₹{detail.daily_volume.toLocaleString("en-IN")}/day</b>
                <span className="text-muted"> at stake</span>
                {detail.losing_per_day > 0 ? (
                  <>
                    <span className="text-muted"> · </span>
                    <b className="text-red tabular">≈₹{detail.losing_per_day.toLocaleString("en-IN")}/day</b>
                    <span className="text-muted"> leaking now (estimate)</span>
                  </>
                ) : rec ? (
                  <span className="font-bold text-green-ink"> · leak stopped</span>
                ) : (
                  <span className="text-muted"> · sales not hit yet</span>
                )}
              </p>
            )}
          </div>
        </div>
        <div className="flex w-full flex-wrap gap-3 sm:w-auto">
        {impact && (
          <div className={`w-full rounded-xl px-4 py-3 sm:w-52 ${IMPACT_STYLE[impact.level].box}`}>
            <div className="flex items-baseline justify-between">
              <p className="text-xs font-bold text-muted">Impact score</p>
              <p className="text-2xl font-black tabular">
                {impact.score}<span className="text-sm font-bold text-muted">/100</span>
              </p>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/70">
              <div className={`h-full rounded-full ${IMPACT_STYLE[impact.level].bar}`} style={{ width: `${impact.score}%` }} />
            </div>
            <p className={`mt-1 text-[11px] font-bold ${IMPACT_STYLE[impact.level].text}`}>{impact.level} impact on the business</p>
          </div>
        )}
        <div className="w-full rounded-xl bg-panel px-4 py-3 sm:w-52">
          <div className="flex items-baseline justify-between">
            <p className="text-xs font-bold text-muted">{silent ? "Merchants dipping together" : "Confidence"}</p>
            <p className="text-2xl font-black tabular">{Math.round(detail.confidence * 100)}%</p>
          </div>
          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-cyan" style={{ width: `${detail.confidence * 100}%` }} />
          </div>
          {detail.cause === "possible_app_switch" ? (
            <p className="mt-1 text-[11px] text-muted">Capped at 70%: we can&apos;t see other apps&apos; data</p>
          ) : (
            !silent && <p className="mt-1 text-[11px] text-muted">How sure the cause is right</p>
          )}
        </div>
        </div>
      </div>

      {detail.story && (
        <p className={`rounded-xl border-l-4 px-4 py-3 text-sm ${silent ? "border-muted bg-panel" : "border-cyan bg-cyan-soft"}`}>
          <span className="font-black">{silent ? "Why I stayed silent: " : "Agent's reading: "}</span>
          {detail.story}
        </p>
      )}

      {impact && (
        <section className="rounded-xl border border-line p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-xs font-black tracking-wider text-cyan-ink uppercase">Business impact · what this means for the merchant</h3>
            <p className="text-[11px] text-muted">Score from the signals below, not a measured loss</p>
          </div>
          <div className="mt-3 grid gap-4 lg:grid-cols-[3fr_2fr]">
            <ul className="space-y-1.5 text-sm">
              {impact.lines.map((line) => {
                const ok = NORMAL_LINE.test(line);
                return (
                  <li key={line} className="flex gap-2">
                    <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-[11px] font-black ${ok ? "bg-green/15 text-green-ink" : "bg-orange/20 text-orange-ink"}`}>
                      {ok ? "✓" : "!"}
                    </span>
                    <span className={ok ? "text-muted" : "text-ink"}>{line}</span>
                  </li>
                );
              })}
            </ul>
            <div className="space-y-2">
              {impact.parts.map((part) => (
                <div key={part.label}>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted">{part.label}</span>
                    <span className="font-bold tabular">{part.points}/{part.max}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-line">
                    <div className={`h-full rounded-full ${IMPACT_STYLE[impact.level].bar}`} style={{ width: `${(part.points / part.max) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {rec && (
        <div className={`rise flex items-center gap-3 rounded-xl px-4 py-3 ${rec.verdict === "recovered" ? "bg-green/15" : "bg-orange/15"}`}>
          <span className={`grid h-9 w-9 place-items-center rounded-full text-lg font-black text-white ${rec.verdict === "recovered" ? "bg-green-ink" : "bg-orange"}`}>
            {rec.verdict === "recovered" ? "✓" : "!"}
          </span>
          <p className="text-sm">
            <b className={rec.verdict === "recovered" ? "text-green-ink" : "text-orange-ink"}>
              {rec.verdict === "recovered" ? "Recovery verified" : "Not yet recovered"}
            </b>
            <span className="text-muted"> · volume at </span>
            <b className="tabular">{Math.round(rec.ratio * 100)}%</b>
            <span className="text-muted"> of the merchant&apos;s own normal on days {rec.from_day}–{rec.to_day}</span>
          </p>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        {/* Left: evidence + charts */}
        <div className="min-w-0 space-y-4">
          <section>
            <h3 className="mb-2 text-xs font-black tracking-wider text-cyan-ink uppercase">
              {silent ? "Biggest dips today · % of last week" : "Evidence · vs the merchant's own normal"}
            </h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {detail.evidence.map((e) => (
                <div key={e.label} className="rounded-xl bg-panel px-3 py-2.5">
                  <p className="flex items-center gap-2 text-xs text-muted">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${SEVERITY[e.severity].dot}`} />
                    <span className="truncate">{e.label}</span>
                  </p>
                  <p className="mt-1 text-sm">
                    {!silent && <span className="text-muted tabular">{e.baseline} → </span>}
                    <b className={`tabular ${SEVERITY[e.severity].now}`}>{e.now}</b>
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-line p-4">
            <VolumeCharts series={detail.series} asOf={asOf} markerDay={detail.detected_day}
              markerLabel={silent ? "Festival" : `Flagged · day ${detail.detected_day}`}
              showFuture={showFuture} recovered={rec?.verdict === "recovered"} />
            {silent && <p className="mt-1 text-xs text-muted">Average of all 500 merchants</p>}
            {!rec && !silent && (
              <label className="mt-3 flex w-fit cursor-pointer items-center gap-2 rounded-full bg-panel px-3 py-1.5 text-xs font-bold text-ink hover:bg-line">
                <input type="checkbox" checked={showFuture} onChange={(e) => setShowFuture(e.target.checked)} className="accent-[#e5484d]" />
                Show what happens if nobody acts
              </label>
            )}
          </section>
        </div>

        {/* Right: chat + action */}
        <div className="flex min-w-0 flex-col gap-4">
          {silent ? (
            <div className="grid min-h-72 flex-1 place-items-center rounded-xl border border-dashed border-line p-6 text-center">
              <div>
                <p className="text-5xl">🔇</p>
                <p className="mt-3 text-lg font-black">0 messages sent</p>
                <p className="mx-auto mt-1 max-w-xs text-sm text-muted">
                  Everyone dipped together, so this is the festival, not a merchant problem. Messaging hundreds of
                  merchants would only be noise.
                </p>
              </div>
            </div>
          ) : (
            <div className="h-[30rem]">
              <ChatPanel caseId={detail.id} ownerName={owner} initial={detail.chat} onReply={onReply}
                suggestions={QUICK_REPLIES[detail.cause] ?? []} />
            </div>
          )}

          {askedForMoney && (
            <div className="rise flex gap-3 rounded-xl border-2 border-red bg-red/5 p-4 text-sm">
              <span className="text-2xl" aria-hidden>🛡️</span>
              <div>
                <p className="font-black text-red">Guardrail: merchant asked for money or an offer</p>
                <p className="mt-1">
                  Fee waivers are not an action the agent has. The request was blocked, recorded, and the case was
                  handed to a person.
                </p>
              </div>
            </div>
          )}

          {p && (
            <section className={`rounded-xl border-2 p-4 ${p.status === "pending_approval" ? "border-orange/60 bg-orange/5" : "border-line"}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-black tracking-wider text-muted uppercase">Proposed action</p>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${RISK_CHIP[p.risk].cls}`}>{RISK_CHIP[p.risk].text}</span>
              </div>
              <p className="mt-2 text-xl font-black">
                {p.label} <span className="text-muted">→</span> {p.team}
              </p>
              {editing && (
                <textarea id="approval-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2}
                  placeholder="Add a note for the team (e.g. send a technician first)"
                  className="mt-3 w-full rounded-lg border border-line bg-white p-2 text-sm outline-none focus:ring-2 focus:ring-cyan" />
              )}
              {p.status === "approved" ? (
                <p className="mt-3 rounded-lg bg-green/15 px-3 py-2.5 font-black text-green-ink">
                  ✓ {humanOnly ? "Assigned to" : "Approved · sent to"} {p.team}
                </p>
              ) : p.status === "dismissed" ? (
                <p className="mt-3 rounded-lg bg-panel px-3 py-2.5 font-bold text-muted">Dismissed</p>
              ) : (
                <div className={`mt-3 grid gap-2 ${humanOnly ? "grid-cols-[2fr_1fr]" : "grid-cols-[2fr_1fr_1fr]"}`}>
                  <button disabled={busy} onClick={() => decide("approve")}
                    className="rounded-lg bg-cyan py-3 font-black text-navy shadow-sm hover:brightness-95 disabled:opacity-50">
                    {busy ? "Working…" : humanOnly ? `Assign to ${p.team}` : "✓ Approve"}
                  </button>
                  {!humanOnly && (
                    <button onClick={() => setEditing((v) => !v)} className="rounded-lg bg-white py-3 font-bold ring-1 ring-line hover:bg-panel">
                      {editing ? "Done" : "Edit"}
                    </button>
                  )}
                  <button disabled={busy} onClick={() => decide("dismiss")}
                    className="rounded-lg bg-white py-3 font-bold ring-1 ring-line hover:bg-panel disabled:opacity-50">Dismiss</button>
                </div>
              )}
              <p className="mt-2 text-xs text-muted">
                {humanOnly
                  ? "The agent made no offer. Offers and fee waivers are decided only by a person."
                  : "Low-risk steps were done by the agent; this one needs you."}
              </p>
            </section>
          )}
          {!p && !silent && detail.status === "auto_resolved" && (
            <p className="flex items-center gap-3 rounded-xl bg-green/15 p-4 text-sm font-bold text-green-ink">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-green-ink text-white">✓</span>
              Resolved by the agent on its own (low risk). No person needed.
            </p>
          )}
        </div>
      </div>

    </div>
  );
}
