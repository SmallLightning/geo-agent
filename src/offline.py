"""Offline mode: replay a recorded AMap snapshot when there is no key / no network.

Fixtures are produced by `python3 scripts/record_fixtures.py` and contain the full
result of a real `recommend()` call, so the demo has realistic data with zero network.
"""

from __future__ import annotations

import json
import os

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def list_fixtures() -> list[str]:
    if not os.path.isdir(FIXTURE_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(FIXTURE_DIR) if f.endswith(".json"))


def load(name: str) -> dict:
    path = os.path.join(FIXTURE_DIR, f"{name}.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def match(keyword: str) -> str | None:
    """Pick the fixture whose keyword matches best (餐厅 / 咖啡 / ...)."""
    names = list_fixtures()
    if not names:
        return None
    for name in names:
        try:
            data = load(name)
        except (OSError, json.JSONDecodeError):
            continue
        if keyword and data.get("filters", {}).get("keyword") == keyword:
            return name
    return names[0]


def build_result(intent) -> dict:
    """Rebuild a result dict from a fixture, re-applying the user's filters."""
    from src.planner import filter_candidates, rank_candidates

    name = match(intent.keyword)
    if name is None:
        raise FileNotFoundError(f"no fixtures in {FIXTURE_DIR}")

    fx = load(name)
    recs = fx.get("recommendations", [])
    recs = filter_candidates(recs, budget=intent.budget, min_rating=intent.min_rating)
    recs = rank_candidates(recs)[: max(0, intent.top)]

    return {
        "origin": fx["origin"],
        "filters": {
            "keyword": intent.keyword,
            "budget": intent.budget,
            "radius_m": intent.radius_m,
            "top": intent.top,
            "min_rating": intent.min_rating,
            "travel_mode": intent.travel_mode or "auto",
        },
        "total_candidates": fx.get("total_candidates", len(fx.get("recommendations", []))),
        "filtered_candidates": len(recs),
        "recommendations": recs,
        "offline_fixture": name,
    }
