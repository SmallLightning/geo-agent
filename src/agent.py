"""Natural-language entry point: 一句话 -> 结构化参数 -> POI 检索 -> 行程建议.

    python3 src/agent.py "从杭州东站出发，找家人均100以内、评分4.5以上、走路能到的餐厅，要前3家"
    python3 src/agent.py "西湖附近人均60以下的咖啡店" --json

有 LLM Key 时用模型解析意图并润色回答；没有 Key 时自动退回正则解析 + 模板回答（仍可完整跑通）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.amap_client import AmapClient, AmapError  # noqa: E402
from src.demo import load_env, recommend  # noqa: E402
from src.intent import Intent, parse_llm, parse_rules  # noqa: E402
from src.llm import LLMClient, LLMError  # noqa: E402
from src import offline as offline_mode  # noqa: E402

ANSWER_SYSTEM = """你是贴心的出行助手。根据给定的候选地点与路线数据，用中文写一段 3~5 行的推荐。

要求：
- 直接给结论，按推荐顺序点名，带上评分、人均、步行/骑行/驾车时间
- 不要编造数据里没有的信息（不要编营业时间、电话、停车场）
- 不要用 markdown 表格，不要分点符号，用自然的口语
- 最后一句给一个取舍建议（比如哪家性价比高、哪家近）
"""


def compose_template(intent: Intent, result: dict) -> str:
    o = result["origin"]
    f = result["filters"]
    recs = result["recommendations"]
    if not recs:
        return (
            f"在 {o['formatted']} 附近 {f['radius_m']} 米内没找到符合条件（关键词={f['keyword']}、"
            f"人均≤{f['budget'] or '不限'}、评分≥{f['min_rating'] or '不限'}）的地点，"
            "可以试试放宽预算或扩大范围。"
        )

    cond = []
    if f["budget"]:
        cond.append(f"人均{f['budget']:.0f}元以内")
    if f["min_rating"]:
        cond.append(f"评分{f['min_rating']}以上")
    cond_txt = "、".join(cond) or "不限预算"

    lines = [f"从 {o['formatted']} 出发，{f['radius_m']} 米内按{cond_txt}帮你挑了 {len(recs)} 家："]
    for i, p in enumerate(recs, 1):
        rating = f"{p['rating']:.1f}分" if p.get("rating") is not None else "暂无评分"
        cost = f"人均{p['cost']:.0f}元" if p.get("cost") is not None else "价格未知"
        route = p.get("route") or {}
        label = {"walking": "步行", "bicycling": "骑行", "driving": "驾车"}.get(route.get("mode"), "路程")
        if route.get("error"):
            route_txt = "路线规划失败"
        else:
            route_txt = "{}（{:.1f}km，约{:.0f}分钟）".format(
                label, route.get("distance_m", 0) / 1000, route.get("duration_s", 0) / 60
            )
        lines.append(f"{i}. {p['name']}｜{rating}｜{cost}｜{route_txt}")
        if p.get("address"):
            lines.append(f"   地址：{p['address']}")
    if result.get("offline_fixture"):
        lines.append(f"（离线演示：数据来自录制快照 {result['offline_fixture']}，非实时）")
    else:
        lines.append("以上地点均来自高德地图实时 POI 数据，营业状态请出发前再确认。")
    return "\n".join(lines)


def compose_llm(llm: LLMClient, text: str, intent: Intent, result: dict) -> str:
    payload = {
        "user_request": text,
        "parsed_intent": intent.to_dict(),
        "origin": result["origin"],
        "filters": result["filters"],
        "candidates": [
            {
                "name": p["name"],
                "address": p.get("address"),
                "rating": p.get("rating"),
                "cost": p.get("cost"),
                "straight_m": p.get("straight_m"),
                "route": p.get("route"),
            }
            for p in result["recommendations"]
        ],
    }
    return llm.chat(
        [
            {"role": "system", "content": ANSWER_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.4,
        max_tokens=500,
    )


def run(text: str, use_llm: bool = True, offline: bool = False) -> dict:
    load_env(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    llm = LLMClient() if use_llm else None

    intent = parse_llm(llm, text) if (llm and llm.configured) else parse_rules(text)
    if not intent.origin:
        return {"ok": False, "error": "没能识别出起点", "intent": intent.to_dict(), "notes": intent.notes}

    used_offline = offline
    if offline:
        result = offline_mode.build_result(intent)
    else:
        try:
            result = recommend(
                AmapClient(),
                origin=intent.origin,
                city=intent.city,
                budget=intent.budget,
                keyword=intent.keyword,
                types=intent.types,
                radius=intent.radius_m,
                top=intent.top,
                min_rating=intent.min_rating,
                travel_mode=intent.travel_mode,
            )
        except AmapError as exc:
            # 没有 Key / 没有网络时自动降级到快照，保证任何机器上都能跑通
            intent.notes.append(f"实时检索不可用，已切换离线快照：{exc}")
            result = offline_mode.build_result(intent)
            used_offline = True

    answer = None
    if llm and llm.configured:
        try:
            answer = compose_llm(llm, text, intent, result)
        except LLMError as exc:
            intent.notes.append(f"LLM 生成回答失败，退回模板：{exc}")
    if not answer:
        answer = compose_template(intent, result)

    return {
        "ok": True,
        "request": text,
        "intent": intent.to_dict(),
        "llm_used": bool(llm and llm.configured),
        "offline": used_offline,
        "answer": answer,
        "result": result,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="一句话出行规划")
    ap.add_argument("text", help="自然语言请求")
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    ap.add_argument("--no-llm", action="store_true", help="强制只用规则解析")
    ap.add_argument("--offline", action="store_true", help="只用离线快照，不访问高德接口")
    args = ap.parse_args()

    out = run(args.text, use_llm=not args.no_llm, offline=args.offline)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif not out.get("ok"):
        print("解析失败：", out.get("error"))
        for note in out.get("notes", []):
            print(" -", note)
    else:
        print(out["answer"])
        print()
        print(f"[intent/{out['intent']['source']}] origin={out['intent']['origin']} "
              f"city={out['intent']['city']} keyword={out['intent']['keyword']} "
              f"budget={out['intent']['budget']} radius={out['intent']['radius_m']} "
              f"top={out['intent']['top']} min_rating={out['intent']['min_rating']} "
              f"mode={out['intent']['travel_mode']} llm={out['llm_used']} offline={out['offline']}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
