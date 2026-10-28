"""Small offline evaluation of the rule-based intent parser.

Not a competition deliverable by itself, but it gives an honest accuracy number for
the submission doc, and guards against regressions.

    python3 scripts/eval_intent.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.intent import parse_rules  # noqa: E402

# (utterance, {field: expected})
CASES = [
    ("从杭州东站出发，找家人均100以内、评分4.5以上、走路能到的餐厅，要前3家",
     dict(origin="杭州东站", city="杭州", budget=100.0, min_rating=4.5, top=3, travel_mode="walking", keyword="餐厅")),
    ("西湖附近人均60以下的咖啡店",
     dict(origin="西湖", city="杭州", budget=60.0, keyword="咖啡", types="050500")),
    ("上海人民广场附近2公里内评分4.8以上的火锅，前5家",
     dict(origin="上海人民广场", city="上海", radius_m=2000, min_rating=4.8, top=5, keyword="火锅")),
    ("从公司出发，找个人均50以内能吃饭的地方",
     dict(origin="公司", budget=50.0, keyword="餐厅")),
    ("北京三里屯附近步行10分钟的酒吧",
     dict(origin="北京三里屯", city="北京", radius_m=800, keyword="酒吧")),
    ("深圳湾附近3公里的停车场",
     dict(origin="深圳湾", city="深圳", radius_m=3000, keyword="停车场")),
    ("成都春熙路周边评分4.6以上的甜品店，要2家",
     dict(origin="成都春熙路", city="成都", min_rating=4.6, top=2, keyword="甜品")),
    ("从南京鼓楼出发，5公里内人均200以内的火锅",
     dict(origin="南京鼓楼", city="南京", budget=200.0, radius_m=5000, keyword="火锅")),
    ("广州塔附近人均80以内的日料",
     dict(origin="广州塔", city="广州", budget=80.0, keyword="日料")),
    ("武汉光谷附近1.5公里的川菜，评分4.2以上",
     dict(origin="武汉光谷", city="武汉", radius_m=1500, min_rating=4.2, keyword="川菜")),
]

FIELDS = ["origin", "city", "keyword", "types", "budget", "radius_m", "top", "min_rating", "travel_mode"]


def main() -> int:
    passed = 0
    total_checks = 0
    failed: list[str] = []

    for text, expected in CASES:
        intent = parse_rules(text)
        checks = 0
        for field, want in expected.items():
            total_checks += 1
            checks += 1
            got = getattr(intent, field)
            if got != want:
                failed.append(f"{field}: got={got!r} want={want!r}  <<{text}>>")
                checks -= 1
        if checks == len(expected):
            passed += 1

    print(f"cases: {passed}/{len(CASES)} fully correct")
    print(f"fields: {total_checks - len(failed)}/{total_checks} correct")
    if failed:
        print("\nfailures:")
        for f in failed:
            print("  -", f)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
