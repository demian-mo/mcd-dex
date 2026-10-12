#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦图鉴 · 交互模式（新手直接玩）
"""

import os
import sys
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
    print("  3. 组队捕获（输入编号，空格分隔）")
    print("  4. ✨ 闪光预报（今日上新/限定，需Token）")
    print("  5. 🎫 券感知（查券池，需Token）")
    print("  6. 我的成就")
    print("  0. 退出")
    print("-" * 46)
    print("  新手推荐路线：先按 3，输入  MCD029 MCD006 MCD031")
    print("  （巨无霸+大薯条+可乐，体验组合技）")
    print("=" * 46)


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
        elif choice == "4":
            try:
                from mcd_dex.live import shiny_forecast
                shiny_forecast()
            except Exception as e:
                print("实时功能暂时不可用：%s" % e)
        elif choice == "5":
            try:
                from mcd_dex.live import coupon_radar
                names = [dex.by_id(sid).name for sid in save.caught if dex.by_id(sid)]
                coupon_radar(names[:12])
            except Exception as e:
                print("实时功能暂时不可用：%s" % e)
        elif choice == "6":
            print(save.achievements_report())
        else:
            print("没这个选项。")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n下次饿了对图鉴喊一声。👋")
