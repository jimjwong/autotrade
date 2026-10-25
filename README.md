# autotrade

`polywallets`: find the Polymarket wallets worth following, show why, and paper-trade them live.

It pulls every wallet on Polymarket's top leaderboards, downloads 90 days of trades and positions for each one, and scores them on a narrow question: **does this wallet have an edge that you could still capture if you copied its trades a little late?** Raw PnL doesn't answer that. It rewards one lucky election bet, and it rewards market makers whose profit comes from the spread itself. Neither of those can be copied.

Pure Python 3.10+, standard library only. Read-only: nothing here can place an order.

## Quick start

```bash
python -m polywallets run              # collect + analyze (default: 90 days, ~200 wallets per board)
open out/report.html                   # interactive report
python -m polywallets watch            # live copy signals + paper portfolio for the top 10
```

A full sweep makes a few thousand API calls and is resumable. If it gets interrupted, re-run `collect` and it picks up where it stopped. Use `--max-wallets 50` for a quick pass.

| Command | What it does |
|---|---|
| `collect` | Seeds wallets from the MONTH/PNL, MONTH/VOL, WEEK/PNL and ALL/PNL leaderboards, then saves `data/raw/<wallet>.json` (activity, open positions, closed positions, portfolio value) |
| `analyze` | Computes metrics and scores, runs the copy backtests, and writes `out/report.html`, `leaderboard.csv`, `analysis.json` and `watchlist.json` |
| `run` | `collect` then `analyze` |
| `watch` | Polls the watchlist wallets, logs qualifying trades to `out/live/signals.jsonl`, and mirrors them into a paper book in `out/live/paper.json` |

Common flags: `--days 90`, `--stake 100` (paper $ per copied buy), `--slippage 0.02` (fill 2¢ worse than the leader), `--min-leader-usd 50` (ignore the leader's dust trades), `--max-entry 0.97` (don't copy buys above 97¢), `--top-n 10`, `--test-days 30`.

## What gets measured

**Results** (closed positions within the window): realized PnL, plus resolved-but-unredeemed PnL, ROI on cost, win rate, profit factor, daily Sharpe (days with no closes count as zero), max drawdown, share of profitable weeks, and the share of gross profit that came from the single best market.

**Behaviour** (raw trades): volume, trade size distribution, trades per active day, median gap between trades, volume-weighted entry price, share of buy volume at ≤15¢ (longshots), 70–93¢ (favorites) and ≥93¢ (resolution sweeping), how much they sell before resolution, how often they buy both sides of a market, category mix, and median hold time.

**Archetypes**: Market maker / bot, Resolution sweeper, Longshot hunter, Favorite grinder, Whale conviction, Swing trader, *Category* specialist, One-hit, Generalist.

**Copy score** (0–100): 50% profit (percentile of PnL and ROI) plus 50% consistency (Sharpe, profitable weeks, profit factor), multiplied by penalties that are listed on every wallet:

| Penalty | Why |
|---|---|
| small sample (<30 closed) | Not enough evidence |
| concentrated in one market | One-hit wonder |
| too fast to follow | Bots and market makers: the edge is in the latency or the spread |
| thin-edge sweeping | Buying at 95¢+ leaves less edge than slippage takes |
| moves the book | Median trade over $25k, so you can't get their price |
| inactive 3+ weeks | Gone cold |
| not profitable in window | Self-explanatory |

## Is the score any good? (walk-forward)

`analyze` also runs an out-of-sample check. It ranks wallets on the first 60 days only, then simulates copying the top N over the last 30 days, which the ranking never saw. It compares three strategies: top N by copy score, top N by raw PnL, and copying everyone. If the score isn't beating raw PnL on your data, don't trust it. The per-wallet "If you'd copied them" figure in the report is in-sample, so treat it as illustrative only.

How the simulation works: it puts a fixed stake on each qualifying BUY at the leader's price plus slippage. When the leader sells, it sells the same fraction of the copied position. Whatever is left is marked at the resolved price, or at the current price for live markets.

## Caveats

- Polymarket's leaderboard has no 90-day window, so the candidate pool comes from the boards above and all metrics are recomputed over the 90 days. A wallet that was only great 60–90 days ago and never appeared on any current board will be missed.
- Categories come from keyword matching on market titles, not from Polymarket's own tags.
- Positions opened before the window but closed inside it count toward that window's results.
- This is research tooling, not financial advice.

## Tests

```bash
python -m unittest discover -s tests
```

The tests use synthetic data and a fake API client, so they need no network access.
