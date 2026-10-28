#!/usr/bin/env bash
# 一键入口：有 Key 用实时数据，没有就用离线快照（评测机 / 评委 clone 下来直接能跑）
#
#   ./run.sh "从杭州东站出发，人均100以内、走路能到的餐厅"
#   ./run.sh --offline "西湖附近的咖啡"
#
set -uo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "需要 python3（3.9+）" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  set -- "从杭州东站出发，找家人均100以内、评分4.5以上、走路能到的餐厅，要前3家"
  echo "未提供参数，使用示例请求：$1"
  echo
fi

# 没配 AMAP_KEY 时直接走离线快照，避免抛异常
if [ ! -f .env ] || ! grep -qE '^AMAP_KEY=.+' .env; then
  echo "[offline] 未检测到 AMAP_KEY，使用内置快照数据演示"
  exec python3 src/agent.py --offline "$@"
fi

exec python3 src/agent.py "$@"
