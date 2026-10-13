#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦图鉴 · 交互模式（新手直接玩）
"""

import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent

# 载入 .env 里的 MCP Token（如果有的话），实时功能就能用
env_file = BASE / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(BASE))
from mcd_dex.dex_engine import McDex, Team, SaveFile  # noqa: E402


def menu():
    print()
    print("=" * 46)
    print("  🎮 麦麦图鉴 · McDex")
    print("=" * 46)
    print("  1. 看图鉴（160 只全览，标注你抓过的）")
    print("  2. 查一只（输入名字，如：巨无霸）")
    print("  3. 🌲 出门觅食（随机遭遇战——真正的捕捉在这里）")
    print("  4. 组队记录（把今天真吃过的登记进图鉴）")
    print("  5. ✨ 闪光预报（今日上新/限定，需Token）")
    print("  6. 🎫 券感知（查券池，需Token）")
    print("  7. 我的成就")
    print("  0. 退出")
    print("-" * 46)
    print("  新手推荐：先按 3 出门觅食，撞见什么看运气，")
    print("  薯条盒三晃稳住才算抓到——闪光只有 4% 遭遇率。")
    print("=" * 46)


def encounter(dex, save):
    """随机遭遇战：撞见 → 丢薯条盒 → 三晃 → 收服或挣脱。"""
    sp = dex.roll_encounter()
    print()
    print("🌲 草丛晃了一下……")
    time.sleep(0.8)
    rare_hint = {"闪光": "???: 一阵特别的气息，像是限时活动才会有的东西……",
                 "史诗": "???: 个头不小，动静很大，不太好对付的样子。",
                 "稀有": "???: 有几分特别的身影。", "常见": "???: 常见的身影。"}
    print("   " + rare_hint[sp.rarity])
    print()
    print("   %s %s ｜%s ｜%s" % (sp.silhouette(), "？？？", sp.category, sp.rarity))
    print()
    while True:
        cmd = input("   丢薯条盒按 y，转身离开按 n > ").strip().lower()
        if cmd in ("y", "n"):
            break
        print("   按 y 或 n。")
    if cmd == "n":
        print("   你悄悄退出了草丛。它目送你离开。")
        return
    time.sleep(0.5)
    caught, shakes = dex.throw_fries(sp)
    for i, ev in enumerate(shakes, 1):
        time.sleep(0.7)
        print("   第%d晃 … %s" % (i, ev))
    if caught:
        print()
        print("   ✅ 收服成功！")
        print(sp.card(owned=True, detail=True))
        save.caught[sp.id] = save.caught.get(sp.id, 0) + 1
        save.save()
        total = sum(save.caught.values())
        new_ach = save.check_new_achievements()
        if new_ach:
            print("   🏅 达成新成就：%s" % "、".join(new_ach))
        print("   （图鉴进度 %d/%d，累计捕获 %d 只）" % (
            len(save.caught), len(dex.species), total))
    else:
        print()
        print("   💨 它挣脱薯条盒跑了……下次手快点。")


def main():
    dex = McDex()
    save = SaveFile()
    print("\n欢迎回来，训练师。当前捕获 %d 只。" % len(save.caught))
    while True:
        menu()
        choice = input("请选择 > ").strip()
        if choice == "0":
            print("下次饿了对图鉴喊一声。👋")
            break
        elif choice == "1":
            print(dex.grid(set(save.caught)))
        elif choice == "2":
            kw = input("查什么 > ").strip()
            hits = dex.search(kw)
            if not hits:
                print("没找到这只。试试别的关键词。")
            for sp in hits[:5]:
                print()
                print(sp.card(owned=sp.id in save.caught, detail=True))
        elif choice == "3":
            encounter(dex, save)
        elif choice == "4":
            raw = input("输入编号（空格分隔，如 MCD029 MCD006 MCD031）> ").strip()
            ids = [x for x in raw.split() if x]
            if not ids:
                print("没收到编号。编号可以在「看图鉴」里找。")
                continue
            team = Team(dex)
            for sid in ids:
                print(team.add(sid))
            print()
            print(team.catch_feed())
            print()
            print(team.totals_report())
            for line in team.combo_report():
                print(line)
            save.register_catch(team)
            save.snapshot_team(team)
            save.save()
            print("\n💾 已存档。")
        elif choice == "5":
            try:
                from mcd_dex.live import shiny_forecast
                shiny_forecast()
            except Exception as e:
                print("实时功能暂时不可用：%s" % e)
        elif choice == "6":
            try:
                from mcd_dex.live import coupon_radar
                names = [dex.by_id(sid).name for sid in save.caught if dex.by_id(sid)]
                coupon_radar(names[:12])
            except Exception as e:
                print("实时功能暂时不可用：%s" % e)
        elif choice == "7":
            print(save.achievements_report())
        else:
            print("没这个选项。")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n下次饿了对图鉴喊一声。👋")
