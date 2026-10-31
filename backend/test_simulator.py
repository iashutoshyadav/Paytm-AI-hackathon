"""Phase 1 check: run `python test_simulator.py` from the backend folder. Rebuilds data.db, then checks every planted case."""
import sys

import db
import simulator as sim

sys.stdout.reconfigure(encoding="utf-8")
db.write(sim.build())

tx = db.read("daily_txns")
dev = db.read("device_health")
st = db.read("settlements")
gt = db.read("ground_truth")
passed = failed = 0


def check(name, ok, detail):
    global passed, failed
    passed, failed = passed + ok, failed + (not ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")


def pooled_failure(mid, days):
    d = tx[(tx.merchant_id == mid) & tx.day.isin(days)]
    return d.failed_count.sum() / (d.failed_count.sum() + d.txn_count.sum())


BASE, RECENT = range(1, 8), range(8, 11)

check("500 merchants", tx.merchant_id.nunique() == 500, f"{tx.merchant_id.nunique()}")
rate = tx[tx.day <= 7].failed_count.sum() / (tx[tx.day <= 7].failed_count.sum() + tx[tx.day <= 7].txn_count.sum())
check("Normal failure rate ~0.8% (real UPI)", 0.005 < rate < 0.011, f"{rate:.2%}")
check("20 noisy decoys", gt.label.str.startswith("noise").sum() == 20, f"{gt.label.str.startswith('noise').sum()}")

b, r = pooled_failure("M001", BASE), pooled_failure("M001", RECENT)
sig = dev[(dev.merchant_id == "M001") & dev.day.isin(RECENT)].signal_strength.mean()
check("Sharma: failures jump from day 8", b < 0.02 and r > 0.05, f"{b:.1%} -> {r:.1%}")
check("Sharma: signal normal (hardware fault, not network)", sig > 55, f"signal {sig:.0f}")

sig2 = dev[(dev.merchant_id == "M002") & dev.day.isin(RECENT)].signal_strength.mean()
off2 = dev[(dev.merchant_id == "M002") & dev.day.isin(RECENT)].offline_events.mean()
check("Bansal: weak signal + offline (network)", sig2 < 30 and off2 >= 2, f"signal {sig2:.0f}, offline {off2:.1f}/day")

raj = tx[tx.merchant_id == "M003"]
drop = 1 - raj[raj.day.isin([8, 9])].txn_count.mean() / raj[raj.day.isin([1, 2])].txn_count.mean()
ticket = raj[raj.day.isin(RECENT)].avg_ticket.mean() / raj[raj.day.isin(BASE)].avg_ticket.mean()
check("Raj: fewer txns, same ticket, healthy device", drop > 0.2 and 0.9 < ticket < 1.1
      and dev[(dev.merchant_id == "M003") & dev.day.isin(RECENT)].offline_events.sum() == 0,
      f"txns -{drop:.0%} (Mon-Tue vs Mon-Tue), ticket x{ticket:.2f}")

delay = st[(st.merchant_id == "M004") & st.day.isin(RECENT)].delay_hours.mean()
check("Noida Fresh Mart: settlement delay", delay > 24, f"{delay:.0f}h vs ~2h normal")

base_vol = tx[tx.day <= 7].groupby("merchant_id").volume.mean()
fest_drop = 1 - tx[tx.day == sim.FESTIVAL_DAY].set_index("merchant_id").volume / base_vol
check("Festival: most merchants dip together", (fest_drop > 0.2).mean() > 0.8,
      f"{(fest_drop > 0.2).mean():.0%} of merchants dipped >20%")

before = tx[(tx.merchant_id == "M001") & (tx.day >= 11)].volume.mean()
sim.apply_fix("M001", from_day=11)
after_tx = db.read("daily_txns", "WHERE merchant_id = 'M001' AND day >= 11")
check("apply_fix: Sharma recovers after approval", after_tx.volume.mean() > before * 1.3
      and after_tx.failure_rate.mean() < 0.03, f"avg volume Rs {before:,.0f} -> Rs {after_tx.volume.mean():,.0f}")

db.write(sim.build())  # leave a clean database behind
print(f"\n{passed}/{passed + failed} passed")
