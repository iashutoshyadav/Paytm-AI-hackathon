"""Early-warning engine + diagnosis.

For every merchant, compare the recent window (days 8..as_of) with the merchant's OWN baseline week (days 1-7),
and with the whole market on the same day. Then run a funnel:

  scanned -> unusual (anything odd at all)
          -> ignored: one-off blips (not sustained)
          -> stayed silent: dip explained by the whole market (festival)
          -> needs action: sustained problem, diagnosed with a likely cause, confidence and evidence

Rules decide. No LLM is involved here, so every decision is explainable with numbers.
"""
import math
from dataclasses import dataclass, field

import pandas as pd

import db

BASELINE_DAYS = range(1, 8)

# Thresholds. "Sustained" means on at least 2 of the recent days, so one bad day never triggers action.
FAIL_JUMP_PP = 3.0          # failure rate up by 3+ percentage points vs own baseline
OFFLINE_DAYS = 2            # days with Soundbox offline events
SIGNAL_LOW = 35             # network signal (0-100)
DELAY_HOURS = 24            # settlement delay
FAIL_P_VALUE = 0.001        # chance of seeing this many failures by luck must be below 0.1% (small shops!)
NETWORK_FAIL_FLOOR = 0.8    # never assume a merchant's normal failure rate is below the UPI average (~0.8%)
TXN_DROP_DAY = 0.80         # market-adjusted transactions below 80% of same weekday last week
TXN_DROP_MEAN = 0.75
TICKET_STABLE = (0.85, 1.15)
FESTIVAL_MARKET_DIP = 0.80  # whole market below 80% of last week = market-wide event
SUSTAINED_DAYS = 2

CAUSE_TEXT = {
    "device_fault": "Device fault",
    "sim_network": "SIM / network issue",
    "possible_app_switch": "Possible switch to another app",
    "settlement_delay": "Settlement delay",
    "payment_failures": "Payment failures (bank / gateway side)",
}


def poisson_tail(k: int, mean: float) -> float:
    """P(X >= k) for X ~ Poisson(mean): how likely k or more failures are by pure chance."""
    if k <= 0:
        return 1.0
    return max(0.0, 1.0 - sum(math.exp(-mean) * mean ** i / math.factorial(i) for i in range(k)))


@dataclass
class Case:
    merchant_id: str
    merchant_name: str
    city: str
    category: str
    cause: str
    confidence: float
    signals_agree: str
    evidence: list = field(default_factory=list)
    note: str = ""
    first_flag_day: int = 0
    daily_volume: int = 0      # Rs: merchant's normal day on Paytm (own baseline week) = what's at stake per day
    losing_per_day: int = 0    # Rs, ESTIMATE: below the same weekday last week, market-adjusted (festival removed)
    impact: dict = field(default_factory=dict)  # Merchant Impact Score, see impact_score()


# Merchant Impact Score: how badly the merchant's business is hit right now (0-100), built from three visible parts.
# This is a risk score from the signals, not a measured loss.
IMPACT_WEIGHTS = {"payments": 45, "sales": 35, "size": 20}
LARGE_MERCHANT_RS = 30000   # a normal day at or above this counts as "large"
SALES_DROP_FULL = 0.30      # a 30% market-adjusted drop counts as the full sales part


def impact_score(r) -> dict:
    fail_part = min(1.0, max(0.0, r.recent_fail - r.base_fail) / 8.0) if r.fail_p < FAIL_P_VALUE else 0.0
    offline_part = min(1.0, r.offline_days / r.window_days)
    settle_part = min(1.0, r.delay_days / r.window_days)
    parts = {
        # Can the merchant take payments and get paid? (the worst of the three)
        "payments": max(fail_part, offline_part, settle_part),
        # Are payments via Paytm below this merchant's normal? (market-adjusted, so festivals don't count)
        "sales": min(1.0, max(0.0, 1 - r.txn_adj_mean) / SALES_DROP_FULL),
        # How much business is at stake?
        "size": min(1.0, r.base_volume / LARGE_MERCHANT_RS),
    }
    score = round(sum(IMPACT_WEIGHTS[k] * v for k, v in parts.items()))
    level = "High" if score >= 60 else "Medium" if score >= 35 else "Low"

    lines = []
    if r.fail_p < FAIL_P_VALUE and r.fail_jump >= FAIL_JUMP_PP:
        lines.append(f"Failed payments at {r.recent_fail:.1f}% vs {r.base_fail:.1f}% normal: customers may be unable "
                     "to pay, and the merchant may lose sales at the counter.")
    else:
        lines.append("Failed payments are within this merchant's normal range.")
    if r.offline_days >= 1:
        lines.append(f"Soundbox offline on {int(r.offline_days)} of the last {int(r.window_days)} days: the merchant "
                     "may not hear payment confirmations.")
    else:
        lines.append("Soundbox is online and working normally.")
    if r.txn_adj_mean < 0.9:
        lines.append(f"Payments via Paytm are {1 - r.txn_adj_mean:.0%} below this merchant's normal "
                     "(same weekday, market-adjusted).")
    else:
        lines.append("Payments via Paytm are close to this merchant's normal.")
    if r.delay_days >= 1:
        lines.append(f"Money is reaching the merchant in about {r.recent_delay:.0f} hours instead of "
                     f"{r.base_delay:.0f}: this affects their daily cash flow.")
    else:
        lines.append("Settlement status is normal.")

    labels = {"payments": "Ability to take payments and get paid", "sales": "Payments vs own normal",
              "size": "Business at stake"}
    return {"score": score, "level": level, "lines": lines,
            "parts": [{"label": labels[k], "points": round(IMPACT_WEIGHTS[k] * v), "max": IMPACT_WEIGHTS[k]}
                      for k, v in parts.items()]}


def _load(as_of: int):
    tx = db.read("daily_txns", "WHERE day <= ?", (as_of,))
    dev = db.read("device_health", "WHERE day <= ?", (as_of,))
    st = db.read("settlements", "WHERE day <= ?", (as_of,))
    df = tx.merge(dev, on=["merchant_id", "day"]).merge(st[["merchant_id", "day", "delay_hours"]],
                                                       on=["merchant_id", "day"])
    df["attempts"] = df.txn_count + df.failed_count
    return df, db.read("merchants"), db.read("calendar")


def compute_signals(as_of: int) -> tuple[pd.DataFrame, dict]:
    """One row per merchant with every signal the diagnosis needs."""
    df, merchants, calendar = _load(as_of)
    recent_days = list(range(BASELINE_DAYS.stop, as_of + 1))
    base = df[df.day.isin(BASELINE_DAYS)]
    rec = df[df.day.isin(recent_days)]

    # Same weekday last week, for each recent day (removes weekend effects)
    prev = df[["merchant_id", "day", "txn_count", "volume"]].copy()
    prev["day"] += 7
    rec = rec.merge(prev, on=["merchant_id", "day"], suffixes=("", "_lastweek"))
    rec["txn_ratio"] = rec.txn_count / rec.txn_count_lastweek.clip(lower=1)
    rec["vol_ratio"] = rec.volume / rec.volume_lastweek.clip(lower=1)

    # Market index: the median merchant's ratio that day. Divide it out so festivals don't look like problems.
    market = rec.groupby("day").txn_ratio.median().rename("market_ratio")
    rec = rec.merge(market, on="day")
    rec["txn_adj"] = rec.txn_ratio / rec.market_ratio

    g_base, g_rec = base.groupby("merchant_id"), rec.groupby("merchant_id")
    s = pd.DataFrame(index=merchants.merchant_id)
    s["base_fail"] = g_base.failed_count.sum() / g_base.attempts.sum() * 100
    s["recent_fail"] = g_rec.failed_count.sum() / g_rec.attempts.sum() * 100
    s["fail_jump"] = s.recent_fail - s.base_fail
    rec["fail_hi"] = rec.failure_rate * 100 > rec.merchant_id.map(s.base_fail) + FAIL_JUMP_PP
    s["fail_hi_days"] = rec.groupby("merchant_id").fail_hi.sum()
    s["recent_failed"] = g_rec.failed_count.sum()
    s["expected_failed"] = g_rec.attempts.sum() * s.base_fail.clip(lower=NETWORK_FAIL_FLOOR) / 100
    s["fail_p"] = [poisson_tail(int(k), m) for k, m in zip(s.recent_failed, s.expected_failed)]
    s["offline_days"] = g_rec.offline_events.apply(lambda x: (x > 0).sum())
    s["offline_per_day"] = g_rec.offline_events.mean()
    s["base_signal"] = g_base.signal_strength.mean()
    s["recent_signal"] = g_rec.signal_strength.mean()
    s["base_delay"] = g_base.delay_hours.mean()
    s["recent_delay"] = g_rec.delay_hours.mean()
    s["delay_days"] = g_rec.delay_hours.apply(lambda x: (x > DELAY_HOURS).sum())
    s["txn_adj_mean"] = g_rec.txn_adj.mean()
    s["txn_drop_days"] = g_rec.txn_adj.apply(lambda x: (x < TXN_DROP_DAY).sum())
    s["ticket_ratio"] = g_rec.avg_ticket.mean() / g_base.avg_ticket.mean()
    s["base_volume"] = g_base.volume.mean()
    s["window_days"] = len(recent_days)
    s["today_vol_ratio"] = rec[rec.day == as_of].set_index("merchant_id").vol_ratio
    s["recent_volume"] = g_rec.volume.mean()

    today_market = float(market.get(as_of, 1.0))
    is_festival = bool(calendar.set_index("day").is_festival.get(as_of, False))
    context = {
        "as_of": as_of,
        "recent_days": recent_days,
        "market_ratio_today": today_market,
        "market_event_today": is_festival or today_market < FESTIVAL_MARKET_DIP,
        "festival_today": is_festival,
    }
    return s.join(merchants.set_index("merchant_id")[["name", "city", "category"]]), context


def _flags(r) -> dict:
    """Which signals are tripped, and which are sustained."""
    return {
        # Anything odd at all (one day is enough here)
        "odd_failures": r.fail_hi_days >= 1,
        "odd_offline": r.offline_days >= 1,
        "odd_signal": r.recent_signal < SIGNAL_LOW,
        "odd_settlement": r.recent_delay > 6,
        "odd_volume": r.today_vol_ratio < 0.70 or r.txn_drop_days >= 1,
        # Sustained
        "failures_up": r.fail_hi_days >= SUSTAINED_DAYS and r.fail_jump >= FAIL_JUMP_PP and r.fail_p < FAIL_P_VALUE,
        "offline": r.offline_days >= OFFLINE_DAYS,
        "signal_low": r.recent_signal < SIGNAL_LOW,
        "settlement_late": r.delay_days >= SUSTAINED_DAYS,
        "txn_down": r.txn_drop_days >= SUSTAINED_DAYS and r.txn_adj_mean < TXN_DROP_MEAN,
        "ticket_stable": TICKET_STABLE[0] <= r.ticket_ratio <= TICKET_STABLE[1],
    }


def _evidence(r, rows):
    out = []
    for key in rows:
        if key == "failures":
            out.append(dict(label="Failed transactions", baseline=f"{r.base_fail:.1f}%",
                            now=f"{r.recent_fail:.1f}% ({int(r.recent_failed)} vs ~{r.expected_failed:.0f} expected)",
                            severity="high" if r.fail_p < FAIL_P_VALUE else "normal"))
        elif key == "offline":
            out.append(dict(label="Soundbox offline (days of last 3)", baseline="0", now=f"{int(r.offline_days)}",
                            severity="high" if r.offline_days >= OFFLINE_DAYS else "normal"))
        elif key == "signal":
            out.append(dict(label="Network signal", baseline=f"{r.base_signal:.0f}", now=f"{r.recent_signal:.0f}",
                            severity="high" if r.recent_signal < SIGNAL_LOW else "normal"))
        elif key == "txns":
            out.append(dict(label="Transactions vs last week (market-adjusted)", baseline="100%",
                            now=f"{r.txn_adj_mean:.0%}", severity="high" if r.txn_adj_mean < TXN_DROP_MEAN else "normal"))
        elif key == "ticket":
            out.append(dict(label="Average bill size", baseline="100%", now=f"{r.ticket_ratio:.0%}",
                            severity="normal"))
        elif key == "settlement":
            out.append(dict(label="Settlement time", baseline=f"{r.base_delay:.0f}h", now=f"{r.recent_delay:.0f}h",
                            severity="high" if r.delay_days >= SUSTAINED_DAYS else "normal"))
        elif key == "volume":
            change = r.recent_volume / r.base_volume - 1
            out.append(dict(label="Daily volume (raw, incl. festival day)", baseline=f"₹{r.base_volume:,.0f}",
                            now=f"₹{r.recent_volume:,.0f}",
                            severity="medium" if change < -0.15 else "normal"))
    return out


def diagnose(r) -> Case | None:
    """Sustained signals -> likely cause. Confidence = share of the cause's signals that agree."""
    f = _flags(r)

    def case(cause, checks, evidence, note=""):
        agree = sum(checks)
        conf = round(min(0.95, 0.55 + 0.4 * agree / len(checks)), 2)
        if cause == "possible_app_switch":
            conf = min(conf, 0.70)  # we can't see other apps' data, so this is never more than "possible"
        return Case(r.name, r["name"], r.city, r.category, cause, conf, f"{agree} of {len(checks)} signals agree",
                    _evidence(r, evidence), note, daily_volume=int(round(r.base_volume, -1)),
                    losing_per_day=int(round(max(0.0, 1 - r.txn_adj_mean) * r.base_volume, -1)),
                    impact=impact_score(r))

    vol_not_down = r.recent_volume >= r.base_volume * 0.85
    leading = "Early warning: volume not yet down." if vol_not_down else ""

    if f["failures_up"] and f["offline"] and not f["signal_low"]:
        return case("device_fault", [f["failures_up"], f["offline"], not f["signal_low"], r.fail_hi_days >= 3],
                    ["failures", "offline", "signal", "volume"],
                    leading or "Failures and drop-outs with normal network signal point to the device itself.")
    if f["offline"] and f["signal_low"]:
        return case("sim_network", [f["offline"], f["signal_low"], r.recent_signal < r.base_signal * 0.6,
                                    r.fail_jump < FAIL_JUMP_PP * 2],
                    ["signal", "offline", "failures"], "Weak network signal with frequent short drop-outs.")
    if f["settlement_late"]:
        return case("settlement_delay", [f["settlement_late"], r.delay_days >= 3, not f["failures_up"]],
                    ["settlement", "volume"], "Payments succeed but money reaches the merchant late.")
    if f["txn_down"] and not f["failures_up"] and not f["offline"]:
        return case("possible_app_switch", [f["txn_down"], f["ticket_stable"], not f["failures_up"],
                                            not f["offline"]],
                    ["txns", "ticket", "failures", "offline"],
                    "Fewer customers paying via Paytm, while bill size, device and failures are normal. "
                    "Customers may be paying on another QR.")
    if f["failures_up"]:
        return case("payment_failures", [f["failures_up"], not f["offline"], r.fail_hi_days >= 3],
                    ["failures", "offline", "volume"], "Failures rising without device problems: bank or gateway side.")
    return None


def scan(as_of: int | None = None) -> dict:
    if as_of is None:
        as_of = int(db.read("meta", "WHERE key = 'as_of_day'").value.iloc[0])
    signals, ctx = compute_signals(as_of)

    cases, silent, ignored = [], [], []
    for _, r in signals.iterrows():
        f = _flags(r)
        if not any(v for k, v in f.items() if k.startswith("odd_")):
            continue
        c = diagnose(r)
        if c:
            cases.append(c)
        elif ctx["market_event_today"] and r.today_vol_ratio < 0.85 and f["odd_volume"]:
            silent.append(dict(merchant_id=r.name, name=r["name"], city=r.city,
                               dip=round(1 - r.today_vol_ratio, 3)))
        else:
            ignored.append(dict(merchant_id=r.name, name=r["name"], reason=_ignore_reason(f)))

    silent.sort(key=lambda x: -x["dip"])
    for c in cases:
        c.first_flag_day = first_flag_day(c.merchant_id, as_of)
    return {
        "as_of": as_of,
        "context": ctx,
        "scanned": len(signals),
        "unusual": len(cases) + len(silent) + len(ignored),
        "cases": cases,
        "stayed_silent": silent,
        "ignored_noise": ignored,
        "signals": signals,
    }


def first_flag_day(merchant_id: str, as_of: int) -> int:
    """The earliest day the engine would have flagged this merchant (re-runs the diagnosis day by day)."""
    for day in range(BASELINE_DAYS.stop, as_of):
        signals, _ = compute_signals(day)
        if diagnose(signals.loc[merchant_id]) is not None:
            return day
    return as_of


def _ignore_reason(f: dict) -> str:
    odd = [k.removeprefix("odd_") for k, v in f.items() if k.startswith("odd_") and v]
    return "One-off, not sustained: " + ", ".join(odd)
