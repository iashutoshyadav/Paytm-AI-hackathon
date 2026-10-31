// Types and calls for the MerchantPulse backend. Shapes match docs/API_CONTRACT.md.

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Cause =
  | "device_fault"
  | "sim_network"
  | "possible_app_switch"
  | "settlement_delay"
  | "payment_failures"
  | "festival_dip";
export type Risk = "low" | "medium" | "high" | "none";
export type Badge = "approve" | "urgent" | "human_only" | "done" | "silent" | "waiting" | "dismissed";

export interface ScanSummary {
  as_of: number;
  scanned: number;
  unusual: number;
  need_action: number;
  stayed_silent: number;
  ignored_noise: number;
  resolved_by_agent: number;
  awaiting_approval: number;
}

export interface CaseSummary {
  id: string;
  merchant_id: string;
  merchant_name: string;
  city: string;
  cause: Cause;
  risk: Risk;
  badge: Badge;
  summary: string;
  confidence: number;
  detected_day: number;
  status: string;
  daily_volume: number; // Rs per day at stake: the merchant's normal day on Paytm
  losing_per_day: number; // Rs per day leaking now (market-adjusted; 0 once fixed)
}

/** ₹1,340 → "₹1.3k", ₹30,840 → "₹30.8k" */
export const rsShort = (n: number) =>
  n >= 1000 ? `₹${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : `₹${n.toLocaleString("en-IN")}`;

export interface Evidence {
  label: string;
  baseline: string;
  now: string;
  severity: "high" | "medium" | "normal";
}

export interface SeriesPoint {
  day: number;
  volume: number;
  failure_rate: number;
  offline_events: number;
  baseline_volume: number;
  counterfactual: number | null; // volume if nobody had acted (saved before any fix)
}

export interface ChatMessage {
  role: "assistant" | "merchant";
  text: string;
  intent?: string | null;
}

export interface ProposedAction {
  action: string;
  label: string;
  team: string;
  risk: Risk;
  status: "pending_approval" | "approved" | "dismissed";
}

export interface Recovery {
  from_day: number;
  to_day: number;
  ratio: number;
  verdict: "recovered" | "not yet recovered";
}

/** Merchant Impact Score: how badly the business is hit (0-100), from visible parts. A risk score, not a measured loss. */
export interface MerchantImpact {
  score: number;
  level: "High" | "Medium" | "Low";
  lines: string[]; // plain-language business impact, including what is normal
  parts: { label: string; points: number; max: number }[];
}

export interface CaseDetail extends CaseSummary {
  story: string;
  impact: MerchantImpact | null;
  evidence: Evidence[];
  series: SeriesPoint[];
  chat: ChatMessage[];
  proposed_action: ProposedAction | null;
  recovery: Recovery | null;
  audit: { time: string; actor: string; event: string }[];
}

export interface ChatReply {
  reply: string;
  intent: string;
  action_taken: string;
  source: "sarvam" | "backup" | "mock";
}

export interface Impact {
  volume_protected_rs: number;
  days_earlier: number;
  auto_resolved: number;
  false_alarms_avoided: number;
  awaiting_human: number;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init);
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => call<{ ok: boolean; sarvam_key_set: boolean }>("/api/health"),
  scan: () => call<ScanSummary>("/api/scan", { method: "POST" }),
  cases: () => call<CaseSummary[]>("/api/cases"),
  caseDetail: (id: string) => call<CaseDetail>(`/api/cases/${id}`),
  chat: (id: string, message: string) => call<ChatReply>(`/api/cases/${id}/chat`, json({ message })),
  decide: (id: string, decision: "approve" | "dismiss", note = "") =>
    call<{ ok: boolean; status: string; recovery: Recovery | null }>(`/api/cases/${id}/decision`, json({ decision, note })),
  impact: () => call<Impact>("/api/impact"),
  reset: () => call<{ ok: boolean }>("/api/reset", { method: "POST" }),

  async tts(text: string): Promise<Blob> {
    const res = await fetch(`${API}/api/voice/tts`, json({ text, language_code: "hi-IN" }));
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? "Voice unavailable");
    return res.blob();
  },
  async stt(audio: Blob): Promise<string> {
    const form = new FormData();
    form.append("file", audio, "merchant.webm");
    const res = await fetch(`${API}/api/voice/stt`, { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? "Speech-to-text unavailable");
    return (await res.json()).transcript;
  },
};

export type Toast = { text: string; tone: "good" | "warn" | "info" };

// Merchant replies offered as one-tap buttons in the chat, so presenters don't type on stage
export const QUICK_REPLIES: Partial<Record<Cause, string[]>> = {
  device_fault: [
    "Haan, device baar baar disconnect ho raha hai.",
    "Kar diya, phir bhi disconnect ho raha hai.",
  ],
  sim_network: ["Ho gaya, ab theek chal raha hai."],
  possible_app_switch: ["Mujhe fee waiver do warna main PhonePe pe chala jaunga.", "Nahi, sab theek hai."],
  settlement_delay: ["Paise 2 din se nahi aaye.", "STOP, mujhe message mat bhejo"],
  payment_failures: ["Haan, payments fail ho rahe hain."],
};

// Display text
export const CAUSE_LABEL: Record<Cause, string> = {
  device_fault: "Device fault",
  sim_network: "SIM / network",
  possible_app_switch: "Possible app switch",
  settlement_delay: "Settlement delay",
  payment_failures: "Payment failures",
  festival_dip: "Festival dip",
};

export const ACTION_LABEL: Record<string, string> = {
  replace_device: "Replace device",
  call_merchant: "Call merchant for retention",
  raise_ticket: "Raise ticket",
};

export const RISK_TEXT: Record<Risk, string> = {
  low: "Low risk · agent acts on its own",
  medium: "Medium risk · needs your approval",
  high: "High risk · human only",
  none: "No action",
};
