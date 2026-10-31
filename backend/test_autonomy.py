"""Phase 3 check: run `python test_autonomy.py` from the backend folder.

Plays the full demo through the real API: scan, agent's own actions, chat, guardrail attacks, approvals,
recovery check, impact, reset. Uses the keyword backup for chat (no Sarvam key needed).
"""
import os
import sys

os.environ["SARVAM_API_KEY"] = ""  # force the backup path so results are deterministic
from fastapi.testclient import TestClient

import autonomy
import main

sys.stdout.reconfigure(encoding="utf-8")
api = TestClient(main.app)
passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + ok, failed + (not ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{': ' + str(detail) if detail != '' else ''}")


def badges():
    return {c["id"]: c["badge"] for c in api.get("/api/cases").json()}


def audit_text(case_id):
    return " | ".join(a["event"] for a in api.get(f"/api/cases/{case_id}").json()["audit"])


main.sarvam_client.API_KEY = ""
api.post("/api/reset")

print("--- Scan: agent takes its own low-risk steps")
s = api.post("/api/scan").json()
check("4 cases need action", s["need_action"] == 4, s["need_action"])
check("Bansal auto-resolved by the agent (low risk)", s["resolved_by_agent"] == 1, s["resolved_by_agent"])
check("3 cases wait for a human", s["awaiting_approval"] == 3, s["awaiting_approval"])
b = badges()
check("Badges", b == {"C-M001": "approve", "C-M002": "done", "C-M003": "human_only", "C-M004": "approve",
                      "C-FESTIVAL": "silent"}, b)
bansal = api.get("/api/cases/C-M002").json()
check("Bansal recovery verified", bansal["recovery"] and bansal["recovery"]["verdict"] == "recovered",
      bansal["recovery"])

print("\n--- Guardrails in code")
state = autonomy.load("C-M001")
for action, why in [("replace_device", "medium risk"), ("call_merchant", "high risk"), ("fee_waiver", "forbidden")]:
    try:
        autonomy.execute(state, action, actor="agent")
        check(f"Agent cannot execute {action} ({why})", False, "it was executed!")
    except autonomy.GuardrailError:
        check(f"Agent cannot execute {action} ({why})", True)
check("Blocked attempts are in the audit log", audit_text("C-M001").count("BLOCKED") == 3)

print("\n--- Sharma: chat, simple fix fails, agent proposes replacement")
r = api.post("/api/cases/C-M001/chat", json={"message": "Haan, device baar baar disconnect ho raha hai."}).json()
check("Confirms issue → agent sends fix steps", (r["intent"], r["action_taken"]) == ("confirmed_issue", "send_fix_steps"),
      r["reply"][:70])
r = api.post("/api/cases/C-M001/chat", json={"message": "Kar diya, phir bhi disconnect ho raha hai."}).json()
check("Fix failed → proposes device replacement", r["intent"] == "not_fixed" and "replace_device" in r["action_taken"],
      r["action_taken"])

print("\n--- Raj: merchant demands a fee waiver")
r = api.post("/api/cases/C-M003/chat", json={"message": "Mujhe fee waiver do warna main PhonePe pe chala jaunga."}).json()
check("Recognised as a money request", r["intent"] == "asks_waiver", r["intent"])
check("Waiver blocked, case escalated to a human", "blocked fee_waiver" in r["action_taken"], r["action_taken"])
check("Reply promises nothing", "faisla main nahi le sakta" in r["reply"], r["reply"][:70])
check("Audit shows the block", "BLOCKED 'fee_waiver'" in audit_text("C-M003"))

print("\n--- Human decisions")
before = api.get("/api/impact").json()
d = api.post("/api/cases/C-M001/decision", json={"decision": "approve", "note": "Send today"}).json()
check("Approve Sharma → replacement sent, volume recovered", d["status"] == "approved"
      and d["recovery"]["verdict"] == "recovered", d["recovery"])
after = api.get("/api/impact").json()
check("Impact: volume protected went up", after["volume_protected_rs"] > before["volume_protected_rs"],
      f"Rs {before['volume_protected_rs']:,} → Rs {after['volume_protected_rs']:,}")
check("Impact: caught days before a volume alert", after["days_earlier"] > 0, f"{after['days_earlier']} days")
check("Impact: false alarms avoided", after["false_alarms_avoided"] > 300, after["false_alarms_avoided"])
d = api.post("/api/cases/C-M003/decision", json={"decision": "approve"}).json()
check("Raj assigned to retention team (no auto offer)", d["status"] == "assigned" and d["recovery"] is None, d["status"])
d = api.post("/api/cases/C-M004/decision", json={"decision": "dismiss"}).json()
check("Dismiss works", d["status"] == "dismissed")
check("Double approval is ignored", api.post("/api/cases/C-M001/decision", json={"decision": "dismiss"}).json()["status"]
      == "approved")
detail = api.get("/api/cases/C-M001").json()
day12 = next(p for p in detail["series"] if p["day"] == 12)
check("Chart has 'after fix' vs 'if nobody acted'", day12["volume"] > day12["counterfactual"],
      f"day 12: Rs {day12['volume']}k vs Rs {day12['counterfactual']}k")

print("\n--- Festival + reset")
check("No case and no messages for festival merchants", autonomy.load("C-M005") is None)
api.post("/api/reset")
api.post("/api/scan")
check("Reset gives a fresh demo", badges()["C-M001"] == "approve" and "Kar diya" not in str(
    api.get("/api/cases/C-M001").json()["chat"]))

print(f"\n{passed}/{passed + failed} passed")
