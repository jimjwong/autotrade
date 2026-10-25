"""Offline tests. All market data here is synthetic and only exercises the math."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from polywallets import cli
from polywallets.backtest import simulate_copy, walk_forward
from polywallets.categories import categorize
from polywallets.collect import collect
from polywallets.metrics import analyze_wallet, max_drawdown
from polywallets.score import _pct_rank, score_cohort

DAY = 86_400
END = 1_760_000_000
START = END - 90 * DAY


def trade(ts, side, asset, price, usd, title="Will BTC be above 100k?", cond=None, outcome="Yes", oi=0):
    return {"type": "TRADE", "timestamp": ts, "side": side, "asset": asset, "price": price,
            "size": usd / price, "usdcSize": usd, "conditionId": cond or f"c-{asset}", "title": title,
            "outcome": outcome, "outcomeIndex": oi, "transactionHash": f"0x{ts}{asset}{side}"}


def closed(ts, asset, pnl, bought=1000, avg=0.5, cur=1.0, title="m"):
    return {"timestamp": ts, "asset": asset, "conditionId": f"c-{asset}", "realizedPnl": pnl,
            "totalBought": bought, "avgPrice": avg, "curPrice": cur, "title": title, "outcome": "Yes"}


def make_snap(wallet, n=40, edge=0.6, size=200.0, price=0.5, start=START, end=END):
    """A wallet that buys n markets evenly over the window; every k-th one wins."""
    act, cps = [], []
    for i in range(n):
        ts = start + int((i + 0.5) * (end - start) / n)
        a = f"{wallet}-a{i}"
        act.append(trade(ts, "BUY", a, price, size))
        win = (i % 10) < edge * 10
        shares = size / price
        cps.append(closed(ts + 3600, a, shares * (1 - price) if win else -size, bought=shares, avg=price,
                          cur=1.0 if win else 0.0))
    return {"wallet": wallet, "window": {"start": start, "end": end}, "activity": act,
            "positions": [], "closed_positions": cps, "value": 1000.0}


class TestPrimitives(unittest.TestCase):
    def test_categorize(self):
        self.assertEqual(categorize("Bitcoin Up or Down - Oct 3"), "Crypto")
        self.assertEqual(categorize("Lakers vs. Celtics"), "Sports")
        self.assertEqual(categorize("Fed decision in December?"), "Economics")
        self.assertEqual(categorize("Who will win the NYC mayoral election?"), "Politics")
        self.assertEqual(categorize("Russia x Ukraine ceasefire in 2026?"), "Geopolitics")
        self.assertEqual(categorize("Something unusual"), "Other")

    def test_max_drawdown(self):
        self.assertEqual(max_drawdown([10, -4, -3, 5, -10]), 12)
        self.assertEqual(max_drawdown([1, 2, 3]), 0)

    def test_pct_rank_ties(self):
        self.assertEqual(_pct_rank([5, 1, 5, 3]), [5 / 6, 0.0, 5 / 6, 1 / 3])


class TestMetrics(unittest.TestCase):
    def test_basic(self):
        m = analyze_wallet(make_snap("0xa", n=40, edge=0.6), {"userName": "alice"})
        self.assertEqual(m["n_closed"], 40)
        self.assertAlmostEqual(m["win_rate"], 0.6)
        self.assertAlmostEqual(m["realized_pnl"], 24 * 200 - 16 * 200)
        self.assertAlmostEqual(m["roi"], 1600 / 8000)
        self.assertAlmostEqual(m["vw_entry_price"], 0.5)
        self.assertEqual(m["top_category"], "Crypto")
        self.assertAlmostEqual(m["median_hold_hours"], 1.0)
        self.assertEqual(m["userName"], "alice")

    def test_window_excludes_open_book_when_historical(self):
        s = make_snap("0xa")
        s["positions"] = [{"size": 10, "cashPnl": 999, "currentValue": 5, "redeemable": False}]
        self.assertEqual(analyze_wallet(s)["unrealized_pnl"], 999)
        self.assertEqual(analyze_wallet(s, window=(START, END - 30 * DAY))["unrealized_pnl"], 0)

    def test_both_sides_and_sweeper(self):
        s = make_snap("0xb", n=0)
        s["activity"] = [trade(START + 10, "BUY", "y", 0.96, 1000, cond="c1", oi=0),
                         trade(START + 20, "BUY", "n", 0.03, 10, cond="c1", oi=1)]
        m = analyze_wallet(s)
        self.assertEqual(m["both_sides_rate"], 1.0)
        self.assertGreater(m["sweeper_share"], 0.98)


class TestScore(unittest.TestCase):
    def test_ranks_consistent_over_lucky(self):
        steady = analyze_wallet(make_snap("0xsteady", n=60, edge=0.7))
        lucky = make_snap("0xlucky", n=5, edge=0.2)
        lucky["closed_positions"][0]["realizedPnl"] = 50_000
        lucky = analyze_wallet(lucky)
        loser = analyze_wallet(make_snap("0xloser", n=40, edge=0.3))
        rows = score_cohort([lucky, loser, steady])
        self.assertEqual([r["wallet"] for r in rows][0], "0xsteady")
        self.assertIn("One-hit", rows[1]["tags"] if rows[1]["wallet"] == "0xlucky" else rows[2]["tags"])
        self.assertIn("not profitable in window", next(r for r in rows if r["wallet"] == "0xloser")["penalties"])


class TestBacktest(unittest.TestCase):
    def test_copy_resolution(self):
        s = make_snap("0xa", n=10, edge=0.6, price=0.5)
        res = simulate_copy(s, stake=100, slippage=0.0)
        self.assertEqual(res["copied_trades"], 10)
        self.assertAlmostEqual(res["invested"], 1000)
        self.assertAlmostEqual(res["value"], 6 * 200)  # 6 winners * 200 shares * $1

    def test_slippage_and_mirrored_sell(self):
        s = make_snap("0xa", n=0)
        s["activity"] = [trade(START + 1, "BUY", "x", 0.40, 400),
                         trade(START + 2, "SELL", "x", 0.60, 300)]  # leader sells half (500 of 1000 shares)
        s["closed_positions"] = [closed(START + 3, "x", 0, cur=0.0)]
        res = simulate_copy(s, stake=100, slippage=0.1)
        shares = 100 / 0.5
        self.assertAlmostEqual(res["value"], shares / 2 * 0.5)

    def test_filters(self):
        s = make_snap("0xa", n=0)
        s["activity"] = [trade(START + 1, "BUY", "x", 0.99, 5000), trade(START + 2, "BUY", "y", 0.5, 10)]
        self.assertEqual(simulate_copy(s)["copied_trades"], 0)

    def test_walk_forward(self):
        snaps = [make_snap(f"0x{i}", n=60, edge=e) for i, e in enumerate([0.8, 0.6, 0.4, 0.2])]
        wf = walk_forward(snaps, {}, test_days=30, top_n=2, slippage=0.0)
        self.assertEqual(len(wf["by_score"]["wallets"]), 2)
        self.assertGreater(wf["by_score"]["pnl"], wf["everyone"]["pnl"])


class FakeClient:
    """Stands in for PolymarketClient; serves the synthetic snapshots."""

    def __init__(self, snaps):
        self.snaps = {s["wallet"]: s for s in snaps}

    def leaderboard(self, time_period, order_by, limit, offset, **_):
        ws = list(self.snaps)[offset:offset + limit]
        return [{"rank": offset + i + 1, "proxyWallet": w, "userName": f"user{w}", "pnl": 1, "vol": 1}
                for i, w in enumerate(ws)]

    def activity_since(self, user, start_ts, end_ts=None, **_):
        return [a for a in self.snaps[user]["activity"] if start_ts <= a["timestamp"] <= (end_ts or 2**40)]

    def positions(self, user):
        return self.snaps[user]["positions"]

    def closed_positions(self, user, since_ts):
        return self.snaps[user]["closed_positions"]

    def portfolio_value(self, user):
        return 1.0


class TestEndToEnd(unittest.TestCase):
    def test_collect_analyze(self):
        import time as _t
        now = int(_t.time())
        snaps = [make_snap(f"0x{i:040x}", n=50, edge=e, start=now - 90 * DAY, end=now)
                 for i, e in enumerate([0.8, 0.7, 0.5, 0.3, 0.6])]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            collect(d / "data", days=90, per_board=10, client=FakeClient(snaps), log=lambda *_: None)
            self.assertEqual(len(list((d / "data" / "raw").glob("*.json"))), 5)
            cli.main(["analyze", "--data", str(d / "data"), "--out", str(d / "out"), "--top-n", "3"])
            payload = json.loads((d / "out" / "analysis.json").read_text())
            self.assertEqual(len(payload["wallets"]), 5)
            self.assertEqual(payload["wallets"][0]["wallet"], snaps[0]["wallet"])
            self.assertTrue(payload["walk_forward"]["by_score"]["wallets"])
            html = (d / "out" / "report.html").read_text()
            self.assertNotIn("__DATA__", html)
            self.assertEqual(len(json.loads((d / "out" / "watchlist.json").read_text())), 3)
            for r in payload["wallets"]:
                self.assertFalse(any(isinstance(v, float) and math.isinf(v) for v in r.values()))


if __name__ == "__main__":
    unittest.main()
