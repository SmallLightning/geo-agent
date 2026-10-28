"""Unit tests for the deterministic parts (no network, no API keys).

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.intent import parse_rules  # noqa: E402
from src.planner import filter_candidates, haversine_m, pick_mode, rank_candidates, select  # noqa: E402


class TestIntentParsing(unittest.TestCase):
    def test_full_sentence(self):
        i = parse_rules("从杭州东站出发，找家人均100以内、评分4.5以上、走路能到的餐厅，要前3家")
        self.assertEqual(i.origin, "杭州东站")
        self.assertEqual(i.city, "杭州")
        self.assertEqual(i.budget, 100.0)
        self.assertEqual(i.min_rating, 4.5)
        self.assertEqual(i.top, 3)
        self.assertEqual(i.travel_mode, "walking")
        self.assertEqual(i.keyword, "餐厅")

    def test_landmark_city_disambiguation(self):
        i = parse_rules("西湖附近人均60以下的咖啡店")
        self.assertEqual(i.origin, "西湖")
        self.assertEqual(i.city, "杭州", "西湖必须落在杭州，不能解析到台湾苗栗县西湖乡")
        self.assertEqual(i.keyword, "咖啡")
        self.assertEqual(i.types, "050500")
        self.assertEqual(i.budget, 60.0)

    def test_radius_units(self):
        self.assertEqual(parse_rules("人民广场附近2公里内的火锅").radius_m, 2000)
        self.assertEqual(parse_rules("附近800米的超市").radius_m, 800)
        self.assertEqual(parse_rules("步行10分钟能到的咖啡").radius_m, 800)

    def test_top_and_rating_variants(self):
        self.assertEqual(parse_rules("评分4.8以上的日料，前5家").top, 5)
        self.assertEqual(parse_rules("评分4.8以上的日料，前5家").min_rating, 4.8)

    def test_missing_origin_is_reported(self):
        i = parse_rules("想找个便宜点的火锅")
        self.assertIsNone(i.origin)
        self.assertTrue(i.notes)


class TestPlanner(unittest.TestCase):
    def poi(self, name, rating, cost, lng, lat):
        return {"name": name, "rating": rating, "cost": cost, "lng": lng, "lat": lat}

    def test_pick_mode_thresholds(self):
        self.assertEqual(pick_mode(999), "walking")
        self.assertEqual(pick_mode(1000), "bicycling")
        self.assertEqual(pick_mode(2999), "bicycling")
        self.assertEqual(pick_mode(3000), "driving")
        self.assertEqual(pick_mode(100, travel_mode="driving"), "driving", "显式偏好优先")
        self.assertEqual(pick_mode(5000, travel_mode="walking"), "walking")

    def test_filter_by_budget_and_rating(self):
        pois = [
            self.poi("贵", 4.9, 300, 120.2, 30.2),
            self.poi("低分", 3.1, 50, 120.2, 30.2),
            self.poi("合适", 4.6, 80, 120.2, 30.2),
            self.poi("价格未知", 4.7, None, 120.2, 30.2),
        ]
        kept = filter_candidates(pois, budget=100, min_rating=4.5)
        self.assertEqual([p["name"] for p in kept], ["合适", "价格未知"])

    def test_rank_rating_then_distance(self):
        pois = [
            self.poi("远高分", 4.8, 50, 120.30, 30.30),
            self.poi("近低分", 4.2, 50, 120.201, 30.201),
            self.poi("中", 4.5, 50, 120.25, 30.25),
        ]
        kept = select(pois, (120.2, 30.2), top=3)
        self.assertEqual([p["name"] for p in kept], ["远高分", "中", "近低分"])

    def test_select_respects_top(self):
        pois = [self.poi(f"p{i}", 4.0 + i / 10, 50, 120.2 + i / 1000, 30.2) for i in range(10)]
        self.assertEqual(len(select(pois, (120.2, 30.2), top=3)), 3)

    def test_haversine_reasonable(self):
        # 杭州东站 -> 西湖，直线约 9~10 km
        d = haversine_m((120.2126, 30.2909), (120.1500, 30.2500))
        self.assertTrue(7000 < d < 11000, d)

    def test_missing_coordinates_are_dropped(self):
        pois = [{"name": "无坐标", "rating": 4.9, "cost": 10, "lng": None, "lat": None}]
        self.assertEqual(select(pois, (120.2, 30.2)), [])


if __name__ == "__main__":
    unittest.main()
