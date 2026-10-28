"""Minimal AMap (Gaode) Web Service client using only the Python stdlib.

Docs: https://lbs.amap.com/api/webservice/summary
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

BASE = "https://restapi.amap.com"


class AmapError(RuntimeError):
    """Raised when AMap returns a non-OK status."""


class AmapClient:
    def __init__(self, key: str | None = None, timeout: float = 15.0) -> None:
        self.key = key or os.environ.get("AMAP_KEY", "")
        if not self.key:
            raise AmapError("AMAP_KEY is not set (put it in .env or the environment)")
        self.timeout = timeout

    # ------------------------------------------------------------------ utils
    def _fetch(self, url: str, retries: int = 3) -> dict:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001 - network hiccups are common
                last = exc
                if attempt + 1 < retries:
                    time.sleep(0.6 * (attempt + 1))
        raise AmapError(f"request failed after {retries} attempts: {last}")

    def _get(self, path: str, **params) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        params["key"] = self.key
        url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
        data = self._fetch(url)
        if str(data.get("status")) != "1":
            raise AmapError(f"{path} failed: {data.get('info')} (infocode={data.get('infocode')})")
        return data

    @staticmethod
    def parse_poi(poi: dict) -> dict:
        lon, lat = (poi.get("location") or ",").split(",")
        biz = poi.get("biz_ext") or {}
        cost = biz.get("cost")
        rating = biz.get("rating")
        return {
            "name": poi.get("name"),
            "address": poi.get("address"),
            "type": poi.get("type"),
            "tel": poi.get("tel"),
            "lng": float(lon) if lon else None,
            "lat": float(lat) if lat else None,
            "rating": float(rating) if rating not in (None, "", []) else None,
            "cost": float(cost) if cost not in (None, "", []) else None,
            "distance_m": int(poi["distance"]) if poi.get("distance") else None,
            "poi_id": poi.get("id"),
        }

    # ----------------------------------------------------------- geocoding
    def geocode(self, address: str, city: str | None = None) -> dict:
        data = self._get("/v3/geocode/geo", address=address, city=city)
        geocodes = data.get("geocodes") or []
        if not geocodes:
            raise AmapError(f"address not found: {address}")
        geo = geocodes[0]
        lon, lat = geo["location"].split(",")
        return {
            "input": address,
            "formatted": geo.get("formatted_address"),
            "lng": float(lon),
            "lat": float(lat),
            "adcode": geo.get("adcode"),
            "city": geo.get("city") or geo.get("province"),
        }

    def regeo(self, lng: float, lat: float, radius: int = 1000) -> dict:
        data = self._get(
            "/v3/geocode/regeo",
            location=f"{lng:.6f},{lat:.6f}",
            radius=radius,
            extensions="base",
        )
        regeo = data.get("regeocode") or {}
        comp = regeo.get("addressComponent") or {}
        return {
            "formatted": regeo.get("formatted_address"),
            "province": comp.get("province"),
            "city": comp.get("city") or comp.get("province"),
            "district": comp.get("district"),
            "adcode": comp.get("adcode"),
        }

    # ---------------------------------------------------------------- POI
    def around(
        self,
        lng: float,
        lat: float,
        keywords: str | None = None,
        types: str | None = None,
        radius: int = 3000,
        offset: int = 25,
        page: int = 1,
    ) -> list[dict]:
        data = self._get(
            "/v3/place/around",
            location=f"{lng:.6f},{lat:.6f}",
            keywords=keywords,
            types=types,
            radius=radius,
            offset=offset,
            page=page,
            extensions="all",
        )
        return [self.parse_poi(p) for p in (data.get("pois") or [])]

    def text_search(
        self,
        keywords: str,
        city: str | None = None,
        types: str | None = None,
        offset: int = 25,
        page: int = 1,
    ) -> list[dict]:
        data = self._get(
            "/v3/place/text",
            keywords=keywords,
            city=city,
            types=types,
            offset=offset,
            page=page,
            extensions="all",
        )
        return [self.parse_poi(p) for p in (data.get("pois") or [])]

    # -------------------------------------------------------------- routing
    def _route(self, kind: str, origin: str, destination: str, extra: dict) -> dict:
        data = self._get(
            f"/v3/direction/{kind}",
            origin=origin,
            destination=destination,
            extensions="base",
            **extra,
        )
        route = data.get("route") or {}
        paths = route.get("paths") or []
        if not paths:
            raise AmapError(f"no {kind} route found")
        path = paths[0]
        return {
            "mode": kind,
            "distance_m": int(path.get("distance") or 0),
            "duration_s": int(path.get("duration") or 0),
            "tolls": path.get("tolls"),
            "traffic_lights": path.get("traffic_lights"),
        }

    def driving(self, origin: str, destination: str, strategy: int = 0) -> dict:
        return self._route("driving", origin, destination, {"strategy": strategy})

    def walking(self, origin: str, destination: str) -> dict:
        return self._route("walking", origin, destination, {})

    def bicycling(self, origin: str, destination: str) -> dict:
        """骑行走 v4 接口（v3 下该服务不可用，返回 SERVICE_NOT_AVAILABLE）。"""
        params = urllib.parse.urlencode(
            {"origin": origin, "destination": destination, "key": self.key}
        )
        data = self._fetch(f"{BASE}/v4/direction/bicycling?{params}")
        if str(data.get("errcode")) != "0":
            raise AmapError(f"/v4/direction/bicycling failed: {data.get('errmsg')} (errcode={data.get('errcode')})")
        paths = (data.get("data") or {}).get("paths") or []
        if not paths:
            raise AmapError("no bicycling route found")
        return {
            "mode": "bicycling",
            "distance_m": int(paths[0].get("distance") or 0),
            "duration_s": int(paths[0].get("duration") or 0),
        }

    # ------------------------------------------------------------- misc
    def ip_location(self, ip: str) -> dict:
        data = self._get("/v3/ip", ip=ip)
        return {"province": data.get("province"), "city": data.get("city"), "adcode": data.get("adcode")}

    def distance(self, origins: str, destination: str, type_: int = 1) -> dict:
        data = self._get("/v3/distance", origins=origins, destination=destination, type=type_)
        results = data.get("results") or []
        if not results:
            raise AmapError("distance query failed")
        return {
            "distance_m": int(results[0].get("distance") or 0),
            "duration_s": int(results[0].get("duration") or 0),
        }
