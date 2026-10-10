#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦图鉴 · 实时情报模块（Live Feed）

两个只读能力，均来自麦当劳 MCP 官方接口：

1. 券感知（available-coupons）
   - 拉取「麦麦省」当前券列表（标题 + 状态）
   - 与队伍成员做匹配，提示更便宜的捕获路径
   - ⚠️ 本项目只读不领：绝不调用 auto-bind-coupons，不做任何账户写操作

2. 闪光预报（campaign-calendar）
   - 拉取官方活动日历，识别「上新/限定/联名/回归」类活动
   - 限定个体（图鉴·彩蛋科/闪光）出没窗口预警

无 Token 时给出友好提示，不影响离线玩法。
"""

from __future__ import annotations

import re
from typing import Optional

try:
    from .mcp_client import McHttpClient
except ImportError:  # 以脚本方式直接运行时
    from mcp_client import McHttpClient

# ----------------------------------------------------------
# 解析：麦麦省优惠券
# ----------------------------------------------------------

def parse_coupons(text: str) -> list[dict]:
    """`- 优惠券标题：X 状态：Y` 的 markdown 列表 → [{'title','status'}]。"""
    coupons: list[dict] = []
    seen: set = set()
    for block in re.split(r"-\s*优惠券标题：", text)[1:]:
        first_line = block.split("\n", 1)[0].rstrip("\\").strip()
        status = "未知"
        if "可领取" in block:
            status = "可领取"
        elif "已领取" in block:
            status = "已领取"
        key = (first_line, status)
        if first_line and key not in seen:
            seen.add(key)
            coupons.append({"title": first_line, "status": status})
    return coupons


def _core_keys(name: str) -> list[str]:
    """物种名 → 用于券标题匹配的关键词集合。

    组成：完整名（去规格词）+ 相邻 2 元组（抓「鸡腿」「薯条」这类共现词，
    让「麦辣鸡腿汉堡」也能命中「龙焰鸡腿堡三件套」的券）。
    """
    cleaned = name
    for w in ("小杯", "中杯", "大杯", "（中）", "(中)", "5块", "-2块", "2块"):
        cleaned = cleaned.replace(w, "")
    cleaned = re.sub(r"（[^）]*）|\([^)]*\)", "", cleaned).strip()
    keys = set()
    if len(cleaned) >= 2:
        keys.add(cleaned)
        for i in range(len(cleaned) - 1):
            keys.add(cleaned[i:i + 2])
    return sorted(k for k in keys if len(k) >= 2)


def match_coupons(team_names: list[str], coupons: list[dict]) -> list[dict]:
    """队伍成员名 × 券标题 的宽松匹配，返回命中的券。"""
    keys: list[str] = []
    for n in team_names:
        keys.extend(_core_keys(n))
    hits = []
    for c in coupons:
        if any(k and k in c["title"] for k in keys):
            hits.append(c)
    return hits


# ----------------------------------------------------------
# 解析：活动日历
# ----------------------------------------------------------

SHINY_PAT = re.compile(r"上新|新品|限定|联名|回归|开售|首发|首推|推出")
STATUS_ORDER = {"进行中": 0, "今日": 1, "未来": 2, "往期回顾": 3}


def parse_campaigns(text: str) -> list[dict]:
    """`#### 日期 状态` 分节 + `**活动标题**：` → [{'date','status','title','body'}]。"""
    campaigns: list[dict] = []
    for sec in re.split(r"####\s*", text)[1:]:
        header = sec.split("\n", 1)[0].strip()
        m = re.match(r"(\d{4}年\d{1,2}月\d{1,2}日)\s*(.*)", header)
        if not m:
            continue
        date, status = m.group(1), (m.group(2) or "").strip() or "未标注"
        blocks = re.split(r"\*\*活动标题\*\*：", sec)[1:]
        for b in blocks:
            title = b.split("\n", 1)[0].strip()
            body_m = re.search(r"\*\*活动内容介绍\*\*：(.+?)(?:\*\*活动图片介绍|$)", b, re.S)
            body = re.sub(r"\s+", " ", body_m.group(1)).strip()[:120] if body_m else ""
            if title:
                campaigns.append({"date": date, "status": status, "title": title, "body": body})
    campaigns.sort(key=lambda c: STATUS_ORDER.get(c["status"], 9))
    return campaigns


def shiny_report(campaigns: list[str] = None, text: str = None, limit: int = 8) -> str:
    """渲染闪光出没预报（传 text 或 campaigns 二选一）。"""
    if campaigns is None:
        campaigns = parse_campaigns(text or "")
    rows = ["✨ 闪光出没预报（上新 / 限定 / 联名 / 回归）", ""]
    shown = 0
    for c in campaigns:
        if c["status"] == "往期回顾":
            continue
        hit = SHINY_PAT.search(c["title"] + " " + c["body"])
        mark = "✨" if hit else "·"
        status = c["status"]
        rows.append("%s [%s] %s" % (mark, status, c["title"]))
        if hit and c["body"]:
            rows.append("    └ %s" % c["body"][:60])
        shown += 1
        if shown >= limit:
            break
    if shown == 0:
        rows.append("（近期没有观测到限定动向。图鉴学家们正在补觉。）")
    rows.append("")
    rows.append("💡 提示：限定/联名上新期间，对应个体按编目规则将标记为✨闪光——错过了可能要再等一年。")
    return "\n".join(rows)


# ----------------------------------------------------------
# 在线入口（带离线降级）
# ----------------------------------------------------------

def _client() -> Optional[McHttpClient]:
    try:
        return McHttpClient()
    except RuntimeError as e:
        print("⚠️ %s" % e)
        return None


def coupon_radar(team_names: list[str]) -> None:
    """券感知：打印当前麦麦省券列表中与队伍相关的券。只读，不领取。"""
    client = _client()
    if not client:
        return
    print("· 连接麦当劳 MCP 查询麦麦省券 ...")
    client.initialize()
    result = client.call_tool("available-coupons")
    text = "".join(x.get("text", "") for x in result.get("content", []) if x.get("type") == "text")
    coupons = parse_coupons(text)
    avail = [c for c in coupons if c["status"] == "可领取"]
    print("🎫 当前共 %d 张券（可领 %d 张 / 已领 %d 张）" % (
        len(coupons), len(avail), len(coupons) - len(avail)))

    hits = match_coupons(team_names, coupons)
    if hits:
        print("🎯 与你的队伍相关：")
        for c in hits:
            icon = "🟢" if c["status"] == "可领取" else "⚪"
            print("   %s %s（%s）" % (icon, c["title"], c["status"]))
    else:
        print("（当前券池没有和队伍直接相关的券。换个队伍组成试试？）")
    print("💡 本项目只读不领：领券请通过麦当劳官方渠道，图鉴只负责提醒你有钱没花。")


def shiny_forecast() -> None:
    """闪光预报：打印官方活动日历中的上新/限定动向。"""
    client = _client()
    if not client:
        return
    print("· 连接麦当劳 MCP 拉取活动日历 ...")
    client.initialize()
    result = client.call_tool("campaign-calendar")
    text = "".join(x.get("text", "") for x in result.get("content", []) if x.get("type") == "text")
    print()
    print(shiny_report(text=text))
