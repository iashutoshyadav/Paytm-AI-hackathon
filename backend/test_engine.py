"""Phase 2 check: run `python test_engine.py` from the backend folder.

Grades the engine against the hidden ground truth (which the engine itself never reads).
"""
import sys
from collections import Counter

import db
import engine
import simulator as sim

sys.stdout.reconfigure(encoding="utf-8")
db.write(sim.build())
res = engine.scan()
truth = db.read("ground_truth").set_index("merchant_id").label

found = {c.merchant_id: c for c in res["cases"]}
silent = {s["merchant_id"] for s in res["stayed_silent"]}
passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + ok, failed + (not ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{': ' + str(detail) if detail != '' else ''}")


print(f"Funnel: {res['scanned']} scanned -> {res['unusual']} unusual -> {len(res['ignored_noise'])} one-offs ignored, "
      f"{len(silent)} stayed silent (festival) -> {len(found)} need action\n")
for c in res["cases"]:
    print(f"  {c.merchant_id} {c.merchant_name:22} {c.cause:20} {c.confidence:.0%} ({c.signals_agree})")
print()

for mid in ["M001", "M002", "M003", "M004"]:
    got = found[mid].cause if mid in found else "not found"
    check(f"{mid} diagnosed as {truth[mid]}", got == truth[mid], got)
check("M005 festival dip: stayed silent, no message", "M005" in silent and "M005" not in found)

false_alarms = [m for m in found if truth[m] not in ("device_fault", "sim_network", "possible_app_switch",
                                                      "settlement_delay")]
check("No false alarms on normal merchants", not false_alarms, ", ".join(false_alarms) or "0")
decoys = truth[truth.str.startswith("noise")].index
check("All 20 noisy decoys ignored", not any(d in found for d in decoys),
      str(Counter("ignored" if d not in found else "FLAGGED" for d in decoys)))
check("Festival detected as market-wide", res["context"]["market_event_today"],
      f"market at {res['context']['market_ratio_today']:.0%} of last week")
check("Sharma flagged before volume fell much (early warning)",
      res["signals"].loc["M001"].recent_volume > res["signals"].loc["M001"].base_volume * 0.75)

print("\n--- Money at risk")
for mid in ["M001", "M003", "M004"]:
    c = found[mid]
    print(f"  {c.merchant_name:22} Rs {c.daily_volume:>6,}/day at stake, Rs {c.losing_per_day:>5,}/day leaking")
check("Money at stake = merchant's own normal day", all(found[m].daily_volume > 0 for m in ["M001", "M003", "M004"]))
check("Sharma and Raj are losing money now", found["M001"].losing_per_day > 0 and found["M003"].losing_per_day > 0)
check("Settlement delay: payments fine, nothing leaking", found["M004"].losing_per_day == 0)
check("Festival removed from the leak (Sharma leak < 20% of his day)",
      found["M001"].losing_per_day < 0.2 * found["M001"].daily_volume)

print("\n--- Merchant Impact Score")
for mid in ["M001", "M003", "M004"]:
    i = found[mid].impact
    print(f"  {found[mid].merchant_name:22} {i['score']}/100 {i['level']}")
imp = {m: found[m].impact for m in ["M001", "M003", "M004"]}
check("Score is the sum of its visible parts", all(i["score"] == sum(p["points"] for p in i["parts"])
                                                   or abs(i["score"] - sum(p["points"] for p in i["parts"])) <= 1
                                                   for i in imp.values()))
check("Device fault = high impact (can't take payments)", imp["M001"]["level"] == "High", imp["M001"]["score"])
check("Settlement delay = high impact (cash flow, big merchant)", imp["M004"]["level"] == "High", imp["M004"]["score"])
check("Impact lines also say what is normal",
      "Settlement status is normal." in imp["M001"]["lines"]
      and "Soundbox is online and working normally." in imp["M004"]["lines"])

print(f"\n{passed}/{passed + failed} passed")
