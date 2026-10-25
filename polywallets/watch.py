"""Live copy-signal feed with a paper-trading ledger.

Polls the activity of the top-scored wallets and emits a signal for each new
trade that passes the same filters the backtest uses. Signals are appended to
signals.jsonl and mirrored into a paper portfolio (paper.json) so you can see
how following them would be going before risking anything. No orders are
placed.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from .api import ApiError, PolymarketClient


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


class PaperBook:
    def __init__(self, path: Path, stake: float, slippage: float):
        self.path = path
        self.stake = stake
        self.slippage = slippage
        self.state = json.loads(path.read_text()) if path.exists() else {"cash_spent": 0.0, "proceeds": 0.0,
                                                                          "positions": {}, "leader": {}}

    def on_trade(self, wallet: str, t: dict, copy_buy: bool) -> None:
        asset, price, size = t.get("asset"), _f(t.get("price")), _f(t.get("size"))
        key = f"{wallet}:{asset}"
        pos = self.state["positions"].setdefault(key, {"shares": 0.0, "cost": 0.0, "title": t.get("title"),
                                                       "outcome": t.get("outcome"), "last": price})
        pos["last"] = price
        leader = self.state["leader"]
        if t.get("side") == "BUY":
            leader[key] = leader.get(key, 0.0) + size
            if copy_buy:
                fill = min(0.999, price + self.slippage)
                pos["shares"] += self.stake / fill
                pos["cost"] += self.stake
                self.state["cash_spent"] += self.stake
        else:
            held = leader.get(key, 0.0)
            leader[key] = max(0.0, held - size)
            if held > 0 and pos["shares"] > 0:
                qty = pos["shares"] * min(1.0, size / held)
                pos["cost"] *= 1 - qty / pos["shares"]
                pos["shares"] -= qty
                self.state["proceeds"] += qty * max(0.0, price - self.slippage)

    def summary(self) -> dict:
        mtm = sum(p["shares"] * p["last"] for p in self.state["positions"].values())
        spent, got = self.state["cash_spent"], self.state["proceeds"]
        return {"spent": spent, "proceeds": got, "open_value": mtm, "pnl": got + mtm - spent}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, indent=1))


def watch(wallets: list[dict], out_dir: Path, interval: int = 30, stake: float = 100.0,
          slippage: float = 0.02, min_leader_usd: float = 50.0, max_entry: float = 0.97,
          client: PolymarketClient | None = None, iterations: int | None = None, log=print) -> None:
    client = client or PolymarketClient(min_interval=0.1)
    out_dir.mkdir(parents=True, exist_ok=True)
    cursor_path = out_dir / "cursor.json"
    cursors: dict[str, int] = json.loads(cursor_path.read_text()) if cursor_path.exists() else {}
    book = PaperBook(out_dir / "paper.json", stake, slippage)
    names = {w["wallet"]: w.get("userName") or w["wallet"][:10] for w in wallets}
    now = int(time.time())
    for w in names:
        cursors.setdefault(w, now)  # only trades from here on

    log(f"Watching {len(names)} wallets every {interval}s. Ctrl-C to stop.")
    n = 0
    while iterations is None or n < iterations:
        n += 1
        for w, name in names.items():
            try:
                rows = client.activity_since(w, cursors[w] + 1, page_size=100, max_rows=500)
            except ApiError as e:
                log(f"  ! {name}: {e}")
                continue
            trades = sorted((r for r in rows if r.get("type") == "TRADE"), key=lambda r: int(r["timestamp"]))
            for t in trades:
                cursors[w] = max(cursors[w], int(t["timestamp"]))
                price, usd = _f(t.get("price")), _f(t.get("usdcSize"))
                copy = t.get("side") == "BUY" and usd >= min_leader_usd and price <= max_entry
                book.on_trade(w, t, copy)
                if t.get("side") == "SELL" or copy:
                    sig = {"ts": int(t["timestamp"]), "wallet": w, "name": name, "side": t.get("side"),
                           "market": t.get("title"), "outcome": t.get("outcome"), "price": price,
                           "leader_usd": usd, "slug": t.get("slug"), "asset": t.get("asset"),
                           "tx": t.get("transactionHash")}
                    with (out_dir / "signals.jsonl").open("a") as f:
                        f.write(json.dumps(sig) + "\n")
                    when = datetime.fromtimestamp(sig["ts"]).strftime("%H:%M:%S")
                    log(f"{when}  {name:<18} {sig['side']:<4} {sig['outcome'] or '':<6} @ {price:.3f}  "
                        f"${usd:>10,.0f}  {sig['market']}")
        cursor_path.write_text(json.dumps(cursors))
        book.save()
        s = book.summary()
        log(f"  paper: spent ${s['spent']:,.0f}  open ${s['open_value']:,.0f}  pnl ${s['pnl']:+,.0f}")
        if iterations is None or n < iterations:
            time.sleep(interval)
