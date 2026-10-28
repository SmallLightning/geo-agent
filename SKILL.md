---
name: nearby-explorer
description: 基于高德地图开放平台的周边地点探索与路线规划。当用户用一句话询问"附近有什么好吃的/好玩的""人均XX以内的餐厅""走路能不能到""怎么过去"时使用。返回候选地点（名称、评分、人均、地址）以及到达方式（步行/骑行/驾车的距离与耗时）。
license: Apache-2.0
---

# 周边去哪儿（nearby-explorer）

把一句中文需求变成「去哪 + 怎么去」。

## 何时使用

用户问的是**位置 + 需求**，例如：

- 「附近有什么好吃的」「人均 100 以内的餐厅」
- 「西湖附近评分 4.5 以上的咖啡店」
- 「从杭州东站出发，走路能到的地方」
- 「人民广场附近 2 公里内的火锅，要前 5 家」

不适用：纯知识问答、和地理位置无关的查询。

## 怎么调用

```bash
python3 scripts/nearby.py --query "从杭州东站出发，找家人均100以内、评分4.5以上、走路能到的餐厅，要前3家"
```

加 `--json` 输出结构化结果（Agent 解析用）：

```bash
python3 scripts/nearby.py --query "西湖附近人均60以下的咖啡店" --json
```

可选参数：

| 参数 | 作用 |
|---|---|
| `--json` | 输出 JSON，而不是给人看的文本 |
| `--offline` | 只用内置快照，不联网 |
| `--no-llm` | 只用规则解析，不调用大模型 |

## 输出

给人看的文本长这样：

```
从 杭州东站 出发，3000 米内按人均100元以内、评分4.5以上帮你挑了 3 家：
1. 不伤心理想国(杭州东站万象汇店)｜4.7分｜人均44元｜步行（0.6km，约8分钟）
   地址：杭州东站万象汇L301(火车东站东广场地铁站J口旁)
```

JSON 结构：

```json
{
  "ok": true,
  "intent": {"origin": "杭州东站", "city": "杭州", "keyword": "餐厅",
             "budget": 100.0, "radius_m": 3000, "top": 3,
             "min_rating": 4.5, "travel_mode": "walking", "source": "rules"},
  "offline": false,
  "llm_used": false,
  "result": {
    "origin": {"formatted": "杭州东站", "lng": 120.2126, "lat": 30.290851},
    "recommendations": [
      {"name": "不伤心理想国(杭州东站万象汇店)", "rating": 4.7, "cost": 44.0,
       "address": "杭州东站万象汇L301", "straight_m": 536,
       "route": {"mode": "walking", "distance_m": 604, "duration_s": 480}}
    ]
  },
  "answer": "……"
}
```

## 能力边界（重要）

- 只返回**高德 POI 与路径数据**，不编造营业时间、电话、是否有停车位；
- 用户没给起点时返回 `ok: false` 并提示「从XX出发」；
- 「西湖」「鼓楼」这类跨省重名地标，用内置地标→城市表纠正（西湖→杭州），必要时让用户补充城市；
- 预算/评分缺失的 POI 不直接丢弃（记为未知），排序时后置。

## 运行依赖

- Python 3.9+，**零第三方依赖**（仅标准库）
- 环境变量 `AMAP_KEY`（高德 Web 服务 Key）；没有 Key 时自动降级到内置快照，仍可完整演示
- 可选 `MINIMAX_API_KEY` / `STEPFUN_API_KEY`：启用大模型解析，理解「安静点」「能停车」这类模糊偏好

## 参考

- `README.md`：架构、接口、开发说明
- `run.sh`：一键入口（自动判断在线/离线）
- `tests/`：16 个单元测试，`python3 -m unittest discover -s tests`
