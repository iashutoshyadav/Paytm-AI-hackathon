"""MerchantPulse API.

Shapes are fixed in docs/API_CONTRACT.md.
  engine.py    detects and diagnoses (rules, no LLM)
  autonomy.py  decides what the agent may do, keeps case state + audit log
  sarvam_*.py  talks to the merchant (falls back to a keyword backup if Sarvam is unavailable)

Run: uvicorn main:app --reload --port 8000
"""
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

import autonomy
import db
import engine
import sarvam_client
import simulator as sim
from stories import STORIES

app = FastAPI(title="MerchantPulse AI")
# FRONTEND_URL = the deployed dashboard (e.g. the Vercel URL); comma-separate several
FRONTEND_URLS = [u.strip().rstrip("/") for u in os.getenv("FRONTEND_URL", "").split(",") if u.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", *FRONTEND_URLS],
    allow_methods=["*"],
    allow_headers=["*"],
)

# A fresh server (e.g. a cloud deploy) has no database yet: build the demo data once
if not os.path.exists(db.DB_PATH):
    db.write(sim.build())

FESTIVAL_ID = "C-FESTIVAL"
_scan: dict | None = None


def _run_scan() -> dict:
    global _scan
    if _scan is None:
        _scan = engine.scan()
        autonomy.sync(_scan)
    return _scan


# ---------- shaping case state for the dashboard ----------

def _badge_and_summary(s: dict) -> tuple[str, str]:
    cause = engine.CAUSE_TEXT[s["cause"]]
    p, rec = s.get("proposal"), s.get("recovery")
    recovered = " · recovered ✓" if rec and rec["verdict"] == "recovered" else ""
    match s["status"]:
        case "auto_resolved":
            return "done", f"{cause} · fixed by agent{recovered}"
        case "pending_approval":
            return ("urgent" if s["cause"] == "payment_failures" else "approve"), f"{cause} · {s['signals_agree']}"
        case "escalated_human":
            return "human_only", f"{cause} · needs a person"
        case "approved":
            return "done", f"{cause} · approved{recovered}"
        case "assigned":
            return "done", f"{cause} · assigned to {p['team']}"
        case "dismissed":
            return "dismissed", f"{cause} · dismissed"
    if s.get("opted_out"):
        return "dismissed", f"{cause} · merchant opted out"
    return "waiting", f"{cause} · waiting for merchant"


def _summary(s: dict) -> dict:
    badge, summary = _badge_and_summary(s)
    risk = s["proposal"]["risk"] if s.get("proposal") else "low"
    return {"id": s["case_id"], "merchant_id": s["merchant_id"], "merchant_name": s["merchant_name"],
            "city": s["city"], "cause": s["cause"], "risk": risk, "badge": badge, "summary": summary,
            "confidence": s["confidence"], "detected_day": s["first_flag_day"], "status": s["status"],
            # Rs per day: normal volume at stake, and how much is leaking now (0 once the problem is fixed)
            "daily_volume": s.get("daily_volume", 0),
            "losing_per_day": 0 if s.get("recovery") else s.get("losing_per_day", 0)}


def _festival_summary(res: dict) -> dict:
    return {"id": FESTIVAL_ID, "merchant_id": "ALL", "merchant_name": "Festival day",
            "city": "All cities", "cause": "festival_dip", "risk": "none", "badge": "silent",
            "summary": f"{len(res['stayed_silent'])} merchants dipped together · no messages sent",
            # How sure we are the dip is market-wide: share of ALL merchants who dipped >20% today
            "confidence": round(float((res["signals"].today_vol_ratio < 0.8).mean()), 2),
            "detected_day": res["as_of"], "status": "silent", "daily_volume": 0, "losing_per_day": 0}


def _series(mid: str, counterfactual: list[dict] | None = None) -> list[dict]:
    """Real simulated data: volume in Rs '000, failure rate in %. `counterfactual` = volume if nobody had acted."""
    tx = db.read("daily_txns", "WHERE merchant_id = ? ORDER BY day", (mid,))
    dev = db.read("device_health", "WHERE merchant_id = ? ORDER BY day", (mid,))
    df = tx.merge(dev, on=["merchant_id", "day"])
    baseline = round(df[df.day <= 7].volume.mean() / 1000, 2)
    cf = {p["day"]: p["volume"] for p in counterfactual or []}
    return [{"day": int(r.day), "volume": round(r.volume / 1000, 2), "failure_rate": round(r.failure_rate * 100, 1),
             "offline_events": int(r.offline_events), "baseline_volume": baseline,
             "counterfactual": round(cf[r.day] / 1000, 2) if r.day in cf else None}
            for r in df.itertuples()]


def _market_series() -> list[dict]:
    """Average merchant across all 500: shows a market-wide event such as the festival."""
    tx = db.read("daily_txns")
    dev = db.read("device_health")
    df = tx.merge(dev, on=["merchant_id", "day"]).groupby("day").agg(
        volume=("volume", "mean"), failed=("failed_count", "sum"), ok=("txn_count", "sum"),
        offline=("offline_events", "mean")).reset_index()
    baseline = round(df[df.day <= 7].volume.mean() / 1000, 2)
    return [{"day": int(r.day), "volume": round(r.volume / 1000, 2),
             "failure_rate": round(r.failed / (r.failed + r.ok) * 100, 1), "offline_events": round(r.offline, 2),
             "baseline_volume": baseline, "counterfactual": None} for r in df.itertuples()]


def _case_detail(case_id: str) -> dict:
    res = _run_scan()
    if case_id == FESTIVAL_ID and res["stayed_silent"]:
        fs = _festival_summary(res)
        return {**fs,
                "story": f"Market-wide dip on day {res['as_of']}: the median merchant is at "
                         f"{res['context']['market_ratio_today']:.0%} of last week. A dip that everyone shares is "
                         "not a merchant problem, so the agent stays silent.",
                "evidence": [dict(label=e["name"], baseline="100%", now=f"{1 - e['dip']:.0%}", severity="normal")
                             for e in res["stayed_silent"][:5]],
                "series": _market_series(), "chat": [], "proposed_action": None, "recovery": None, "impact": None,
                "audit": [{"time": f"Day {res['as_of']}", "actor": "engine",
                           "event": f"Stayed silent for {len(res['stayed_silent'])} merchants: festival dip. "
                                    "0 messages sent."}]}

    s = autonomy.load(case_id)
    c = next((c for c in res["cases"] if f"C-{c.merchant_id}" == case_id), None)
    if s is None or c is None:
        raise HTTPException(404, "case not found")
    p = s.get("proposal")
    return {
        **_summary(s),
        "story": c.note,
        "impact": c.impact,
        "evidence": c.evidence,
        "series": _series(s["merchant_id"], s["counterfactual"]),
        "chat": [{"role": m["role"], "text": m["text"], "intent": m.get("intent")} for m in s["chat"]],
        "proposed_action": {**p, "label": autonomy.ACTIONS[p["action"]].label} if p else None,
        "recovery": s.get("recovery"),
        "audit": autonomy.audit_trail(case_id),
    }


# ---------- endpoints ----------

@app.get("/api/health")
def health():
    return {"ok": True, "sarvam_key_set": bool(sarvam_client.API_KEY)}


@app.post("/api/scan")
def scan():
    global _scan
    _scan = None
    res = _run_scan()
    imp = autonomy.impact(res)
    return {"as_of": res["as_of"], "scanned": res["scanned"], "unusual": res["unusual"],
            "need_action": len(res["cases"]), "stayed_silent": len(res["stayed_silent"]),
            "ignored_noise": len(res["ignored_noise"]), "resolved_by_agent": imp["auto_resolved"],
            "awaiting_approval": imp["awaiting_human"]}


@app.get("/api/cases")
def list_cases():
    res = _run_scan()
    cases = [_summary(s) for s in autonomy.all_states()]
    if res["stayed_silent"]:
        cases.append(_festival_summary(res))
    return cases


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    return _case_detail(case_id)


class ChatIn(BaseModel):
    message: str


def _sarvam_context(s: dict) -> tuple[str, str]:
    c = next(c for c in _run_scan()["cases"] if c.merchant_id == s["merchant_id"])
    evidence = "; ".join(f"{e['label']}: normal {e['baseline']}, now {e['now']}" for e in c.evidence)
    story = STORIES.get(s["merchant_id"])
    fix = story["fix_steps"] if story else "Restart the Soundbox and re-insert the SIM card."
    return (f"Merchant: {s['merchant_name']}, {s['city']}. Likely cause: {engine.CAUSE_TEXT[s['cause']]} "
            f"({s['confidence']:.0%} confidence). Evidence: {evidence}."), fix


@app.post("/api/cases/{case_id}/chat")
def chat(case_id: str, body: ChatIn):
    s = autonomy.load(case_id)
    if s is None:
        raise HTTPException(404, "case not found")
    # Sarvam writes the reply and suggests an intent; autonomy.py decides what to trust and what actually happens.
    if sarvam_client.API_KEY and not s.get("opted_out"):
        try:
            context, fix = _sarvam_context(s)
            history = [{"role": "user" if m["role"] == "merchant" else "assistant", "content": m["text"]}
                       for m in s["chat"]] + [{"role": "user", "content": body.message}]
            r = sarvam_client.merchant_reply(context, fix, history)
            return autonomy.handle_message(case_id, body.message, model_intent=r["intent"], model_reply=r["reply"],
                                           source="sarvam")
        except Exception as e:
            print(f"Sarvam unavailable, using backup: {e}")  # the demo never breaks
    return autonomy.handle_message(case_id, body.message, source="backup")


class DecisionIn(BaseModel):
    decision: str  # "approve" | "dismiss"
    note: str = ""


@app.post("/api/cases/{case_id}/decision")
def decide(case_id: str, body: DecisionIn):
    if body.decision not in ("approve", "dismiss"):
        raise HTTPException(422, "decision must be approve or dismiss")
    try:
        s = autonomy.decide(case_id, body.decision, body.note)
    except KeyError:
        raise HTTPException(404, "no pending proposal for this case")
    return {"ok": True, "status": s["status"], "recovery": s.get("recovery")}


@app.get("/api/impact")
def impact():
    return autonomy.impact(_run_scan())


@app.post("/api/reset")
def reset():
    """Back to the start of the demo: fresh data, no cases, empty audit log."""
    global _scan
    autonomy.clear()
    db.write(sim.build())
    _scan = None
    return {"ok": True}


# ---------- voice (real Sarvam calls) ----------

class TTSIn(BaseModel):
    text: str
    language_code: str = "hi-IN"


@app.post("/api/voice/tts")
def tts(body: TTSIn):
    try:
        return Response(sarvam_client.text_to_speech(body.text, body.language_code), media_type="audio/wav")
    except sarvam_client.SarvamError as e:
        raise HTTPException(502, str(e))


@app.post("/api/voice/stt")
async def stt(file: UploadFile = File(...)):
    try:
        return {"transcript": sarvam_client.speech_to_text(await file.read(), file.filename or "audio.webm")}
    except sarvam_client.SarvamError as e:
        raise HTTPException(502, str(e))
