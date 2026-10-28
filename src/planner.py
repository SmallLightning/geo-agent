"""Pure planning helpers: distance, filtering, ranking, travel-mode choice.

Kept free of network calls so they can be unit tested deterministically.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

WALK_LIMIT_M = 1000
BIKE_LIMIT_M = 3000


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Straight-line distance in metres between two (lng, lat) points."""
    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(h))


def pick_mode(straight_m: float | None, travel_mode: str | None = None) -> str:
    """Explicit preference wins; otherwise infer from distance."""
    if travel_mode in {"walking", "bicycling", "driving"}:
        return travel_mode
    dist = straight_m or 0
    if dist < WALK_LIMIT_M:
        return "walking"
    if dist < BIKE_LIMIT_M:
        return "bicycling"
    return "driving"


def annotate_distance(pois: list[dict], origin: tuple[float, float]) -> list[dict]:
    """Attach straight_m to every POI that has coordinates."""
    out = []
    for poi in pois:
        if poi.get("lng") is None or poi.get("lat") is None:
            continue
        poi = dict(poi)
        poi["straight_m"] = round(haversine_m(origin, (poi["lng"], poi["lat"])))
        out.append(poi)
    return out


def filter_candidates(
    pois: list[dict],
    budget: float | None = None,
    min_rating: float | None = None,
) -> list[dict]:
    """Drop POIs over budget / under rating. Missing values are treated as unknown, not excluded."""
    out = []
    for poi in pois:
        cost = poi.get("cost")
        rating = poi.get("rating")
        if budget is not None and cost is not None and cost > budget:
            continue
        if min_rating is not None and rating is not None and rating < min_rating:
            continue
        out.append(poi)
    return out


def rank_candidates(pois: list[dict]) -> list[dict]:
    """Higher rating first, then closer first. Unknown rating/price sinks to the bottom."""

    def key(p: dict) -> tuple:
        rating = p.get("rating")
        dist = p.get("distance_m") or p.get("straight_m") or 99999
        return (-(rating if rating is not None else -1), dist)

    return sorted(pois, key=key)


def select(
    pois: list[dict],
    origin: tuple[float, float],
    budget: float | None = None,
    min_rating: float | None = None,
    top: int = 3,
) -> list[dict]:
    """Annotate -> filter -> rank -> take top N."""
    annotated = annotate_distance(pois, origin)
    filtered = filter_candidates(annotated, budget=budget, min_rating=min_rating)
    return rank_candidates(filtered)[: max(0, top)]
