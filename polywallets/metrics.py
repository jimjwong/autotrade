"""Per-wallet performance and behaviour metrics from a raw snapshot.

Everything here is a pure function of the snapshot dict written by
collect.snapshot_wallet, so it can be re-run offline and unit tested.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .categories import categorize

DAY = 86_400


def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _day(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def _week(ts: int) -> str:
    y, w, _ = datetime.fromtimestamp(int(ts), tz=timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


def max_drawdown(series: list[float]) -> float:
    """Largest peak-to-trough drop of a cumulative series (returned positive)."""
    peak, dd, cum = 0.0, 0.0, 0.0
    for x in series:
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


def analyze_wallet(snap: dict, meta: dict | None = None, window: tuple[int, int] | None = None) -> dict:
    """`window` narrows analysis to a sub-range of the snapshot (for walk-forward
    tests). The open book is a present-day view, so it's ignored whenever the
    window ends before the snapshot does, to avoid leaking the future."""
    meta = meta or {}
    start, end = window or (int(snap["window"]["start"]), int(snap["window"]["end"]))
    includes_present = end >= int(snap["window"]["end"])
    days = max(1, round((end - start) / DAY))

    trades = [a for a in snap.get("activity", []) if a.get("type") == "TRADE"
              and start <= int(a.get("timestamp", 0)) <= end]
    trades.sort(key=lambda a: int(a["timestamp"]))
    redeems = [a for a in snap.get("activity", []) if a.get("type") == "REDEEM"
               and start <= int(a.get("timestamp", 0)) <= end]

    # ---- trading behaviour -------------------------------------------------
    buys = [t for t in trades if t.get("side") == "BUY"]
    sells = [t for t in trades if t.get("side") == "SELL"]
    usd = [_f(t.get("usdcSize")) or _f(t.get("size")) * _f(t.get("price")) for t in trades]
    buy_usd = [_f(t.get("usdcSize")) or _f(t.get("size")) * _f(t.get("price")) for t in buys]
    volume = sum(usd)
    buy_volume = sum(buy_usd)
    sell_volume = volume - buy_volume

    def buy_share(pred) -> float:
        if not buy_volume:
            return 0.0
        return sum(u for t, u in zip(buys, buy_usd) if pred(_f(t.get("price")))) / buy_volume

    vw_entry = (sum(_f(t.get("price")) * u for t, u in zip(buys, buy_usd)) / buy_volume) if buy_volume else 0.0

    active_days = len({_day(t["timestamp"]) for t in trades})
    gaps = [int(b["timestamp"]) - int(a["timestamp"]) for a, b in zip(trades, trades[1:])]

    cat_vol: Counter = Counter()
    for t, u in zip(trades, usd):
        cat_vol[categorize(t.get("title"), t.get("eventSlug"))] += u
    cat_share = {c: v / volume for c, v in cat_vol.most_common()} if volume else {}
    hhi = sum(s * s for s in cat_share.values())
    top_cat = next(iter(cat_share), "Other")

    # Markets where the wallet bought more than one outcome: a market-making /
    # arbitrage fingerprint rather than a directional view.
    outcomes_bought: dict[str, set] = defaultdict(set)
    for t in buys:
        outcomes_bought[t.get("conditionId")].add(t.get("outcomeIndex", t.get("outcome")))
    markets = {t.get("conditionId") for t in trades}
    both_sides = (sum(1 for s in outcomes_bought.values() if len(s) > 1) / len(outcomes_bought)
                  if outcomes_bought else 0.0)

    first_buy: dict[str, int] = {}
    for t in buys:
        first_buy.setdefault(t.get("asset"), int(t["timestamp"]))

    # ---- realized results -------------------------------------------------
    closed = [c for c in snap.get("closed_positions", []) if start <= int(c.get("timestamp", 0)) <= end]
    pnls = [_f(c.get("realizedPnl")) for c in closed]
    cost = sum(_f(c.get("totalBought")) * _f(c.get("avgPrice")) for c in closed)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    realized = sum(pnls)

    daily: dict[str, float] = defaultdict(float)
    weekly: dict[str, float] = defaultdict(float)
    for c, p in zip(closed, pnls):
        daily[_day(c["timestamp"])] += p
        weekly[_week(c["timestamp"])] += p
    day_series = [daily[k] for k in sorted(daily)]
    # Sharpe over calendar days in the window (days with no closes count as 0)
    # so wallets that close rarely don't look artificially smooth.
    full = day_series + [0.0] * max(0, days - len(day_series))
    sd = statistics.pstdev(full) if len(full) > 1 else 0.0
    sharpe = (statistics.fmean(full) / sd * math.sqrt(365)) if sd > 0 else 0.0

    by_market: dict[str, float] = defaultdict(float)
    for c, p in zip(closed, pnls):
        by_market[c.get("conditionId") or c.get("title")] += p
    gross_win = sum(p for p in by_market.values() if p > 0)
    top_market_share = (max(by_market.values()) / gross_win) if gross_win > 0 else 0.0

    holds = [(int(c["timestamp"]) - first_buy[c.get("asset")]) / 3600 for c in closed
             if c.get("asset") in first_buy and int(c["timestamp"]) >= first_buy[c.get("asset")]]

    best = max(closed, key=lambda c: _f(c.get("realizedPnl")), default=None)
    worst = min(closed, key=lambda c: _f(c.get("realizedPnl")), default=None)

    # ---- open book --------------------------------------------------------
    open_pos = [p for p in snap.get("positions", []) if _f(p.get("size")) > 0] if includes_present else []
    live = [p for p in open_pos if not p.get("redeemable")]
    unredeemed = [p for p in open_pos if p.get("redeemable")]
    unrealized = sum(_f(p.get("cashPnl")) for p in live)
    # Resolved-but-not-yet-redeemed positions are economically realized.
    pending_realized = sum(_f(p.get("cashPnl")) for p in unredeemed)

    weekly_vals = list(weekly.values())
    return {
        "wallet": snap["wallet"],
        "userName": meta.get("userName", ""),
        "xUsername": meta.get("xUsername", ""),
        "verified": meta.get("verified", False),
        "boards": [f"{b['board']}#{b['rank']}" for b in meta.get("boards", [])],
        "days": days,
        "window_end": end,
        "portfolio_value": _f(snap.get("value")),

        "realized_pnl": realized,
        "pending_realized_pnl": pending_realized,
        "unrealized_pnl": unrealized,
        "total_pnl": realized + pending_realized + unrealized,
        "roi": (realized / cost) if cost > 0 else 0.0,
        "n_closed": len(closed),
        "win_rate": (len(wins) / len(pnls)) if pnls else 0.0,
        "avg_win": statistics.fmean(wins) if wins else 0.0,
        "avg_loss": statistics.fmean(losses) if losses else 0.0,
        "profit_factor": (sum(wins) / -sum(losses)) if losses else (math.inf if wins else 0.0),
        "sharpe": sharpe,
        "max_drawdown": max_drawdown(day_series),
        "profitable_day_rate": (sum(1 for v in day_series if v > 0) / len(day_series)) if day_series else 0.0,
        "profitable_week_rate": (sum(1 for v in weekly_vals if v > 0) / len(weekly_vals)) if weekly_vals else 0.0,
        "top_market_share": top_market_share,
        "median_hold_hours": statistics.median(holds) if holds else None,
        "best_trade": {"title": best.get("title"), "outcome": best.get("outcome"),
                       "pnl": _f(best.get("realizedPnl"))} if best else None,
        "worst_trade": {"title": worst.get("title"), "outcome": worst.get("outcome"),
                        "pnl": _f(worst.get("realizedPnl"))} if worst else None,

        "n_trades": len(trades),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "n_redeems": len(redeems),
        "volume": volume,
        "sell_ratio": (sell_volume / volume) if volume else 0.0,
        "avg_trade_usd": (volume / len(trades)) if trades else 0.0,
        "median_trade_usd": statistics.median(usd) if usd else 0.0,
        "max_trade_usd": max(usd, default=0.0),
        "active_days": active_days,
        "trades_per_active_day": (len(trades) / active_days) if active_days else 0.0,
        "median_gap_seconds": statistics.median(gaps) if gaps else None,
        "markets_traded": len(markets),
        "vw_entry_price": vw_entry,
        "longshot_share": buy_share(lambda p: p <= 0.15),
        "favorite_share": buy_share(lambda p: 0.70 <= p < 0.93),
        "sweeper_share": buy_share(lambda p: p >= 0.93),
        "both_sides_rate": both_sides,
        "category_share": cat_share,
        "top_category": top_cat,
        "category_hhi": hhi,
        "open_positions": len(live),
        "open_value": sum(_f(p.get("currentValue")) for p in live),
        "daily_pnl": dict(sorted(daily.items())),
        "first_trade_ts": int(trades[0]["timestamp"]) if trades else None,
        "last_trade_ts": int(trades[-1]["timestamp"]) if trades else None,
    }
