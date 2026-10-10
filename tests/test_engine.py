#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦图鉴 · 引擎自测（零依赖，直接跑）

    python3 tests/test_engine.py

全绿输出 TESTS PASSED。断言基于真实菜单同步后的 data/dex.json。
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from mcd_dex.dex_engine import McDex, Team, SaveFile  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✅ %s" % name)
    else:
        FAIL += 1
        print("  ❌ %s %s" % (name, extra))


def main():
    dex = McDex()

    print("[1] 图鉴加载（真实数据）")
    check("图鉴非空", len(dex.species) > 0)
    check("规模为全菜单级（>=100）", len(dex.species) >= 100, str(len(dex.species)))
    check("无待编目个体", all(s.category != "待编目科" for s in dex.species.values()))

    print("[2] 查询")
    bm = dex.by_id("MCD029")
    check("按编号查巨无霸", bm and bm.name == "巨无霸")
    check("按关键词查「辣」能命中", len(dex.search("辣")) >= 2)
    check("稀有度筛选史诗", len(dex.by_rarity("史诗")) >= 2)

    print("[3] 种族值面板")
    s = bm.stats()
    check("六维面板", set(s) == {"HP", "攻击", "防御", "特攻", "特防", "速度"})
    check("数值在合理区间", all(1 <= v <= 255 for v in s.values()), str(s))
    angus = dex.search("安格斯")[0].stats()
    icecream = dex.by_id("MCD015").stats()  # 圆筒冰淇淋
    check("重堡攻击高于圆筒", angus["攻击"] > icecream["攻击"])

    print("[4] 进化线")
    lines = dex.evolution_lines()
    check("存在经典牛线/火线", {"经典牛线", "火线"} <= set(lines))
    stages = [sp.evo.get("stage") for sp in lines.get("经典牛线", [])]
    check("经典牛线三阶", stages == [1, 2, 3], str(stages))
    fry = [sp.evo.get("stage") for sp in lines.get("薯薯线", [])]
    check("薯薯线四阶（迷你→大）", fry == [1, 2, 3, 4], str(fry))

    print("[5] 队伍与合计")
    t = Team(dex)
    t.add("MCD029"); t.add("MCD006"); t.add("MCD031")   # 巨无霸+大薯条+可乐中杯
    tot = t.totals()
    check("捕获三只", tot["count"] == 3)
    expected = 513 + 379 + 147
    check("热量=三者之和（官方值）", abs(tot["kcal"] - expected) < 1, "%s vs %s" % (tot["kcal"], expected))
    rep = t.totals_report()
    check("合计报表含百分比", "%/日" in rep)

    print("[6] 组合技")
    import datetime
    combos = t.combo_report(now=datetime.datetime(2026, 10, 10, 12, 0))
    joined = "\n".join(combos)
    check("堡+薯+可乐触发铁三角", "经典铁三角" in joined)
    check("巨无霸触发指数梗", "巨无霸指数" in joined)

    t2 = Team(dex)
    t2.add("MCD027"); t2.add(dex.search("麦辣鸡翅")[0].id)
    check("双辣触发共鸣", "双辣共鸣" in "\n".join(t2.combo_report()))

    t3 = Team(dex)
    t3.add(dex.search("苹板")[0].id)
    check("限定触发闪光捕获", "闪光捕获" in "\n".join(t3.combo_report()))

    print("[7] 存档与成就")
    save = SaveFile(BASE_DIR / "data" / "test_save.json")
    save.register_catch(t)
    save.snapshot_team(t)
    save.save()
    reloaded = SaveFile(BASE_DIR / "data" / "test_save.json")
    check("存档可回读", reloaded.caught.get("MCD029") == 1)
    check("历史快照记录", len(reloaded.history) == 1)
    check("初训师成就达成", "🟩 初训师" in reloaded.achievements_report())

    print("[8] 渲染")
    g = dex.grid(set(dex.species))
    check("全图鉴渲染捕获率", "160/160" in g)
    card = bm.card(owned=False)
    check("未捕获显示雾中", "雾中" in card)
    check("彩蛋科在图鉴中", "彩蛋科" in g)

    print("[9] 实时情报解析（离线夹具）")
    try:
        from mcd_dex.live import parse_coupons, match_coupons, parse_campaigns, shiny_report
    except ImportError:
        from live import parse_coupons, match_coupons, parse_campaigns, shiny_report

    coupon_fixture = """### 麦麦省优惠券列表：
- 优惠券标题：免费脆薯饼 \\
  状态：可领取 \\
- 优惠券标题：龙焰鸡腿堡三件套 26.9 元 \\
  状态：可领取 \\
- 优惠券标题：巧克力味厚松饼猪柳蛋套餐 \\
  状态：已领取 \\
"""
    coupons = parse_coupons(coupon_fixture)
    check("券解析出 3 张", len(coupons) == 3, str(coupons))
    check("券状态识别", coupons[0]["status"] == "可领取" and coupons[2]["status"] == "已领取")
    hits = match_coupons(["麦辣鸡腿汉堡"], coupons)
    check("券匹配：鸡腿汉堡命中鸡腿堡券", any("鸡腿" in c["title"] for c in hits), str(hits))
    hits2 = match_coupons(["大薯条"], coupons)
    check("券匹配：薯条与薯饼不混淆", not any("薯饼" in c["title"] for c in hits2), str(hits2))

    cal_fixture = """### 当前时间：2026-10-10 11:29:35

#### 2026年10月9日 往期回顾

-   **活动标题**：旧活动一则
    **活动内容介绍**：内容。

#### 2026年10月10日 今日

-   **活动标题**：蓝莓爆爆珠麦旋风上新
    **活动内容介绍**：真实蓝莓原浆x爆爆珠。
-   **活动标题**：普通抽奖活动
    **活动内容介绍**：积分抽奖。
"""
    camps = parse_campaigns(cal_fixture)
    check("日历解析出 2 条今日", sum(1 for c in camps if c["status"] == "今日") == 2, str(camps))
    check("往期被排到末尾", camps[-1]["status"] == "往期回顾")
    rep = shiny_report(campaigns=camps)
    check("上新被标记为闪光", "✨ [今日] 蓝莓" in rep)
    check("普通活动不带闪光标", "· [今日] 普通抽奖" in rep)

    print()
    print("=" * 40)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    if FAIL == 0:
        print("TESTS PASSED ✅")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
