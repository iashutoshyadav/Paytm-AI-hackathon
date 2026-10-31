"""Merchant simulator: 500 merchants x 30 days of realistic Paytm data, with 5 planted problems and 20 noisy decoys.

Timeline (matches the pitch deck):
  days 1-7   normal week -> each merchant's own baseline (every weekday once)
  day 8      the 5 problems start
  day 10     "today" in the demo, and a festival day (every merchant dips)
  days 11-30 what happens WITHOUT MerchantPulse. apply_fix() rewrites these after a human approves.

Every (merchant, day) uses its own seeded random generator, so regenerating one merchant (apply_fix) gives
identical normal noise and only removes the problem.

Run: python simulator.py
"""
import sys

import numpy as np
import pandas as pd

import db

SEED = 42
N_MERCHANTS = 500
DAYS = 30
PROBLEM_START = 8
AS_OF_DAY = 10
FESTIVAL_DAY = 10
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # day 1 is a Monday

# category: (avg ticket Rs, daily volume range Rs, weekend factor, share of merchants)
CATEGORIES = {
    "kirana":      (180, (6000, 20000), 1.15, 0.28),
    "medical":     (350, (8000, 30000), 1.00, 0.12),
    "tea_stall":   (25,  (1500, 5000),  0.90, 0.12),
    "grocery":     (250, (12000, 40000), 1.20, 0.10),
    "restaurant":  (300, (8000, 35000), 1.30, 0.10),
    "salon":       (200, (3000, 12000), 1.35, 0.08),
    "mobile_shop": (600, (5000, 25000), 1.20, 0.07),
    "hardware":    (450, (6000, 22000), 0.85, 0.07),
    "sweets":      (220, (6000, 20000), 1.25, 0.06),
}
CATEGORY_WORD = {"kirana": "Kirana Store", "medical": "Medicals", "tea_stall": "Tea Stall", "grocery": "Grocery Mart",
                 "restaurant": "Dhaba", "salon": "Salon", "mobile_shop": "Mobile Centre", "hardware": "Hardware",
                 "sweets": "Sweets"}
SURNAMES = ["Agarwal", "Arora", "Bansal", "Bhatia", "Chauhan", "Chopra", "Garg", "Goel", "Gupta", "Jain", "Kapoor",
            "Khanna", "Kumar", "Malhotra", "Mehta", "Mishra", "Nagpal", "Pandey", "Rana", "Rastogi", "Saini", "Sethi",
            "Sharma", "Singh", "Singhal", "Sood", "Tiwari", "Tyagi", "Verma", "Yadav", "Ahmed", "Khan", "Qureshi"]
CITIES = ["Noida", "Delhi", "Gurugram", "Ghaziabad", "Faridabad"]

# The 5 planted problems (ids and names match stories.py)
PLANTED = {
    "M001": dict(name="Sharma General Store", city="Noida", category="kirana", base_volume=12000, failure_rate=0.010,
                 label="device_fault"),
    "M002": dict(name="Bansal Kirana", city="Noida", category="kirana", base_volume=9000, failure_rate=0.008,
                 label="sim_network"),
    "M003": dict(name="Raj Tea Stall", city="Noida", category="tea_stall", base_volume=4000, failure_rate=0.007,
                 label="possible_app_switch"),
    "M004": dict(name="Noida Fresh Mart", city="Noida", category="grocery", base_volume=30000, failure_rate=0.008,
                 label="settlement_delay"),
    "M005": dict(name="Verma Hardware", city="Noida", category="hardware", base_volume=15000, failure_rate=0.008,
                 label="festival_dip"),
}
N_NOISY = 20
NOISE_TYPES = ["failure_spike_1day", "offline_once", "volume_wobble_1day", "settlement_late_once", "high_variance"]


def _rng(*keys) -> np.random.Generator:
    return np.random.default_rng([SEED, *keys])


# ---------- merchants ----------

def make_merchants() -> pd.DataFrame:
    rng = _rng(0)
    cats = list(CATEGORIES)
    shares = np.array([CATEGORIES[c][3] for c in cats])
    rows, used_names = [], set()
    for i in range(1, N_MERCHANTS + 1):
        mid = f"M{i:03d}"
        if mid in PLANTED:
            p = PLANTED[mid]
            row = dict(merchant_id=mid, name=p["name"], city=p["city"], category=p["category"],
                       base_volume=p["base_volume"], base_failure_rate=p["failure_rate"])
        else:
            cat = rng.choice(cats, p=shares / shares.sum())
            lo, hi = CATEGORIES[cat][1]
            name = f"{rng.choice(SURNAMES)} {CATEGORY_WORD[cat]}"
            while name in used_names or name in {p["name"] for p in PLANTED.values()}:
                name = f"{rng.choice(SURNAMES)} {CATEGORY_WORD[cat]} {rng.integers(2, 99)}"
            row = dict(merchant_id=mid, name=name, city=str(rng.choice(CITIES)), category=str(cat),
                       base_volume=int(rng.uniform(lo, hi) // 100 * 100),
                       base_failure_rate=float(np.clip(rng.normal(0.008, 0.002), 0.003, 0.015)))
        used_names.add(row["name"])
        row.update(avg_ticket=CATEGORIES[row["category"]][0] * float(rng.uniform(0.8, 1.2)),
                   signal_strength=float(rng.uniform(65, 90)),
                   language="hi-IN" if rng.random() < 0.8 else "en-IN",
                   device="Soundbox",
                   phone=f"+91 98{rng.integers(10_000_000, 99_999_999)}")
        rows.append(row)
    return pd.DataFrame(rows)


def assign_labels(merchants: pd.DataFrame) -> dict[str, str]:
    """Ground truth: planted causes, noisy decoys, everyone else normal. The engine must never read this."""
    labels = {mid: p["label"] for mid, p in PLANTED.items()}
    rng = _rng(1)
    others = [m for m in merchants.merchant_id if m not in PLANTED]
    for k, mid in enumerate(rng.choice(others, N_NOISY, replace=False)):
        labels[str(mid)] = "noise_" + NOISE_TYPES[k % len(NOISE_TYPES)]
    return labels


# ---------- one merchant, one day ----------

def _problem_effects(label: str, day: int) -> dict:
    """Overrides for a planted problem on a given day (empty before day 8)."""
    if day < PROBLEM_START:
        return {}
    k = day - PROBLEM_START  # 0 on day 8
    if label == "device_fault":
        # Hardware failing: signal stays normal, but the box drops and payments fail.
        # Leading signals first, customers drift away later: about -50% by day 15.
        failure = [0.05, 0.08, 0.09][k] if k < 3 else 0.10
        demand = [0.97, 0.94, 0.90][k] if k < 3 else max(0.55, 0.90 - 0.07 * (k - 2))
        return dict(failure_rate=failure, demand=demand, offline_events=2 + (k >= 2) + (k >= 5),
                    offline_minutes_each=45)
    if label == "sim_network":
        # Network problem: very weak signal, short frequent drops, only a small rise in failures.
        return dict(failure_rate=0.02, demand=0.95, offline_events=3, signal=22.0, offline_minutes_each=20)
    if label == "possible_app_switch":
        # Customers still come, they just pay on another QR: fewer transactions, same ticket, healthy device.
        return dict(demand=[0.75, 0.65, 0.60][k] if k < 3 else max(0.35, 0.60 - 0.03 * (k - 2)))
    if label == "settlement_delay":
        return dict(delay_hours=48.0)
    return {}


def _noise_effects(label: str, day: int) -> dict:
    """Short, harmless oddities on days 8-10 that a naive alert system would flag."""
    if label == "noise_failure_spike_1day" and day == 9:
        return dict(failure_rate=0.04)
    if label == "noise_offline_once" and day == 9:
        return dict(offline_events=1, offline_minutes_each=30)
    if label == "noise_volume_wobble_1day" and day == 8:
        return dict(demand=0.70)
    if label == "noise_settlement_late_once" and day == 9:
        return dict(delay_hours=12.0)
    if label == "noise_high_variance" and day >= PROBLEM_START:
        return dict(extra_noise=0.25)
    return {}


def simulate_day(m: dict, idx: int, day: int, label: str, fixed: bool) -> tuple[dict, dict, dict]:
    rng = _rng(2, idx, day)
    cat = m["category"]
    weekday = (day - 1) % 7
    fx = {}
    if not fixed:
        fx = _problem_effects(label, day) if not label.startswith("noise") else _noise_effects(label, day)

    demand = CATEGORIES[cat][2] if weekday >= 5 else 1.0
    if day == FESTIVAL_DAY:
        demand *= 0.55 if label == "festival_dip" else float(np.clip(rng.normal(0.68, 0.06), 0.5, 0.85))
    demand *= fx.get("demand", 1.0)
    demand *= max(0.3, rng.normal(1.0, 0.07 + fx.get("extra_noise", 0.0)))

    ticket = m["avg_ticket"] * max(0.7, rng.normal(1.0, 0.05))
    attempts = max(1, int(round(m["base_volume"] * demand / m["avg_ticket"])))
    failure_rate = fx.get("failure_rate", m["base_failure_rate"])
    failed = int(rng.binomial(attempts, failure_rate))
    success = attempts - failed
    volume = round(success * ticket, 2)

    offline_events = fx.get("offline_events", int(rng.poisson(0.03)))
    offline_minutes = int(offline_events * fx.get("offline_minutes_each", rng.integers(5, 15)))
    signal = float(np.clip(rng.normal(fx.get("signal", m["signal_strength"]), 4), 0, 100))
    delay = float(fx.get("delay_hours", max(0.5, rng.normal(2.0, 0.5))))

    txn = dict(merchant_id=m["merchant_id"], day=day, weekday=WEEKDAYS[weekday], txn_count=success,
               failed_count=failed, failure_rate=round(failed / attempts, 4), avg_ticket=round(ticket, 2),
               volume=volume)
    device = dict(merchant_id=m["merchant_id"], day=day, offline_events=offline_events,
                  offline_minutes=offline_minutes, signal_strength=round(signal, 1))
    settle = dict(merchant_id=m["merchant_id"], day=day, expected_amount=volume, settled_amount=volume,
                  delay_hours=round(delay, 1))
    return txn, device, settle


def simulate_merchant(m: dict, idx: int, label: str, fixed_from: int | None = None, days=range(1, DAYS + 1)):
    rows = [simulate_day(m, idx, d, label, fixed=fixed_from is not None and d >= fixed_from) for d in days]
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]


# ---------- build / save / fix ----------

def build() -> dict[str, pd.DataFrame]:
    merchants = make_merchants()
    labels = assign_labels(merchants)
    txns, devices, settles = [], [], []
    for idx, m in enumerate(merchants.to_dict("records")):
        t, d, s = simulate_merchant(m, idx, labels.get(m["merchant_id"], "normal"))
        txns += t
        devices += d
        settles += s
    calendar = pd.DataFrame([dict(day=d, weekday=WEEKDAYS[(d - 1) % 7], is_weekend=(d - 1) % 7 >= 5,
                                  is_festival=d == FESTIVAL_DAY, festival_name="Festival" if d == FESTIVAL_DAY else "")
                             for d in range(1, DAYS + 1)])
    ground_truth = pd.DataFrame([dict(merchant_id=mid, label=labels.get(mid, "normal"))
                                 for mid in merchants.merchant_id])
    meta = pd.DataFrame([dict(key="as_of_day", value=str(AS_OF_DAY)),
                         dict(key="problem_start", value=str(PROBLEM_START)),
                         dict(key="festival_day", value=str(FESTIVAL_DAY))])
    return dict(merchants=merchants, daily_txns=pd.DataFrame(txns), device_health=pd.DataFrame(devices),
                settlements=pd.DataFrame(settles), calendar=calendar, ground_truth=ground_truth, meta=meta)


def apply_fix(merchant_id: str, from_day: int) -> None:
    """After a human approves a fix: rewrite this merchant's data from `from_day` without the problem (Phase 6)."""
    merchants = db.read("merchants")
    idx = int(merchants.index[merchants.merchant_id == merchant_id][0])
    m = merchants.iloc[idx].to_dict()
    label = db.read("ground_truth", "WHERE merchant_id = ?", (merchant_id,)).label.iloc[0]
    days = range(from_day, DAYS + 1)
    t, d, s = simulate_merchant(m, idx, label, fixed_from=from_day, days=days)
    with db.connect() as conn:
        for table in ("daily_txns", "device_health", "settlements"):
            conn.execute(f"DELETE FROM {table} WHERE merchant_id = ? AND day >= ?", (merchant_id, from_day))
        pd.DataFrame(t).to_sql("daily_txns", conn, if_exists="append", index=False)
        pd.DataFrame(d).to_sql("device_health", conn, if_exists="append", index=False)
        pd.DataFrame(s).to_sql("settlements", conn, if_exists="append", index=False)


# ---------- CLI ----------

def _report(t: dict[str, pd.DataFrame]) -> None:
    tx, dev, st = t["daily_txns"], t["device_health"], t["settlements"]
    gt = t["ground_truth"].label.value_counts()
    print(f"Merchants: {len(t['merchants'])} | rows: {len(tx)} txns, {len(dev)} device, {len(st)} settlements")
    print(f"Normal failure rate (days 1-7, all merchants): {tx[tx.day <= 7].failure_rate.mean():.2%}")
    print(f"Labels: {gt.get('normal', 0)} normal, {gt.filter(like='noise').sum()} noisy decoys, 5 planted\n")

    def show(mid, cols):
        df = tx.merge(dev, on=["merchant_id", "day"]).merge(st[["merchant_id", "day", "delay_hours"]],
                                                           on=["merchant_id", "day"])
        df = df[(df.merchant_id == mid) & (df.day.between(5, 15))]
        name = t["merchants"].set_index("merchant_id").name[mid]
        print(f"--- {mid} {name} ---")
        print(df[["day", "weekday"] + cols].to_string(index=False))
        print()

    show("M001", ["volume", "failure_rate", "offline_events", "signal_strength"])
    show("M002", ["volume", "failure_rate", "offline_events", "signal_strength"])
    show("M003", ["txn_count", "avg_ticket", "failure_rate", "offline_events"])
    show("M004", ["volume", "delay_hours"])

    base = tx[tx.day <= 7].groupby("merchant_id").volume.mean()
    fest = tx[tx.day == FESTIVAL_DAY].set_index("merchant_id").volume
    drop = 1 - fest / base
    print(f"Festival day {FESTIVAL_DAY}: {(drop > 0.2).sum()} of {len(drop)} merchants dipped >20% "
          f"(median dip {drop.median():.0%}); Verma Hardware dipped {drop['M005']:.0%}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    tables = build()
    db.write(tables)
    print(f"Saved to {db.DB_PATH}\n")
    _report(tables)
