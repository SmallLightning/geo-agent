"""Probe which MiniMax base_url / model combination works with the given key.

Usage:  MINIMAX_API_KEY=... python3 scripts/probe_minimax.py
        MINIMAX_API_KEY=... MINIMAX_GROUP_ID=... python3 scripts/probe_minimax.py
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

KEY = os.environ.get("MINIMAX_API_KEY", "")
GROUP = os.environ.get("MINIMAX_GROUP_ID", "")

BASES = [
    "https://api.minimaxi.com/v1",
    "https://api.minimax.chat/v1",
    "https://api.minimax.cn/v1",
]
MODELS = ["MiniMax-M3.1-Flash", "MiniMax-M3", "MiniMax-Text-01", "abab6.5s-chat"]

if not KEY:
    raise SystemExit("set MINIMAX_API_KEY first")


def probe(base: str, model: str, use_group: bool) -> tuple[bool, str]:
    url = f"{base}/chat/completions"
    if use_group and GROUP:
        url += "?" + urllib.parse.urlencode({"GroupId": GROUP})
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "只回复两个字：收到"}],
            "max_tokens": 20,
            "stream": False,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
        choice = (data.get("choices") or [{}])[0]
        msg = (choice.get("message") or {}).get("content")
        base_resp = data.get("base_resp") or {}
        if msg:
            return True, f"OK: {str(msg)[:40]!r}"
        return False, f"no content; base_resp={base_resp}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:160]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


for base in BASES:
    for model in MODELS:
        for use_group in ([False, True] if GROUP else [False]):
            ok, detail = probe(base, model, use_group)
            tag = "group" if use_group else "nogroup"
            print(f"{'PASS' if ok else 'fail'}  {base:32s} {model:20s} {tag:8s} {detail}")
            if ok:
                print("\n>>> USE THESE:")
                print(f"LLM_BASE_URL={base}")
                print(f"LLM_MODEL={model}")
                raise SystemExit(0)
print("\nno combination worked")
raise SystemExit(1)
