# MerchantPulse API contract

Backend: `http://localhost:8000` · Interactive docs: `http://localhost:8000/docs`

The Phase 0 backend returns **mock data in these exact shapes**. The frontend builds against them now; the backend
swaps in real logic in Phases 1–3 without changing the shapes. **Change a shape only if both of you agree.**

## Enums

| Field | Values |
|---|---|
| `cause` | `device_fault` · `sim_network` · `possible_app_switch` · `settlement_delay` · `payment_failures` · `festival_dip` |
| `risk` | `low` · `medium` · `high` · `none` |
| `badge` | `approve` (orange) · `urgent` (red) · `human_only` (red) · `done` (green) · `silent` (grey) · `waiting` · `dismissed` |
| `status` | `contacted` · `pending_approval` · `escalated_human` · `auto_resolved` · `approved` · `assigned` · `dismissed` · `silent` |
| `intent` | `confirmed_issue` · `denied_issue` · `fixed` · `not_fixed` · `asks_waiver` · `opt_out` · `other` |

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{ ok, sarvam_key_set }` |
| POST | `/api/scan` | Scan summary (below), runs the agent on all merchants |
| GET | `/api/cases` | `CaseSummary[]` |
| GET | `/api/cases/{id}` | `CaseDetail` |
| POST | `/api/cases/{id}/chat` | Body `{ message }` → `{ reply, intent, action_taken, source: "sarvam" \| "backup" \| "mock" }` |
| POST | `/api/cases/{id}/decision` | Body `{ decision: "approve" \| "dismiss", note }` → `{ ok, status, recovery }` |
| GET | `/api/impact` | `{ volume_protected_rs, days_earlier, auto_resolved, false_alarms_avoided, awaiting_human }` (all computed, not mock) |
| POST | `/api/reset` | `{ ok }`, restarts the demo |
| POST | `/api/voice/tts` | Body `{ text, language_code }` → `audio/wav` |
| POST | `/api/voice/stt` | Multipart `file` (webm/wav) → `{ transcript }` |

### Scan summary
```json
{ "as_of": 10, "scanned": 500, "unusual": 25, "need_action": 4, "stayed_silent": 1, "ignored_noise": 20,
  "resolved_by_agent": 1, "awaiting_approval": 2 }
```

### CaseSummary
```json
{ "id": "C-M001", "merchant_id": "M001", "merchant_name": "Sharma General Store", "city": "Noida",
  "cause": "device_fault", "risk": "medium", "badge": "approve",
  "summary": "Device fault · merchant confirmed", "confidence": 0.86, "detected_day": 8,
  "daily_volume": 12540, "losing_per_day": 1340 }
```

`daily_volume` = ₹ per day at stake (the merchant's normal day, from their own baseline week).
`losing_per_day` = ₹ per day below the same weekday last week, market-adjusted so a festival doesn't count; 0 once
a fix is verified. The "Needs you" queue is sorted by `losing_per_day`, then `daily_volume`.

### CaseDetail = CaseSummary +
```json
{
  "story": "…",
  "impact": { "score": 66, "level": "High" | "Medium" | "Low",
              "lines": ["Failed payments at 5.8% vs 0.9% normal: …", "Settlement status is normal."],
              "parts": [ { "label": "Ability to take payments and get paid", "points": 45, "max": 45 } ] } | null,
  "evidence": [ { "label": "Failed transactions", "baseline": "0.8%", "now": "9%", "severity": "high" } ],
  "series":   [ { "day": 1, "volume": 12.0, "failure_rate": 0.8, "offline_events": 0, "baseline_volume": 12.0,
                  "counterfactual": null } ],
  "chat":     [ { "role": "assistant" | "merchant", "text": "…", "intent": "confirmed_issue" | null } ],
  "proposed_action": { "action": "replace_device", "label": "Replace Soundbox", "team": "Device team",
                       "risk": "medium", "status": "pending_approval" | "approved" | "dismissed" },
  "recovery": { "from_day": 11, "to_day": 15, "ratio": 1.04, "verdict": "recovered" } | null,
  "audit":    [ { "time": "Day 10 11:04:09", "actor": "engine" | "agent" | "merchant" | "human: support agent",
                  "event": "…" } ]
}
```
`series.counterfactual` = volume if nobody had acted (saved at detection, before any fix), for days after `as_of`.
Audit events starting with `BLOCKED` are guardrail refusals.
`series.volume` is in ₹ '000. `proposed_action` is `null` when there is nothing to approve.

### Festival group case (`id: "C-FESTIVAL"`)
One card for every merchant the agent stayed silent on. `merchant_name` is `"Festival day"`, `badge` is `silent`,
`evidence` lists the 5 biggest dips (each `now` = % of last week), `chat` is empty, `proposed_action` is `null`.
`confidence` = share of all merchants who dipped together.
