"""Record real AMap responses into fixtures/ so offline mode has realistic data.

Requires a working AMAP_KEY in .env. Run once whenever the fixtures need refreshing:

    python3 scripts/record_fixtures.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.amap_client import AmapClient  # noqa: E402
from src.demo import load_env, recommend  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")

SCENARIOS = [
    ("hangzhou_east_station", dict(origin="杭州东站", city="杭州", keyword="餐厅", types="050000", radius=3000)),
    ("hangzhou_west_lake_coffee", dict(origin="西湖", city="杭州", keyword="咖啡", types="050500", radius=3000)),
]


def main() -> int:
    load_env(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    client = AmapClient()
    for name, kwargs in SCENARIOS:
        print(f"recording {name} ...", flush=True)
        result = recommend(client, top=10, **kwargs)
        path = os.path.join(FIXTURE_DIR, f"{name}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"  -> {path} ({len(result['recommendations'])} places)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
