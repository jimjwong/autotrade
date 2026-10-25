"""Archetype tagging and a cohort-relative "copyability" score.

The score answers a narrower question than "who made the most money": which
wallets show a repeatable edge that a follower could plausibly capture after
seeing the trade a few seconds to minutes late. Raw PnL rewards one lucky
election bet and market makers whose edge is the spread itself; neither is
something you can copy.
"""

from __future__ import annotations

import math


def archetypes(m: dict) -> list[str]:
    tags: list[str] = []
    if m["trades_per_active_day"] >= 150 or (m["both_sides_rate"] >= 0.35 and m["n_trades"] >= 200):
        tags.append("Market maker / bot")
    if m["sweeper_share"] >= 0.5:
        tags.append("Resolution sweeper")
    if m["longshot_share"] >= 0.35:
        tags.append("Longshot hunter")
    if m["favorite_share"] >= 0.5:
        tags.append("Favorite grinder")
    if m["median_trade_usd"] >= 5_000 and m["markets_traded"] <= 40:
        tags.append("Whale conviction")
    if m["sell_ratio"] >= 0.4 and "Market maker / bot" not in tags:
        tags.append("Swing trader")
    if m["category_share"] and m["category_share"].get(m["top_category"], 0) >= 0.7:
        tags.append(f"{m['top_category']} specialist")
    if m["top_market_share"] >= 0.6 and m["realized_pnl"] > 0:
        tags.append("One-hit")
    return tags or ["Generalist"]


def _pct_rank(values: list[float]) -> list[float]:
    """Percentile rank in [0, 1] with ties averaged."""
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2 / (n - 1)
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def score_cohort(rows: list[dict]) -> list[dict]:
    """Mutates and returns rows with tags, score components and final score."""
    if not rows:
        return rows

    def signed_log(x: float) -> float:
        return math.copysign(math.log1p(abs(x)), x)

    pnl_r = _pct_rank([signed_log(r["realized_pnl"] + r["pending_realized_pnl"]) for r in rows])
    roi_r = _pct_rank([max(-1.0, min(r["roi"], 5.0)) for r in rows])
    sharpe_r = _pct_rank([max(-5.0, min(r["sharpe"], 10.0)) for r in rows])
    week_r = _pct_rank([r["profitable_week_rate"] for r in rows])
    pf_r = _pct_rank([min(r["profit_factor"], 10.0) for r in rows])

    for i, r in enumerate(rows):
        r["tags"] = archetypes(r)
        profit = 0.55 * pnl_r[i] + 0.45 * roi_r[i]
        consistency = 0.45 * sharpe_r[i] + 0.35 * week_r[i] + 0.20 * pf_r[i]

        # Multiplicative penalties in (0, 1]: each reflects a reason a follower
        # wouldn't reproduce the result.
        penalties: dict[str, float] = {}
        if r["n_closed"] < 30:
            penalties["small sample"] = 0.4 + 0.6 * r["n_closed"] / 30
        if r["top_market_share"] > 0.4:
            penalties["concentrated in one market"] = max(0.3, 1.4 - r["top_market_share"] * 1.25)
        if "Market maker / bot" in r["tags"]:
            penalties["too fast to follow"] = 0.35
        if r["sweeper_share"] > 0.3:
            # Buying at 0.95+ leaves ~5c of edge, which latency and slippage eat.
            penalties["thin-edge sweeping"] = max(0.4, 1.3 - r["sweeper_share"])
        if r["median_trade_usd"] > 25_000:
            penalties["moves the book"] = 0.75
        if not r["last_trade_ts"] or r["last_trade_ts"] < r["window_end"] - 21 * 86_400:
            penalties["inactive 3+ weeks"] = 0.6
        if r["realized_pnl"] + r["pending_realized_pnl"] <= 0:
            penalties["not profitable in window"] = 0.3

        mult = 1.0
        for v in penalties.values():
            mult *= v
        r["score_profit"] = round(100 * profit, 1)
        r["score_consistency"] = round(100 * consistency, 1)
        r["penalties"] = {k: round(v, 2) for k, v in penalties.items()}
        r["score"] = round(100 * (0.5 * profit + 0.5 * consistency) * mult, 1)

    rows.sort(key=lambda r: r["score"], reverse=True)
    for rank, r in enumerate(rows, 1):
        r["copy_rank"] = rank
    return rows
