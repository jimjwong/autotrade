"""Load a collected data directory and produce the scored cohort."""

from __future__ import annotations

import json
from pathlib import Path

from .metrics import analyze_wallet
from .score import score_cohort


def load(data_dir: Path) -> tuple[dict, list[dict], dict[str, dict]]:
    index = json.loads((data_dir / "wallets.json").read_text())
    metas = {w["wallet"]: w for w in index["wallets"]}
    snaps = []
    for path in sorted((data_dir / "raw").glob("*.json")):
        snap = json.loads(path.read_text())
        if snap["wallet"] in metas:
            snaps.append(snap)
    return index, snaps, metas


def analyze(snaps: list[dict], metas: dict[str, dict]) -> list[dict]:
    return score_cohort([analyze_wallet(s, metas.get(s["wallet"])) for s in snaps])


def cohort_summary(rows: list[dict]) -> dict:
    from collections import Counter

    tags = Counter(t for r in rows for t in r["tags"])
    cats = Counter(r["top_category"] for r in rows)
    profitable = [r for r in rows if r["realized_pnl"] + r["pending_realized_pnl"] > 0]
    pnl_by_tag: dict[str, float] = {}
    for r in rows:
        for t in r["tags"]:
            pnl_by_tag[t] = pnl_by_tag.get(t, 0.0) + r["realized_pnl"] + r["pending_realized_pnl"]
    return {
        "wallets": len(rows),
        "profitable": len(profitable),
        "total_realized": sum(r["realized_pnl"] + r["pending_realized_pnl"] for r in rows),
        "total_volume": sum(r["volume"] for r in rows),
        "median_win_rate": sorted(r["win_rate"] for r in rows)[len(rows) // 2] if rows else 0,
        "tags": dict(tags.most_common()),
        "pnl_by_tag": dict(sorted(pnl_by_tag.items(), key=lambda kv: -kv[1])),
        "top_categories": dict(cats.most_common()),
        "one_hit_share": tags.get("One-hit", 0) / len(rows) if rows else 0,
    }
