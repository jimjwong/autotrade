"""Discover top wallets and snapshot their last-N-days data to disk.

Polymarket's leaderboard only offers DAY / WEEK / MONTH / ALL windows, so we
seed a broad candidate pool from several boards (PnL and volume, month and
all-time) and then recompute everything over our own 90-day window from raw
activity. That way a wallet that was great 60 days ago but quiet this month
still gets picked up, and all-time whales who've gone cold get scored fairly.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .api import ApiError, PolymarketClient

DAY = 86_400

SEED_BOARDS = [
    ("MONTH", "PNL"),
    ("MONTH", "VOL"),
    ("WEEK", "PNL"),
    ("ALL", "PNL"),
]


def discover_wallets(client: PolymarketClient, per_board: int = 200, log=print) -> dict[str, dict]:
    """Return {wallet: {userName, boards: [...], ...}} merged across seed boards."""
    pool: dict[str, dict] = {}
    for period, order in SEED_BOARDS:
        fetched = 0
        offset = 0
        while fetched < per_board:
            limit = min(50, per_board - fetched)
            try:
                rows = client.leaderboard(time_period=period, order_by=order, limit=limit, offset=offset)
            except ApiError as e:
                log(f"  ! leaderboard {period}/{order} offset {offset}: {e}")
                break
            if not rows:
                break
            for r in rows:
                w = (r.get("proxyWallet") or "").lower()
                if not w:
                    continue
                entry = pool.setdefault(w, {
                    "wallet": w,
                    "userName": r.get("userName") or "",
                    "xUsername": r.get("xUsername") or "",
                    "verified": bool(r.get("verifiedBadge")),
                    "boards": [],
                })
                entry["boards"].append({"board": f"{period}/{order}", "rank": int(r.get("rank") or 0),
                                        "pnl": float(r.get("pnl") or 0), "vol": float(r.get("vol") or 0)})
            fetched += len(rows)
            offset += len(rows)
            if len(rows) < limit:
                break
        log(f"  leaderboard {period}/{order}: {fetched} rows")
    return pool


def snapshot_wallet(client: PolymarketClient, wallet: str, start_ts: int, end_ts: int) -> dict:
    return {
        "wallet": wallet,
        "window": {"start": start_ts, "end": end_ts},
        "fetched_at": int(time.time()),
        "activity": client.activity_since(wallet, start_ts, end_ts),
        "positions": client.positions(wallet),
        "closed_positions": client.closed_positions(wallet, start_ts),
        "value": client.portfolio_value(wallet),
    }


def collect(out_dir: Path, days: int = 90, per_board: int = 200, max_wallets: int | None = None,
            refresh: bool = False, client: PolymarketClient | None = None, log=print) -> Path:
    """Fetch everything into out_dir/{wallets.json, raw/<wallet>.json}. Resumable."""
    client = client or PolymarketClient()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(exist_ok=True)

    end_ts = int(time.time())
    start_ts = end_ts - days * DAY

    log(f"Discovering wallets from {len(SEED_BOARDS)} leaderboards...")
    pool = discover_wallets(client, per_board=per_board, log=log)
    wallets = sorted(pool.values(), key=lambda e: min(b["rank"] for b in e["boards"]))
    if max_wallets:
        wallets = wallets[:max_wallets]
    (out_dir / "wallets.json").write_text(json.dumps(
        {"days": days, "start": start_ts, "end": end_ts, "wallets": wallets}, indent=1))
    log(f"{len(wallets)} unique wallets. Fetching {days}d history...")

    for i, w in enumerate(wallets, 1):
        path = raw_dir / f"{w['wallet']}.json"
        if path.exists() and not refresh:
            continue
        try:
            snap = snapshot_wallet(client, w["wallet"], start_ts, end_ts)
        except ApiError as e:
            log(f"  [{i}/{len(wallets)}] {w['wallet']} FAILED: {e}")
            continue
        path.write_text(json.dumps(snap))
        log(f"  [{i}/{len(wallets)}] {w['userName'] or w['wallet'][:10]}: "
            f"{len(snap['activity'])} events, {len(snap['closed_positions'])} closed, "
            f"{len(snap['positions'])} open")
    return out_dir
