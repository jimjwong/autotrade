"""Keyword market categorizer.

The data API doesn't return a category per trade, and looking every market up
in Gamma would add thousands of calls to a sweep, so we classify from the
market title and event slug. First matching rule wins.
"""

from __future__ import annotations

import re

_RULES: list[tuple[str, re.Pattern]] = [
    ("Crypto", re.compile(
        r"\b(bitcoin|btc|ethereum|eth|solana|sol|xrp|doge|dogecoin|crypto|bnb|hyperliquid|"
        r"memecoin|stablecoin|up or down|updown|microstrategy|coinbase|binance|airdrop|fdv)\b", re.I)),
    ("Sports", re.compile(
        r"\b(nfl|nba|mlb|nhl|wnba|ncaa|cfb|cbb|ufc|mma|epl|premier league|la liga|serie a|bundesliga|"
        r"ligue 1|champions league|uefa|fifa|world cup|mls|atp|wta|tennis|golf|pga|f1|formula 1|nascar|"
        r"super bowl|stanley cup|world series|playoffs?|grand slam|wimbledon|boxing|cricket|ipl|"
        r"spread|o/u|over/under|moneyline|vs\.?|fc|esports|lol|cs2|dota|valorant)\b", re.I)),
    ("Economics", re.compile(
        r"\b(fed|fomc|interest rates?|rate (cut|hike)|bps|cpi|inflation|gdp|recession|unemployment|"
        r"jobs report|nonfarm|payrolls|tariffs?|treasury|yields?|s&p|nasdaq|dow|stock|ipo|earnings)\b", re.I)),
    ("Politics", re.compile(
        r"\b(election|elected|president|presidential|senate|house|congress|governor|mayor|primary|"
        r"nominee|nomination|democrat|republican|gop|dnc|rnc|trump|biden|harris|vance|newsom|"
        r"parliament|prime minister|chancellor|cabinet|impeach|supreme court|scotus|poll|vote|"
        r"electoral|referendum|party)\b", re.I)),
    ("Geopolitics", re.compile(
        r"\b(war|ceasefire|invade|invasion|military|strike|missile|nato|ukraine|russia|putin|zelensky|"
        r"israel|gaza|hamas|hezbollah|iran|china|taiwan|north korea|sanctions|treaty|peace deal)\b", re.I)),
    ("Tech & AI", re.compile(
        r"\b(ai|openai|chatgpt|gpt|anthropic|claude|gemini|google|apple|nvidia|tesla|spacex|"
        r"starship|elon|musk|tweets?|x\.com|meta|microsoft|launch|app store)\b", re.I)),
    ("Culture", re.compile(
        r"\b(oscars?|grammys?|emmys?|golden globes?|box office|movie|album|song|spotify|billboard|"
        r"taylor swift|celebrity|tv|netflix|youtube|mrbeast|time person of the year|pope|eurovision)\b", re.I)),
    ("Weather & Science", re.compile(
        r"\b(temperature|weather|hurricane|earthquake|rain|snow|climate|nasa|highest temp|degrees)\b", re.I)),
]

CATEGORIES = [name for name, _ in _RULES] + ["Other"]


def categorize(title: str | None, event_slug: str | None = None) -> str:
    text = f"{title or ''} {(event_slug or '').replace('-', ' ')}"
    for name, pattern in _RULES:
        if pattern.search(text):
            return name
    return "Other"
