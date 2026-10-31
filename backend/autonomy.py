"""Autonomy + workflow engine: what the agent may do on its own, what needs a human, and what it can never do.

Guardrails live in code, not in the prompt:
  - Every action is registered with a risk level. The agent executes LOW risk actions itself.
  - MEDIUM risk actions can only be PROPOSED by the agent; execute() refuses them unless a human approves.
  - HIGH risk actions (retention calls) are handed to a human; the agent never executes them.
  - Money actions (fee waivers, offers, refunds) are not registered at all, so nothing can trigger them.
    Any attempt is blocked and written to the audit log.

Case state and the audit log are stored in SQLite so the dashboard, chat and approvals all see the same truth.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime

import db
import engine
import simulator as sim
from stories import STORIES


@dataclass(frozen=True)
class Action:
    risk: str          # low | medium | high
    team: str | None   # who carries it out (None = the agent itself)
    label: str


ACTIONS = {
    # Low risk: the agent acts on its own
    "send_check_in":     Action("low", None, "Message merchant to confirm the issue"),
    "send_fix_steps":    Action("low", None, "Send guided fix steps"),
    "inform_merchant":   Action("low", None, "Tell merchant what is happening"),
    "mark_resolved":     Action("low", None, "Mark case resolved"),
    "escalate_to_human": Action("low", None, "Hand the case to a human"),
    "stop_messages":     Action("low", None, "Stop messaging (merchant opted out)"),
    # Medium risk: agent proposes, a human approves
    "replace_device":    Action("medium", "Device team", "Replace Soundbox"),
    "technician_visit":  Action("medium", "Device team", "Send technician"),
    "raise_ticket":      Action("medium", None, "Raise ticket"),
    # High risk: human only
    "call_merchant":     Action("high", "Retention team", "Retention call by a person"),
}
# Deliberately NOT in ACTIONS. Listed only so attempts are recognised and logged.
FORBIDDEN = {"fee_waiver", "retention_offer", "refund", "cashback", "account_change"}

# What the agent does when a case is detected: (actions it takes now, action it proposes for a human)
PLAYBOOK = {
    "device_fault":        (["send_check_in"], ("replace_device", "Device team")),
    "sim_network":         (["send_fix_steps"], None),
    "possible_app_switch": (["send_check_in", "escalate_to_human"], ("call_merchant", "Retention team")),
    "settlement_delay":    (["inform_merchant"], ("raise_ticket", "Settlements team")),
    "payment_failures":    (["inform_merchant"], ("raise_ticket", "Payments team")),
}

# Actions whose approval fixes the underlying problem in the simulation (Phase 6 recovery check)
FIXES_PROBLEM = {"replace_device", "technician_visit", "raise_ticket", "mark_resolved"}


class GuardrailError(Exception):
    pass


# ---------- storage ----------

def _init():
    with db.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS case_state (case_id TEXT PRIMARY KEY, data TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS audit_log "
                     "(id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, day INTEGER, clock TEXT, actor TEXT, event TEXT)")


def load(case_id: str) -> dict | None:
    _init()
    with db.connect() as conn:
        row = conn.execute("SELECT data FROM case_state WHERE case_id = ?", (case_id,)).fetchone()
    return json.loads(row[0]) if row else None


def save(state: dict) -> None:
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO case_state VALUES (?, ?)", (state["case_id"], json.dumps(state)))


def all_states() -> list[dict]:
    _init()
    with db.connect() as conn:
        return [json.loads(r[0]) for r in conn.execute("SELECT data FROM case_state ORDER BY case_id")]


def audit(case_id: str, day: int, actor: str, event: str) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO audit_log (case_id, day, clock, actor, event) VALUES (?, ?, ?, ?, ?)",
                     (case_id, day, datetime.now().strftime("%H:%M:%S"), actor, event))


def audit_trail(case_id: str) -> list[dict]:
    _init()
    with db.connect() as conn:
        rows = conn.execute("SELECT day, clock, actor, event FROM audit_log WHERE case_id = ? ORDER BY id",
                            (case_id,)).fetchall()
    return [{"time": f"Day {d} {c}", "actor": a, "event": e} for d, c, a, e in rows]


def clear() -> None:
    _init()
    with db.connect() as conn:
        conn.execute("DELETE FROM case_state")
        conn.execute("DELETE FROM audit_log")


# ---------- the guardrail ----------

def execute(state: dict, action: str, actor: str = "agent", detail: str = "") -> None:
    """The only way any action happens. Enforces the autonomy levels."""
    day = state["as_of"]
    if action not in ACTIONS:
        audit(state["case_id"], day, actor, f"BLOCKED '{action}': not an allowed action"
              + (" (money/offer decisions are human-only)" if action in FORBIDDEN else ""))
        raise GuardrailError(f"{action} is not an allowed action")
    a = ACTIONS[action]
    if a.risk != "low" and actor == "agent":
        audit(state["case_id"], day, actor, f"BLOCKED '{action}': {a.risk} risk needs a human")
        raise GuardrailError(f"{action} is {a.risk} risk and needs a human")
    team = detail or a.team
    audit(state["case_id"], day, actor, f"{a.label}" + (f" → {team}" if team else ""))
    state.setdefault("actions_taken", []).append({"action": action, "actor": actor, "team": team})


# ---------- detection -> cases ----------

OPENING = {
    "device_fault": "Namaste {owner}, main Paytm ka AI assistant hoon. Aapke Soundbox par payments fail ho rahe hain "
                    "aur device baar baar offline ho raha hai. Kya aapko bhi yeh dikh raha hai?",
    "sim_network": "Namaste {owner}, main Paytm ka AI assistant hoon. Aapka Soundbox network se disconnect ho raha hai. "
                   "Kripya SIM card nikaal kar dobara lagaiye aur device restart kijiye.",
    "possible_app_switch": "Namaste {owner}, main Paytm ka AI assistant hoon. Kya Paytm se payment lene mein aapko "
                           "koi dikkat aa rahi hai?",
    "settlement_delay": "Namaste {owner}, main Paytm ka AI assistant hoon. Aapke settlements mein deri ho rahi hai. "
                        "Hum isse theek karwa rahe hain, aapko update milega.",
    "payment_failures": "Namaste {owner}, main Paytm ka AI assistant hoon. Aapke kuch payments fail ho rahe hain. "
                        "Hum bank ke saath check kar rahe hain.",
}


def _owner(name: str) -> str:
    return name.split()[0] + " ji"


def _future_volume(merchant_id: str, after_day: int) -> list[dict]:
    tx = db.read("daily_txns", "WHERE merchant_id = ? AND day > ? ORDER BY day", (merchant_id, after_day))
    return [{"day": int(d), "volume": float(v)} for d, v in zip(tx.day, tx.volume)]


def sync(scan: dict) -> None:
    """Create a case for every new detection and let the agent take its low-risk first steps."""
    _init()
    for c in scan["cases"]:
        case_id = f"C-{c.merchant_id}"
        if load(case_id):
            continue  # already being handled
        actions, proposal = PLAYBOOK[c.cause]
        story = STORIES.get(c.merchant_id)
        opening = story["backup_script"][0][1] if story and story["backup_script"] else \
            OPENING[c.cause].format(owner=_owner(c.merchant_name))
        state = {
            "case_id": case_id, "merchant_id": c.merchant_id, "merchant_name": c.merchant_name, "city": c.city,
            "cause": c.cause, "confidence": c.confidence, "signals_agree": c.signals_agree,
            "first_flag_day": c.first_flag_day, "as_of": scan["as_of"], "status": "contacted",
            "daily_volume": c.daily_volume, "losing_per_day": c.losing_per_day,
            "proposal": None, "chat": [{"role": "assistant", "text": opening}], "opted_out": False,
            # What happens if nobody acts: saved now, before any fix rewrites the future
            "counterfactual": _future_volume(c.merchant_id, scan["as_of"]),
            "recovery": None,
        }
        audit(case_id, c.first_flag_day, "engine", f"Flagged: {engine.CAUSE_TEXT[c.cause]} "
              f"({c.confidence:.0%}, {c.signals_agree})")
        for a in actions:
            execute(state, a)
        if proposal:
            action, team = proposal
            state["proposal"] = {"action": action, "team": team, "risk": ACTIONS[action].risk,
                                 "status": "pending_approval"}
            state["status"] = "escalated_human" if ACTIONS[action].risk == "high" else "pending_approval"
            audit(case_id, scan["as_of"], "agent", f"Proposed: {ACTIONS[action].label} → {team} "
                  f"({ACTIONS[action].risk} risk, needs a human)")
        save(state)

        # Demo: Bansal's merchant follows the guided steps and the issue is fixed (simulated reply)
        if story and c.cause == "sim_network" and len(story["backup_script"]) > 1:
            handle_message(case_id, story["backup_script"][1][0], simulated=True)


# ---------- conversation -> actions ----------

def classify(text: str) -> str:
    """Keyword backup for when Sarvam is unavailable. Order matters: guardrail-relevant intents first."""
    t = text.lower()
    if re.search(r"waiver|fee|offer|discount|cashback|refund|paise wapas|maaf|phonepe|gpay|google pay|chala jaunga|chhod", t):
        return "asks_waiver"
    if re.search(r"\bstop\b|band karo|mat bhejo|message nahi|unsubscribe", t):
        return "opt_out"
    if re.search(r"phir bhi|abhi bhi|still|nahi hua|not fixed|nahi chal|kaam nahi|same problem", t):
        return "not_fixed"
    if re.search(r"ho gaya|theek (chal|ho)|fixed|chal raha hai|working|sahi ho", t):
        return "fixed"
    if re.search(r"sab theek|koi dikkat nahi|no problem|all good|nahi hai", t):
        return "denied_issue"
    if re.search(r"\bhaan\b|\bha\b|\byes\b|sahi|disconnect|band ho|offline|problem|dikkat", t):
        return "confirmed_issue"
    return "other"


INTENTS_WITH_TEMPLATES = ["confirmed_issue", "not_fixed", "fixed", "asks_waiver", "opt_out", "denied_issue"]


def _reply_for(state: dict, intent: str) -> str:
    owner, cause = _owner(state["merchant_name"]), state["cause"]
    story = STORIES.get(state["merchant_id"])
    if intent == "asks_waiver":
        return (f"Aapki baat samajh gaya {owner}. Fees ya offer ka faisla main nahi le sakta. "
                "Paytm team ka ek member aapko jaldi call karega.")
    if intent == "opt_out":
        return f"Theek hai {owner}, hum aapko aage message nahi bhejenge. Dhanyavaad."
    if intent == "fixed":
        return f"Bahut badhiya {owner}! Ab aapke payments normal chal rahe hain. Koi aur dikkat ho to batayiye."
    if intent == "denied_issue":
        return f"Dhanyavaad {owner}. Hum aapke account par nazar rakhenge."
    if intent == "not_fixed":
        if cause == "device_fault":
            return (f"Dhanyavaad {owner}. Lagta hai device mein kharabi hai. Naya Soundbox bhejne ki request "
                    "Paytm team ko bhej di hai. Approval ke baad aapko update milega.")
        return f"Samajh gaya {owner}. Ek technician bhejne ki request Paytm team ko bhej di hai."
    if intent == "confirmed_issue":
        if cause in ("device_fault", "sim_network"):
            steps = story.get("fix_steps_hi", story["fix_steps"]) if story else \
                "Soundbox restart kijiye aur SIM card dobara lagaiye."
            return f"Samajh gaya {owner}. Kripya yeh kijiye: {steps} Ho jaaye to bataiye."
        return f"Dhanyavaad {owner}. Paytm team ko bata diya hai, woh jaldi aapse sampark karenge."
    return f"{owner}, kripya thoda aur bataiye, kya dikkat aa rahi hai?"


# Safety-critical intents: the deterministic keyword check can force these even if the LLM missed them,
# and the reply for them is always our fixed, approved wording (the LLM never improvises about money).
SAFETY_INTENTS = ("asks_waiver", "opt_out")


def resolve_intent(text: str, model_intent: str | None) -> str:
    keyword = classify(text)
    for safety in SAFETY_INTENTS:
        if safety in (keyword, model_intent):
            return safety
    return model_intent or keyword


def handle_message(case_id: str, text: str, model_intent: str | None = None, model_reply: str | None = None,
                   simulated: bool = False, source: str = "backup") -> dict:
    """Merchant said something. Classify, reply, and take only the actions the guardrails allow.

    model_intent / model_reply come from Sarvam when available; code decides which to trust.
    """
    state = load(case_id)
    if state is None:
        raise KeyError(case_id)
    intent = resolve_intent(text, model_intent)
    reply = model_reply if model_reply and intent not in SAFETY_INTENTS else _reply_for(state, intent)
    who = "merchant (simulated)" if simulated else "merchant"
    state["chat"].append({"role": "merchant", "text": text})
    audit(case_id, state["as_of"], who, f'Said: "{text}" → intent: {intent}')
    action_taken = "none"

    if state["opted_out"]:
        return {"reply": "", "intent": intent, "action_taken": "none (merchant opted out)", "source": source}

    if intent == "asks_waiver":
        # The agent cannot grant this. Prove it: the attempt is blocked by the guardrail, then a human is looped in.
        try:
            execute(state, "fee_waiver")
        except GuardrailError:
            pass
        execute(state, "escalate_to_human")
        state["proposal"] = {"action": "call_merchant", "team": "Retention team", "risk": "high",
                             "status": "pending_approval"}
        state["status"] = "escalated_human"
        action_taken = "blocked fee_waiver, escalated to human"
    elif intent == "opt_out":
        execute(state, "stop_messages")
        state["opted_out"] = True
        action_taken = "stop_messages"
    elif intent == "fixed" and state["cause"] in ("device_fault", "sim_network"):
        execute(state, "mark_resolved")
        state["status"] = "auto_resolved"
        _apply_fix_and_check(state)
        action_taken = "mark_resolved"
    elif intent == "confirmed_issue" and state["cause"] in ("device_fault", "sim_network"):
        execute(state, "send_fix_steps")
        action_taken = "send_fix_steps"
    elif intent == "not_fixed" and state["cause"] in ("device_fault", "sim_network"):
        action = "replace_device" if state["cause"] == "device_fault" else "technician_visit"
        state["proposal"] = {"action": action, "team": "Device team", "risk": "medium",
                             "status": "pending_approval"}
        state["status"] = "pending_approval"
        audit(case_id, state["as_of"], "agent", f"Simple fix failed. Proposed: {ACTIONS[action].label} "
              "→ Device team (medium risk, needs approval)")
        action_taken = f"proposed {action}"

    state["chat"].append({"role": "assistant", "text": reply, "intent": intent})
    save(state)
    return {"reply": reply, "intent": intent, "action_taken": action_taken, "source": source}


# ---------- human decisions ----------

def decide(case_id: str, decision: str, note: str = "", by: str = "support agent") -> dict:
    state = load(case_id)
    if state is None or not state.get("proposal"):
        raise KeyError(case_id)
    p = state["proposal"]
    if p["status"] != "pending_approval":
        return state
    if decision == "approve":
        execute(state, p["action"], actor=f"human: {by}", detail=p["team"])
        p["status"] = "approved"
        state["status"] = "assigned" if p["risk"] == "high" else "approved"
        if p["action"] in FIXES_PROBLEM:
            _apply_fix_and_check(state)
    else:
        audit(case_id, state["as_of"], f"human: {by}", f"Dismissed proposal: {ACTIONS[p['action']].label}")
        p["status"] = "dismissed"
        state["status"] = "dismissed"
    if note:
        audit(case_id, state["as_of"], f"human: {by}", f"Note: {note}")
    save(state)
    return state


def _apply_fix_and_check(state: dict) -> None:
    """Fix the problem from tomorrow on (simulation), then verify volume actually recovered."""
    fix_day = state["as_of"] + 1
    sim.apply_fix(state["merchant_id"], from_day=fix_day)
    tx = db.read("daily_txns", "WHERE merchant_id = ?", (state["merchant_id"],))
    base = tx[tx.day <= 7].set_index("day").volume
    check = tx[tx.day.between(fix_day, fix_day + 4)]
    # Compare each day with the same weekday in the baseline week
    expected = sum(base[(d - 1) % 7 + 1] for d in check.day)
    ratio = float(check.volume.sum() / expected) if expected else 0.0
    verdict = "recovered" if ratio >= 0.85 else "not yet recovered"
    state["recovery"] = {"from_day": fix_day, "to_day": fix_day + 4, "ratio": round(ratio, 2), "verdict": verdict}
    audit(state["case_id"], fix_day + 4, "engine",
          f"Recovery check days {fix_day}-{fix_day + 4}: volume at {ratio:.0%} of baseline → {verdict}")


# ---------- impact ----------

def impact(scan: dict) -> dict:
    """Real numbers from the simulation, not estimates."""
    states = all_states()
    protected, earlier = 0.0, []
    for s in states:
        cf = {p["day"]: p["volume"] for p in s["counterfactual"]}
        if s.get("recovery"):
            now = _future_volume(s["merchant_id"], s["as_of"])
            protected += sum(p["volume"] - cf.get(p["day"], p["volume"]) for p in now)
        # When would a plain "volume fell 30%" dashboard alert have fired, without MerchantPulse?
        tx = db.read("daily_txns", "WHERE merchant_id = ? AND day <= 7", (s["merchant_id"],)).set_index("day").volume
        for day in sorted(cf):
            if cf[day] < 0.7 * tx[(day - 1) % 7 + 1] and cf.get(day + 1, 1e9) < 0.7 * tx[day % 7 + 1]:
                earlier.append(day + 1 - s["first_flag_day"])
                break
    return {
        "volume_protected_rs": int(round(protected, -2)),
        "days_earlier": round(sum(earlier) / len(earlier)) if earlier else 0,
        "auto_resolved": sum(s["status"] == "auto_resolved" for s in states),
        "false_alarms_avoided": len(scan["ignored_noise"]) + len(scan["stayed_silent"]),
        "awaiting_human": sum(s.get("proposal") is not None and s["proposal"]["status"] == "pending_approval"
                              for s in states),
    }
