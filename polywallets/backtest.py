"""Copy-trade simulation and walk-forward validation.

`simulate_copy` replays a wallet's trades as a follower would have taken them:
a fixed stake per BUY at a worse price (slippage), mirroring SELLs by the same
fraction of the position the leader sold, and marking whatever is left at the
latest known price (1/0 for resolved markets).

`walk_forward` is the honest version of "who should I copy": rank wallets on
the first part of the window only, then measure what copying the top-N would
have earned in the remaining, unseen part.
"""

from __future__ import annotations

from collections import defaultdict

from .metrics import analyze_wallet
from .score import score_cohort

DAY = 86_400


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def mark_prices(snap: dict) -> dict[str, float]:
    """Best available current price per outcome token."""
    marks: dict[str, float] = {}
    for a in sorted(snap.get("activity", []), key=lambda a: int(a.get("timestamp", 0))):
        if a.get("type") == "TRADE" and a.get("asset"):
            marks[a["asset"]] = _f(a.get("price"))
    for c in snap.get("closed_positions", []):
        if c.get("asset") and c.get("curPrice") is not None:
            marks[c["asset"]] = _f(c["curPrice"])
    for p in snap.get("positions", []):
        if p.get("asset") and p.get("curPrice") is not None:
            marks[p["asset"]] = _f(p["curPrice"])
    return marks


def simulate_copy(snap: dict, start: int | None = None, end: int | None = None, stake: float = 100.0,
                  slippage: float = 0.02, min_leader_usd: float = 50.0, max_entry: float = 0.97) -> dict:
    """slippage is in price units (0.02 = pay 2c more per share than the leader)."""
    start = start if start is not None else int(snap["window"]["start"])
    end = end if end is not None else int(snap["window"]["end"])
    marks = mark_prices(snap)

    trades = sorted((a for a in snap.get("activity", []) if a.get("type") == "TRADE"
                     and start <= int(a.get("timestamp", 0)) <= end), key=lambda a: int(a["timestamp"]))

    leader_shares: dict[str, float] = defaultdict(float)
    mine: dict[str, float] = defaultdict(float)
    invested: dict[str, float] = defaultdict(float)
    proceeds: dict[str, float] = defaultdict(float)
    titles: dict[str, str] = {}
    copied = skipped = 0

    for t in trades:
        asset, price, size = t.get("asset"), _f(t.get("price")), _f(t.get("size"))
        usd = _f(t.get("usdcSize")) or size * price
        titles[asset] = f"{t.get('title', '')} [{t.get('outcome', '')}]"
        if t.get("side") == "BUY":
            leader_shares[asset] += size
            fill = min(0.999, price + slippage)
            if usd < min_leader_usd or price > max_entry or fill <= 0:
                skipped += 1
                continue
            mine[asset] += stake / fill
            invested[asset] += stake
            copied += 1
        elif t.get("side") == "SELL":
            held = leader_shares[asset]
            leader_shares[asset] = max(0.0, held - size)
            if mine[asset] <= 0 or held <= 0:
                continue
            frac = min(1.0, size / held)
            qty = mine[asset] * frac
            mine[asset] -= qty
            proceeds[asset] += qty * max(0.0, price - slippage)

    per_asset = []
    for asset, spent in invested.items():
        value = proceeds[asset] + mine[asset] * marks.get(asset, 0.0)
        per_asset.append({"asset": asset, "market": titles.get(asset, ""), "invested": spent,
                          "value": value, "pnl": value - spent})
    total_in = sum(invested.values())
    total_val = sum(p["value"] for p in per_asset)
    per_asset.sort(key=lambda p: p["pnl"])
    return {
        "wallet": snap["wallet"],
        "copied_trades": copied,
        "skipped_trades": skipped,
        "markets": len(per_asset),
        "invested": total_in,
        "value": total_val,
        "pnl": total_val - total_in,
        "roi": (total_val - total_in) / total_in if total_in else 0.0,
        "market_hit_rate": (sum(1 for p in per_asset if p["pnl"] > 0) / len(per_asset)) if per_asset else 0.0,
        "worst_markets": per_asset[:3],
        "best_markets": per_asset[-3:][::-1],
    }


def walk_forward(snaps: list[dict], metas: dict[str, dict], test_days: int = 30, top_n: int = 10,
                 **sim_kwargs) -> dict:
    """Score on [start, split), copy the top_n on [split, end]. Compare to copying
    the top_n by raw training-window PnL, and to copying everyone."""
    if not snaps:
        return {}
    start = int(snaps[0]["window"]["start"])
    end = int(snaps[0]["window"]["end"])
    split = end - test_days * DAY

    train = score_cohort([analyze_wallet(s, metas.get(s["wallet"]), window=(start, split)) for s in snaps])
    by_wallet = {s["wallet"]: s for s in snaps}

    def run(wallets: list[str]) -> dict:
        sims = [simulate_copy(by_wallet[w], split, end, **sim_kwargs) for w in wallets]
        inv = sum(s["invested"] for s in sims)
        pnl = sum(s["pnl"] for s in sims)
        return {"wallets": wallets, "invested": inv, "pnl": pnl, "roi": pnl / inv if inv else 0.0,
                "per_wallet": sorted(({"wallet": s["wallet"], "pnl": s["pnl"], "roi": s["roi"],
                                       "copied_trades": s["copied_trades"]} for s in sims),
                                     key=lambda x: x["pnl"], reverse=True)}

    by_pnl = sorted(train, key=lambda r: r["realized_pnl"] + r["pending_realized_pnl"], reverse=True)
    return {
        "train_window": [start, split],
        "test_window": [split, end],
        "top_n": top_n,
        "by_score": run([r["wallet"] for r in train[:top_n]]),
        "by_raw_pnl": run([r["wallet"] for r in by_pnl[:top_n]]),
        "everyone": run([r["wallet"] for r in train]),
    }
