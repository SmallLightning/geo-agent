"""End-to-end demo: 起点 + 预算 -> 附近餐厅推荐 -> 驾车路线规划.

纯规则版（不依赖 LLM），保证在任何机器上都能跑通；
后续 LLM/Agent 编排层可以直接把 recommend() 的返回当作工具结果。

Usage:
    python -m src.demo --from "杭州东站" --budget 100 --radius 3000 --top 3
    python -m src.demo --from "杭州东站" --keyword "咖啡" --budget 60 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.amap_client import AmapClient  # noqa: E402


def load_env(path: str = ".env") -> None:
    """Very small .env loader (no external dependency)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt

    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(h))


def recommend(
    client: AmapClient,
    origin: str,
    city: str | None = None,
    budget: float | None = None,
    keyword: str = "餐厅",
    types: str = "050000",
    radius: int = 3000,
    top: int = 3,
    max_candidates: int = 60,
) -> dict:
    start = client.geocode(origin, city=city)
    pois: list[dict] = []
    for page in (1, 2, 3):
        batch = client.around(
            start["lng"], start["lat"], keywords=keyword, types=types, radius=radius, page=page
        )
        pois.extend(batch)
        if len(pois) >= max_candidates or len(batch) < 25:
            break

    candidates = []
    for poi in pois:
        if poi["lng"] is None or poi["lat"] is None:
            continue
        if budget is not None and poi["cost"] is not None and poi["cost"] > budget:
            continue
        poi["straight_m"] = round(haversine_m((start["lng"], start["lat"]), (poi["lng"], poi["lat"])))
        candidates.append(poi)

    def score(p: dict) -> tuple[float, float]:
        rating = p.get("rating") or 0.0
        dist = p.get("distance_m") or p.get("straight_m") or 99999
        return (-rating, dist)

    candidates.sort(key=score)
    picked = candidates[:top]

    for p in picked:
        # 短距离步行/骑行更贴近真实出行，长距离才用驾车
        dist = p.get("straight_m") or 0
        if dist < 1000:
            mode, fn = "walking", client.walking
        elif dist < 3000:
            mode, fn = "bicycling", client.bicycling
        else:
            mode, fn = "driving", client.driving
        try:
            route = fn(f"{start['lng']:.6f},{start['lat']:.6f}", f"{p['lng']:.6f},{p['lat']:.6f}")
            route["mode"] = mode
            p["route"] = route
        except Exception as exc:  # noqa: BLE001 - demo: keep going
            # 骑行服务不可用时退回步行
            try:
                route = client.walking(
                    f"{start['lng']:.6f},{start['lat']:.6f}", f"{p['lng']:.6f},{p['lat']:.6f}"
                )
                route["mode"] = "walking"
                route["fallback_from"] = mode
                p["route"] = route
            except Exception:  # noqa: BLE001
                p["route"] = {"error": str(exc), "mode": mode}

    return {
        "origin": start,
        "filters": {"keyword": keyword, "budget": budget, "radius_m": radius, "top": top},
        "total_candidates": len(pois),
        "filtered_candidates": len(candidates),
        "recommendations": picked,
    }


def render(result: dict) -> str:
    o = result["origin"]
    f = result["filters"]
    lines = [
        f"起点: {o['formatted']}  ({o['lng']:.6f},{o['lat']:.6f})",
        f"条件: 关键词={f['keyword']} 预算={f['budget'] or '不限'} 半径={f['radius_m']}m",
        f"候选: 抓取 {result['total_candidates']} 家, 过滤后 {result['filtered_candidates']} 家",
        "-" * 78,
    ]
    for i, p in enumerate(result["recommendations"], 1):
        rating = "无评分" if p.get("rating") is None else f"{p['rating']:.1f}分"
        cost = "价格未知" if p.get("cost") is None else f"人均{p['cost']:.0f}元"
        dist = p.get("distance_m") or p.get("straight_m") or 0
        lines.append(f"{i}. {p['name']}  [{rating} | {cost} | 直线{dist}m]")
        lines.append(f"   地址: {p.get('address') or '-'}")
        route = p.get("route") or {}
        label = {"walking": "步行", "bicycling": "骑行", "driving": "驾车"}.get(route.get("mode"), "路线")
        if route.get("error"):
            lines.append(f"   {label}: 规划失败 ({route['error']})")
        else:
            lines.append(
                "   {}: {:.1f} km, 约 {:.0f} 分钟".format(
                    label, route.get("distance_m", 0) / 1000.0, route.get("duration_s", 0) / 60.0
                )
            )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="AMap POI + routing demo")
    ap.add_argument("--from", dest="origin", required=True, help="起点地址，如 杭州东站")
    ap.add_argument("--city", default=None, help="城市名，用于消歧（如 杭州）")
    ap.add_argument("--keyword", default="餐厅")
    ap.add_argument("--types", default="050000", help="高德 POI 类型码，050000=餐饮服务")
    ap.add_argument("--budget", type=float, default=None, help="人均预算上限（元）")
    ap.add_argument("--radius", type=int, default=3000)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--json", action="store_true", help="输出 JSON（给 Agent/Dify 用）")
    args = ap.parse_args()

    load_env(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    client = AmapClient()
    result = recommend(
        client,
        origin=args.origin,
        city=args.city,
        budget=args.budget,
        keyword=args.keyword,
        types=args.types,
        radius=args.radius,
        top=args.top,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
