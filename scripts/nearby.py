"""Skill entry point: one sentence in, places + how to get there out.

    python3 scripts/nearby.py --query "从杭州东站出发，人均100以内、走路能到的餐厅"
    python3 scripts/nearby.py --query "..." --json

This is the command a host agent calls (see SKILL.md). It is intentionally thin:
all logic lives in src/agent.py so the CLI, the web UI and the skill share one path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.agent import run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="周边去哪儿：一句话找地点 + 路线")
    ap.add_argument("--query", "-q", required=True, help="一句话需求，如：从杭州东站出发，人均100以内的餐厅")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--offline", action="store_true", help="只用内置快照，不联网")
    ap.add_argument("--no-llm", action="store_true", help="只用规则解析")
    args = ap.parse_args()

    out = run(args.query, use_llm=not args.no_llm, offline=args.offline)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif out.get("ok"):
        print(out["answer"])
        print()
        notes = out.get("intent", {}).get("notes") or []
        if notes:
            print("提示：" + "；".join(notes))
    else:
        print(f"没能完成：{out.get('error')}")
        for note in out.get("notes", []) or []:
            print(" -", note)

    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
