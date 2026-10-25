"""Command line entry point: python -m polywallets <command>."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import report
from .analyze import analyze, cohort_summary, load
from .backtest import simulate_copy, walk_forward
from .collect import collect


def cmd_collect(a) -> None:
    collect(Path(a.data), days=a.days, per_board=a.per_board, max_wallets=a.max_wallets, refresh=a.refresh)


def cmd_analyze(a) -> None:
    data, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    index, snaps, metas = load(data)
    if not snaps:
        sys.exit(f"No snapshots in {data}/raw. Run `collect` first.")
    rows = analyze(snaps, metas)
    sim = {"stake": a.stake, "slippage": a.slippage, "min_leader_usd": a.min_leader_usd, "max_entry": a.max_entry}
    by_wallet = {s["wallet"]: s for s in snaps}
    for r in rows:
        r["copy"] = simulate_copy(by_wallet[r["wallet"]], **sim)
    wf = walk_forward(snaps, metas, test_days=a.test_days, top_n=a.top_n, **sim) if index["days"] > a.test_days else {}

    payload = {"generated": int(time.time()), "days": index["days"], "window": [index["start"], index["end"]],
               "sim": sim, "summary": cohort_summary(rows), "walk_forward": wf, "wallets": rows}
    report.write_json(payload, out / "analysis.json")
    report.write_csv(rows, out / "leaderboard.csv")
    report.write_html(payload, out / "report.html")
    (out / "watchlist.json").write_text(json.dumps(
        [{"wallet": r["wallet"], "userName": r["userName"], "score": r["score"], "tags": r["tags"]}
         for r in rows[:a.top_n]], indent=1))

    print(f"\nTop {min(15, len(rows))} by copy score ({index['days']}d):")
    print(f"{'#':>3} {'wallet':<22} {'score':>6} {'realized':>12} {'roi':>7} {'win%':>6} {'closed':>6}  type")
    for r in rows[:15]:
        print(f"{r['copy_rank']:>3} {(r['userName'] or r['wallet'][:12])[:22]:<22} {r['score']:>6.1f} "
              f"{r['realized_pnl']:>12,.0f} {r['roi']:>7.1%} {r['win_rate']:>6.1%} {r['n_closed']:>6}  "
              f"{', '.join(r['tags'])}")
    if wf:
        print(f"\nWalk-forward (rank on first {index['days'] - a.test_days}d, copy last {a.test_days}d):")
        for k, label in [("by_score", "top by score"), ("by_raw_pnl", "top by raw PnL"), ("everyone", "everyone")]:
            x = wf[k]
            print(f"  {label:<16} pnl {x['pnl']:>+12,.0f}  roi {x['roi']:>+7.1%}  on ${x['invested']:,.0f}")
    print(f"\nWrote {out}/report.html, leaderboard.csv, analysis.json, watchlist.json")


def cmd_watch(a) -> None:
    from .watch import watch

    wallets = json.loads(Path(a.watchlist).read_text())[:a.top_n]
    try:
        watch(wallets, Path(a.out), interval=a.interval, stake=a.stake, slippage=a.slippage,
              min_leader_usd=a.min_leader_usd, max_entry=a.max_entry)
    except KeyboardInterrupt:
        print("\nstopped")


def cmd_run(a) -> None:
    cmd_collect(a)
    cmd_analyze(a)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="polywallets", description="Analyze and follow top Polymarket wallets.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, collect_args=False, analyze_args=False):
        sp.add_argument("--data", default="data", help="snapshot directory (default: data)")
        sp.add_argument("--out", default="out", help="output directory (default: out)")
        if collect_args:
            sp.add_argument("--days", type=int, default=90)
            sp.add_argument("--per-board", type=int, default=200, help="wallets per seed leaderboard")
            sp.add_argument("--max-wallets", type=int, default=None)
            sp.add_argument("--refresh", action="store_true", help="re-download wallets already on disk")
        sp.add_argument("--stake", type=float, default=100.0, help="paper $ per copied buy")
        sp.add_argument("--slippage", type=float, default=0.02, help="price units, 0.02 = 2c worse fill")
        sp.add_argument("--min-leader-usd", type=float, default=50.0, help="ignore leader trades smaller than this")
        sp.add_argument("--max-entry", type=float, default=0.97, help="don't copy buys priced above this")
        sp.add_argument("--top-n", type=int, default=10)
        if analyze_args:
            sp.add_argument("--test-days", type=int, default=30, help="walk-forward holdout length")

    common(sub.add_parser("collect", help="download leaderboard wallets + 90d history"), collect_args=True)
    common(sub.add_parser("analyze", help="score wallets and write reports"), analyze_args=True)
    common(sub.add_parser("run", help="collect then analyze"), collect_args=True, analyze_args=True)
    w = sub.add_parser("watch", help="live copy signals + paper trading for the watchlist")
    common(w)
    w.add_argument("--watchlist", default="out/watchlist.json")
    w.add_argument("--interval", type=int, default=30)
    w.set_defaults(out="out/live")

    a = p.parse_args(argv)
    {"collect": cmd_collect, "analyze": cmd_analyze, "run": cmd_run, "watch": cmd_watch}[a.cmd](a)


if __name__ == "__main__":
    main()
