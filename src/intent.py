"""Turn a Chinese free-text request into structured search parameters.

Two parsers:
  * parse_rules()  – regex based, no network, always available (fallback / offline demo)
  * parse_llm()    – asks an OpenAI-compatible model for strict JSON, best quality
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉",
    "西安", "天津", "长沙", "青岛", "厦门", "宁波", "合肥", "郑州", "济南", "福州",
]

# 高频地名 -> 城市，解决「西湖」被解析到台湾苗栗县西湖乡这类跨省歧义
LANDMARK_CITY = {
    "西湖": "杭州", "西湖区": "杭州", "杭州东站": "杭州", "萧山机场": "杭州", "灵隐寺": "杭州",
    "外滩": "上海", "南京路": "上海", "陆家嘴": "上海", "人民广场": "上海", "虹桥": "上海",
    "故宫": "北京", "天安门": "北京", "三里屯": "北京", "中关村": "北京", "国贸": "北京",
    "世界之窗": "深圳", "深圳湾": "深圳", "华强北": "深圳",
    "天河城": "广州", "广州塔": "广州", "珠江新城": "广州",
    "春熙路": "成都", "宽窄巷子": "成都", "太古里": "成都",
    "洪崖洞": "重庆", "解放碑": "重庆",
    "黄鹤楼": "武汉", "光谷": "武汉",
    "大雁塔": "西安", "钟楼": "西安", "鼓楼": "南京",
}

KEYWORDS = {
    "咖啡": "050500",
    "奶茶": "050500",
    "火锅": "050000",
    "烧烤": "050000",
    "日料": "050000",
    "川菜": "050000",
    "快餐": "050000",
    "甜品": "050000",
    "酒吧": "080300",
    "超市": "060400",
    "商场": "060100",
    "医院": "090100",
    "酒店": "100000",
    "景点": "110000",
    "停车场": "150900",
}

_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass
class Intent:
    origin: str | None = None
    city: str | None = None
    keyword: str = "餐厅"
    types: str = "050000"
    budget: float | None = None
    radius_m: int = 3000
    top: int = 3
    min_rating: float | None = None
    travel_mode: str | None = None  # walking / bicycling / driving / auto
    source: str = "rules"
    raw: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _to_int(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    if token in _CN_NUM:
        return _CN_NUM[token]
    return None


def parse_rules(text: str) -> Intent:
    t = text.strip()
    intent = Intent(raw=t, source="rules")

    # ---- origin
    for pattern in (
        r"从\s*([^，,。;；]{1,20}?)\s*(?:出发|走|开始|过去)",
        r"在\s*([^，,。;；]{1,20}?)\s*(?:附近|周边|周围|旁边|边上)",
        r"([^，,。;；]{2,20}?)(?:附近|周边|周围|旁边|边上)",
    ):
        m = re.search(pattern, t)
        if m:
            intent.origin = m.group(1).strip()
            break

    # ---- city（先看文本里的城市名，再用起点地标反推）
    for city in CITIES:
        if city in t:
            intent.city = city
            break
    if not intent.city and intent.origin:
        for landmark, city in LANDMARK_CITY.items():
            if landmark in intent.origin:
                intent.city = city
                break

    # ---- budget: 人均100 / 预算 100 / 100元以内 / 不超过100
    for pattern in (
        r"人均\s*(\d+(?:\.\d+)?)",
        r"预算\s*(?:在|是)?\s*(\d+(?:\.\d+)?)",
        r"不超过\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|内|左右)",
    ):
        m = re.search(pattern, t)
        if m:
            intent.budget = float(m.group(1))
            break

    # ---- radius: 3公里 / 800米 / 步行10分钟
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:公里|千米|km|KM)", t)
    if m:
        intent.radius_m = int(float(m.group(1)) * 1000)
    else:
        m = re.search(r"(\d+)\s*米", t)
        if m:
            intent.radius_m = int(m.group(1))
        else:
            m = re.search(r"(?:步行|走路|骑车|开车)\s*(\d+)\s*分钟", t)
            if m:
                intent.radius_m = int(m.group(1)) * 80  # 步行 80m/min 粗估

    # ---- rating: 评分4.5以上 / 4.5分以上 / 4.5以上
    m = re.search(r"(?:评分|打分)\s*(\d(?:\.\d)?)", t) or re.search(
        r"(\d(?:\.\d)?)\s*分?\s*(?:以上|及以上)", t
    )
    if m and float(m.group(1)) <= 5.0:
        intent.min_rating = float(m.group(1))

    # ---- top: 前3家 / 3家
    m = re.search(r"(?:前|要)\s*([一二两三四五六七八九十\d]+)\s*家", t)
    if m:
        n = _to_int(m.group(1))
        if n:
            intent.top = max(1, min(n, 10))

    # ---- keyword / poi type
    for kw, code in KEYWORDS.items():
        if kw in t:
            intent.keyword = "咖啡" if kw == "奶茶" else kw
            intent.types = code
            break
    else:
        if "吃" in t or "饭" in t or "餐" in t:
            intent.keyword = "餐厅"

    # ---- travel mode hint
    if "走" in t or "步行" in t:
        intent.travel_mode = "walking"
    elif "骑" in t:
        intent.travel_mode = "bicycling"
    elif "开车" in t or "驾车" in t:
        intent.travel_mode = "driving"

    if not intent.origin:
        intent.notes.append("没识别出起点，请用「从XX出发」或「XX附近」表述")
    return intent


LLM_SYSTEM_PROMPT = """你是出行助手的参数解析器。把用户的中文请求解析成 JSON，只输出 JSON，不要解释。

字段定义：
- origin: string|null  出发地/参照地点，原样保留地名
- city:   string|null  城市名（用于地名消歧，如 杭州）
- keyword: string      搜索关键词，如 餐厅/咖啡/火锅/停车场，默认 "餐厅"
- types: string        高德 POI 类型码：餐饮 050000，咖啡 050500，商场 060100，景点 110000，停车场 150900
- budget: number|null  人均预算上限（元）
- radius_m: number     搜索半径（米），默认 3000
- top: number          返回条数，默认 3，最大 10
- min_rating: number|null  最低评分（0-5）
- travel_mode: "walking"|"bicycling"|"driving"|null  出行方式偏好

示例输入：从杭州东站出发，找家人均100以内、评分4.5以上、走路能到的餐厅，要前3家
示例输出：{"origin":"杭州东站","city":"杭州","keyword":"餐厅","types":"050000","budget":100,"radius_m":3000,"top":3,"min_rating":4.5,"travel_mode":"walking"}
"""


def parse_llm(client, text: str) -> Intent:
    """Ask the model for JSON; fall back to rules on any failure."""
    base = parse_rules(text)
    if client is None or not getattr(client, "configured", False):
        return base

    try:
        raw = client.chat(
            [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=900,
            json_mode=True,
        )
        data = json.loads(raw.strip().strip("`").removeprefix("json").strip())
    except Exception as exc:  # noqa: BLE001 - degraded mode is fine
        base.notes.append(f"LLM 解析失败，已退回规则解析：{exc}")
        return base

    intent = Intent(raw=text, source="llm")
    intent.origin = data.get("origin") or base.origin
    intent.city = data.get("city") or base.city
    intent.keyword = data.get("keyword") or base.keyword
    intent.types = str(data.get("types") or base.types)
    budget = data.get("budget")
    intent.budget = float(budget) if isinstance(budget, (int, float)) else base.budget
    radius = data.get("radius_m")
    intent.radius_m = int(radius) if isinstance(radius, (int, float)) and radius > 0 else base.radius_m
    top = data.get("top")
    intent.top = max(1, min(int(top), 10)) if isinstance(top, (int, float)) else base.top
    rating = data.get("min_rating")
    intent.min_rating = float(rating) if isinstance(rating, (int, float)) else base.min_rating
    mode = data.get("travel_mode")
    intent.travel_mode = mode if mode in {"walking", "bicycling", "driving"} else base.travel_mode
    if not intent.origin:
        intent.notes.append("没识别出起点，请用「从XX出发」或「XX附近」表述")
    return intent
