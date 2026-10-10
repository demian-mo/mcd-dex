#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦图鉴 · 数据同步脚本

从麦当劳 MCP 官方接口（list-nutrition-foods）拉取全菜单营养数据：
- 官方返回格式：Markdown 包装 + JSON 外壳 + "[N]{fields}: rows" 结构化文本
- 营养数值原样入库（kJ/kcal/protein/fat/carb/sodium/calcium），不做任何编造
- 科属 / 稀有度 / 进化线由本项目的编目规则表（启发式）判定
- 同步结果写入 data/dex.json（覆盖前自动备份）

用法：
    export MCD_MCP_TOKEN=你的Token
    python3 scripts/fetch_dex.py            # 同步
    python3 scripts/fetch_dex.py --dry-run  # 只看分类报告，不写文件
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from mcd_dex.mcp_client import McHttpClient  # noqa: E402

DEX_PATH = BASE_DIR / "data" / "dex.json"

# ============================================================
# 编目规则（项目自定义，非麦当劳官方分类；数值一律不在此定义）
# ============================================================

CATEGORY_RULES = [
    # 彩蛋科：活动联名梗名个体（如程序员节限定），置顶优先判定
    (r"yeyeyeye|果然多肉|苹板|薯鱼|牛气满满", "彩蛋科"),
    (r"麦满分|早餐|早安|营养卷|图林根|脆薯饼|油条|粥|豆浆", "晨晨科"),
    (r"新地|旋风|圆筒|圣代|蛋挞|冰淇淋|蛋糕|甜品|派$|阿芙佳朵|拉明顿|奶冻|爆珠", "甜甜科"),
    (r"可乐|雪碧|咖啡|拿铁|美式|红茶|绿茶|柠檬|奶茶|奶昔|朱古力|牛奶|麦旋酷|特调|汽水|锡兰|橙|汁|水$|奶铁|玛奇朵|卡布奇诺|燕麦|黑巧|雪冰|怡泉|纯悦", "饮饮科"),
    (r"堡|汉堡|巨无霸|安格斯|板烧|牛堡|麦香鸡|麦香鱼", "堡堡科"),
    (r"薯条|薯盒", "薯薯科"),
    (r"麦乐鸡|鸡翅|鸡排|玉米|那么大|麦乐鸡5块|鸡球|V翅|双翅|翅$|卷$|苹果片", "零嘴科"),
]

RARITY_RULES = [
    (r"巨无霸|安格斯|双层|那么大", "史诗"),
    (r"限定|季节|活动|yeyeyeye|果然多肉|苹板|薯鱼|牛气满满|绝代双翅", "闪光"),
    (r"麦辣|大薯条|中薯条|大杯|新品|风味", "稀有"),
]

# 进化线锚点（基于真实餐品名）
EVO_ANCHORS = [
    (r"^吉士汉堡包$", "经典牛线", 1),
    (r"^双层吉士汉堡$", "经典牛线", 2),
    (r"^巨无霸$", "经典牛线", 3),
    (r"^麦香鸡$", "火线", 1),
    (r"^麦辣鸡腿汉堡$", "火线", 2),
    (r"^迷你薯条$", "薯薯线", 1),
    (r"^小薯条$", "薯薯线", 2),
    (r"^中薯条$", "薯薯线", 3),
    (r"^大薯条$", "薯薯线", 4),
    (r"^可乐小杯$", "碳酸线·可乐", 1),
    (r"^可乐中杯$", "碳酸线·可乐", 2),
    (r"^可乐大杯$", "碳酸线·可乐", 3),
    (r"^雪碧小杯$", "碳酸线·雪碧", 1),
    (r"^雪碧中杯$", "碳酸线·雪碧", 2),
    (r"^雪碧大杯$", "碳酸线·雪碧", 3),
    (r"^圆筒冰淇淋$", "甜品线", 1),
    (r"麦旋风|新地", "甜品线", 2),
    (r"^猪柳麦满分$", "晨晨线", 1),
    (r"^猪柳蛋麦满分$", "晨晨线", 2),
    (r"^小杯玉米杯$", "玉米线", 1),
    (r"^大杯玉米杯$", "玉米线", 2),
]

FLAVOR_BY_CATEGORY = {
    "堡堡科": "厚实可靠的主力选手。单层还是双层，决定它是同伴还是BOSS。",
    "薯薯科": "进化只会长个的奇妙物种。永远第一个被清空。",
    "饮饮科": "流动性极强的辅助型宝可梦。与堡堡科同场会发动组合技。",
    "甜甜科": "治愈系收尾担当。出现即宣告本轮对局进入幸福结局。",
    "晨晨科": "仅在上午出没的限时宝可梦。早起的训练师才配拥有。",
    "零嘴科": "社交场合的高频出没者。总是被整份捕获，但没人记得吃了几块。",
    "彩蛋科": "活动限定的联名梗个体。名字即谜题，读懂的人会心一笑。",
    "待编目科": "新观测到的神秘个体，编目学家的望远镜已就位。",
}

RARITY_FLAVOR = {
    "史诗": "（图鉴备注：该个体战斗力和满足感都属于顶级梯队。）",
    "闪光": "（图鉴备注：季节限定闪光体，错过了就要再等一年。）",
    "稀有": "（图鉴备注：值得专门绕路去捕获的个体。）",
}


# ============================================================
# 官方返回体解析
# ============================================================

def extract_rows(raw_text: str) -> list[dict]:
    """Markdown 包装 → JSON 外壳 → '[N]{fields}:' 行协议 → 行字典列表。"""
    marker = "## Original Response"
    if marker in raw_text:
        raw_text = raw_text.split(marker, 1)[1]
    start, end = raw_text.find("{"), raw_text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("未在返回体中找到 JSON 外壳")
    outer = json.loads(raw_text[start:end + 1])
    if not outer.get("success", True) or outer.get("code") not in (200, 0, None):
        raise RuntimeError("接口返回失败：%s" % outer.get("message"))
    data_str = outer.get("data") or ""
    m = re.match(r"\[(\d+)\]\{([^}]+)\}\s*:", data_str.strip())
    if not m:
        raise RuntimeError("data 字段不是预期的行协议格式，前 200 字：%s" % data_str[:200])
    fields = [f.strip() for f in m.group(2).split(",")]
    rows = []
    for line in data_str[m.end():].strip().splitlines():
        line = line.strip()
        if not line:
            continue
        vals = [v.strip() for v in line.split(",")]
        # 名称中含逗号的极端情况：多余的段并回名称
        if len(vals) > len(fields):
            vals = [",".join(vals[:len(vals) - len(fields) + 1])] + vals[len(vals) - len(fields) + 1:]
        if len(vals) != len(fields):
            continue
        rows.append(dict(zip(fields, vals)))
    return rows


# ============================================================
# 编目
# ============================================================

def match_first(patterns, text):
    for pat, val in patterns:
        if re.search(pat, text):
            return val
    return None


def to_num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def classify(name: str) -> tuple[str, str, dict]:
    category = match_first(CATEGORY_RULES, name) or "待编目科"
    rarity = match_first(RARITY_RULES, name) or "常见"
    evo = {}
    for pat, line, stage in EVO_ANCHORS:
        if re.search(pat, name):
            evo = {"line": line, "stage": stage}
            break
    return category, rarity, evo


def pick_emoji(name: str) -> str:
    table = [
        (r"巨无霸|安格斯|板烧|堡|汉堡", "🍔"),
        (r"麦满分", "🥯"),
        (r"薯条", "🍟"),
        (r"可乐|雪碧|汽水|特调", "🥤"),
        (r"咖啡|美式|浓缩", "☕"),
        (r"柠檬|红茶|锡兰|茶", "🍋"),
        (r"奶昔|牛奶|奶", "🥛"),
        (r"麦旋酷|橙|汁", "🧃"),
        (r"旋风|圆筒|圣代|冰淇淋|新地", "🍦"),
        (r"派|蛋挞", "🥧"),
        (r"麦乐鸡|鸡翅|鸡排|鸡", "🍗"),
        (r"玉米", "🌽"),
        (r"朱古力|巧克力", "🍫"),
    ]
    for pat, emo in table:
        if re.search(pat, name):
            return emo
    return "🍽️"


def build_tags(name: str, category: str) -> list[str]:
    tags = []
    if "辣" in name:
        tags.append("辣")
    if "无糖" in name or "零度" in name:
        tags.append("零糖")
    if "咖啡" in name or "浓缩" in name or "拿铁" in name:
        tags.append("含咖啡因")
    if category == "晨晨科":
        tags.append("限时出没")
    return tags


def build_species(row: dict, seq: int) -> dict:
    name = row.get("productName", "").strip()
    category, rarity, evo = classify(name)
    kcal = to_num(row.get("energyKcal"))
    flavor = FLAVOR_BY_CATEGORY.get(category, "") + RARITY_FLAVOR.get(rarity, "")
    if kcal == 0:
        flavor += "（观测记录：能量读数为零。传说中的无糖系幽灵个体？）"
    return {
        "id": "MCD%03d" % seq,
        "name": name,
        "emoji": pick_emoji(name),
        "category": category,
        "rarity": rarity,
        "kcal": int(kcal),
        "protein": to_num(row.get("protein")),
        "fat": to_num(row.get("fat")),
        "carbs": to_num(row.get("carbohydrate")),
        "sodium": to_num(row.get("sodium")),
        "calcium": to_num(row.get("calcium")),
        "evo": evo,
        "flavor": flavor,
        "tags": build_tags(name, category),
    }


# ============================================================
# 主流程
# ============================================================

def review_report(species: list[dict]) -> str:
    from collections import Counter
    cats = Counter(sp["category"] for sp in species)
    rars = Counter(sp["rarity"] for sp in species)
    unknown = [sp["name"] for sp in species if sp["category"] == "待编目科"]
    lines = [
        "📋 编目报告：共 %d 只" % len(species),
        "  科属分布：" + "、".join("%s×%d" % kv for kv in cats.most_common()),
        "  稀有度：" + "、".join("%s×%d" % kv for kv in rars.most_common()),
    ]
    if unknown:
        lines.append("  ⚠️ 待编目（%d）：%s" % (len(unknown), "、".join(unknown[:20])))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = McHttpClient()
    print("· 连接麦当劳 MCP ...")
    client.initialize()
    result = client.call_tool("list-nutrition-foods")
    raw_text = "".join(
        c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"
    )
    rows = extract_rows(raw_text)
    species = [build_species(r, i + 1) for i, r in enumerate(rows)]

    print(review_report(species))

    if args.dry_run:
        print("… dry-run 模式，未写入文件。")
        return

    out = {
        "meta": {
            "source": "mcd-mcp:list-nutrition-foods",
            "generated_at": str(date.today()),
            "note": "营养数值来自麦当劳 MCP 官方接口；科属/稀有度/进化线为项目编目规则，非官方分类。"
        },
        "species": species,
    }
    if DEX_PATH.exists():
        backup = DEX_PATH.with_suffix(".json.bak")
        shutil.copy2(DEX_PATH, backup)
        print("· 已备份旧图鉴 -> %s" % backup.name)
    DEX_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✅ 图鉴已更新 -> data/dex.json（%d 只）" % len(species))


if __name__ == "__main__":
    main()
