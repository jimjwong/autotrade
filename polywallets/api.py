"""Thin client for Polymarket's public, unauthenticated data endpoints.

Only the standard library is used so the tool runs anywhere Python 3.10+ does.
All endpoints here are read-only; nothing in this module can place orders.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

DATA_API = "https://data-api.polymarket.com"

USER_AGENT = "polywallets/0.1 (+https://github.com/jimjwong/autotrade)"


class ApiError(RuntimeError):
    pass


class PolymarketClient:
    def __init__(self, timeout: float = 30.0, retries: int = 4, min_interval: float = 0.15):
        self.timeout = timeout
        self.retries = retries
        # Simple client-side rate limit so a full sweep doesn't trip 429s.
        self.min_interval = min_interval
        self._last_call = 0.0

    # -- transport ---------------------------------------------------------

    def _get(self, base: str, path: str, params: dict | None = None):
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{base}{path}" + (f"?{query}" if query else "")
        delay = 1.0
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                # 4xx other than 429 won't get better on retry.
                if e.code != 429 and 400 <= e.code < 500:
                    raise ApiError(f"GET {url} -> HTTP {e.code}") from e
                err = e
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                err = e
            if attempt < self.retries:
                time.sleep(delay)
                delay *= 2
        raise ApiError(f"GET {url} failed after {self.retries + 1} attempts: {err}")

    # -- leaderboard -------------------------------------------------------

    def leaderboard(self, time_period: str = "MONTH", order_by: str = "PNL",
                    category: str = "OVERALL", limit: int = 50, offset: int = 0) -> list[dict]:
        """time_period: DAY | WEEK | MONTH | ALL. order_by: PNL | VOL."""
        data = self._get(DATA_API, "/v1/leaderboard", {
            "timePeriod": time_period, "orderBy": order_by, "category": category,
            "limit": limit, "offset": offset,
        })
        return data if isinstance(data, list) else data.get("data", [])

    # -- per-wallet --------------------------------------------------------

    def activity_since(self, user: str, start_ts: int, end_ts: int | None = None,
                       page_size: int = 500, max_rows: int = 50_000) -> list[dict]:
        """All on-chain activity (TRADE, REDEEM, SPLIT, MERGE, ...) in [start_ts, end_ts].

        Pages backwards by moving the `end` cursor rather than using a large
        offset, because the API caps offsets.
        """
        rows: list[dict] = []
        seen: set[tuple] = set()
        end = end_ts or int(time.time())
        while len(rows) < max_rows:
            page = self._get(DATA_API, "/activity", {
                "user": user, "start": start_ts, "end": end, "limit": page_size,
                "sortBy": "TIMESTAMP", "sortDirection": "DESC",
            })
            if not page:
                break
            new = 0
            for r in page:
                key = (r.get("transactionHash"), r.get("asset"), r.get("type"), r.get("side"),
                       r.get("size"), r.get("timestamp"))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(r)
                new += 1
            oldest = min(int(r.get("timestamp", end)) for r in page)
            if len(page) < page_size or new == 0:
                break
            # Re-include the boundary second; duplicates are dropped above.
            end = oldest if oldest < end else end - 1
        return rows

    def positions(self, user: str, page_size: int = 500, max_rows: int = 5_000) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while len(rows) < max_rows:
            page = self._get(DATA_API, "/positions", {
                "user": user, "limit": page_size, "offset": offset, "sizeThreshold": 0,
            })
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def closed_positions(self, user: str, since_ts: int, page_size: int = 50,
                         max_rows: int = 10_000) -> list[dict]:
        """Resolved/closed positions, newest first, stopping once older than since_ts."""
        rows: list[dict] = []
        offset = 0
        while len(rows) < max_rows:
            page = self._get(DATA_API, "/closed-positions", {
                "user": user, "limit": page_size, "offset": offset,
                "sortBy": "TIMESTAMP", "sortDirection": "DESC",
            })
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size or min(int(p.get("timestamp", 0)) for p in page) < since_ts:
                break
            offset += page_size
        return rows

    def portfolio_value(self, user: str) -> float | None:
        data = self._get(DATA_API, "/value", {"user": user})
        if isinstance(data, list) and data:
            return float(data[0].get("value") or 0)
        return None
