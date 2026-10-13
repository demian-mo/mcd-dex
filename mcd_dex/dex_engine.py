#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦图鉴 · 核心引擎（McDex Engine）

职责：
- 图鉴加载与查询（按编号 / 名称 / 科属 / 稀有度）
- 种族值面板（营养值 -> 攻/防/速/特 的宝可梦式映射）
- 队伍（订单）编排：捕获登记、组合技检测、属性合计
- 存档（savefile.json）读写

数据来源：
- data/dex.json 可由 scripts/fetch_dex.py 从麦当劳 MCP 官方营养接口同步

本文件不包含任何真实 Token；凭据一律走环境变量 MCD_MCP_TOKEN。
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DEX_PATH = BASE_DIR / "data" / "dex.json"
SAVE_PATH = BASE_DIR / "data" / "savefile.json"

RARITY_ORDER = {"常见": 1, "稀有": 2, "史诗": 3, "传说": 4, "闪光": 5}
RARITY_ICON = {"常见": "●", "稀有": "◆", "史诗": "★", "传说": "👑", "闪光": "✨"}

# ---------- 官方营养参考值（成人每日，GB 28050 标示口径的常用近似） ----------
DAILY_REF = {
    "kcal": 2000,     # 能量 kcal
    "protein": 60,    # 蛋白质 g
    "fat": 60,        # 脂肪 g
    "carbs": 300,     # 碳水化合物 g
    "sodium": 2000,   # 钠 mg
    "calcium": 800,   # 钙 mg
}


# ============================================================
# 图鉴条目
# ============================================================

def _fmt(v) -> str:
    """数值显示：整数去掉小数点。"""
    f = float(v or 0)
    return str(int(f)) if f == int(f) else ("%.1f" % f)


@dataclass
class Species:
    id: str
    name: str
    emoji: str
    category: str          # 科属，例如「堡堡科」
    rarity: str            # 常见/稀有/史诗/传说/闪光
    kcal: int
    protein: float
    fat: float
    carbs: float
    sodium: float
    calcium: float
    flavor: str = ""       # 图鉴描述
    tags: list = field(default_factory=list)
    evo: dict = field(default_factory=dict)   # {line, stage, next, nextAlt}

    # ---------- 种族值面板 ----------
    def stats(self) -> dict:
        """把官方营养数据映射成宝可梦式种族值（满分为 255 的经典量纲）。

        映射原则（半玩笑半认真，README 里有说明）：
        - 攻击  = 蛋白质（力量来自蛋白）
        - 特攻  = 热量密度（kcal/g 蛋白质之外的能量轰炸）
        - 防御  = 脂肪（物理缓冲层）
        - 特防  = 钙（骨骼坚固）
        - 速度  = 碳水（快充能量）
        - HP   = 总热量（血条厚度）
        """
        return {
            "HP": self._scale(self.kcal, 0, 900, 40, 255),
            "攻击": self._scale(self.protein, 0, 40, 20, 200),
            "防御": self._scale(self.fat, 0, 45, 20, 200),
            "特攻": self._scale(self.kcal / max(self._nz(self.protein + self.fat), 1), 0, 18, 20, 220),
            "特防": self._scale(self.calcium, 0, 200, 20, 180),
            "速度": self._scale(self.carbs, 0, 70, 20, 200),
        }

    @staticmethod
    def _nz(x: float) -> float:
        return x if x else 1

    @staticmethod
    def _scale(v: float, lo: float, hi: float, out_lo: int, out_hi: int) -> int:
        if hi <= lo:
            return out_lo
        t = (v - lo) / (hi - lo)
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        return int(out_lo + t * (out_hi - out_lo))

    # ---------- 遭遇战 ----------
    def silhouette(self) -> str:
        """剪影形态：只露轮廓，不露脸。"""
        if self.category == "饮饮科":
            return " ▗▖ "
        if self.category in ("薯薯科", "零嘴科"):
            return " ▝▞ "
        return " ▟▙ "

    # ---------- 渲染 ----------
    def card(self, owned: bool = True, detail: bool = False) -> str:
        s = self.stats()
        bars = " ".join(f"{k}{v:>3}" for k, v in s.items())
        vis = "" if owned else " ｜雾中（未捕获，图鉴仅显示剪影）"
        evo_desc = ""
        if self.evo:
            evo_desc = f" ｜{self.evo.get('line', '?')}·第{self.evo.get('stage', '?')}阶"
            if self.evo.get("next"):
                evo_desc += " ｜可进化 →"
        lines = [
            f"{self.emoji} №{self.id} {self.name}"
            f" ｜{self.category} ｜{RARITY_ICON.get(self.rarity, '?')}{self.rarity}{evo_desc}{vis}",
            f"    种族值 {bars}",
        ]
        if detail:
            lines.append(
                "    官方营养值：能量%dkcal｜蛋白质%sg｜脂肪%sg｜碳水%sg｜钠%smg｜钙%smg"
                % (self.kcal, _fmt(self.protein), _fmt(self.fat), _fmt(self.carbs),
                   _fmt(self.sodium), _fmt(self.calcium))
            )
        lines.append(f"    {self.flavor}")
        return "\n".join(lines)


# ============================================================
# 图鉴本体
# ============================================================

class McDex:
    def __init__(self, dex_path: Path = DEX_PATH):
        raw = json.loads(Path(dex_path).read_text(encoding="utf-8"))
        self.meta: dict = raw.get("meta", {})
        self.species: dict[str, Species] = {}
        for item in raw["species"]:
            sp = Species(**item)
            self.species[sp.id] = sp

    # ---------- 查询 ----------
    def by_id(self, sid: str) -> Optional[Species]:
        return self.species.get(sid)

    def search(self, keyword: str) -> list[Species]:
        kw = keyword.strip()
        return [s for s in self.species.values()
                if kw in s.name or kw in s.category or kw in s.id or kw in "".join(s.tags)]

    def by_rarity(self, rarity: str) -> list[Species]:
        return [s for s in self.species.values() if s.rarity == rarity]

    def by_category(self, category: str) -> list[Species]:
        return [s for s in self.species.values() if s.category == category]

    def evolution_lines(self) -> dict[str, list[Species]]:
        lines: dict[str, list[Species]] = {}
        for s in self.species.values():
            if not s.evo:
                continue
            lines.setdefault(s.evo["line"], []).append(s)
        for members in lines.values():
            members.sort(key=lambda x: x.evo.get("stage", 0))
        return lines

    # ---------- 遭遇战 ----------
    # 每种稀有度的遭遇权重：常见满地走，闪光要碰运气
    ENCOUNTER_WEIGHT = {"常见": 100, "稀有": 30, "史诗": 10, "传说": 4, "闪光": 4}
    # 每种稀有度的单晃挣脱率（三晃全过才算收服）
    ESCAPE_RATE = {"常见": 0.05, "稀有": 0.18, "史诗": 0.30, "传说": 0.40, "闪光": 0.42}

    def roll_encounter(self) -> Species:
        """按稀有度权重随机抽一只遭遇。"""
        pool = list(self.species.values())
        weights = [self.ENCOUNTER_WEIGHT.get(s.rarity, 20) for s in pool]
        return random.choices(pool, weights=weights, k=1)[0]

    def throw_fries(self, sp: Species) -> tuple[bool, list[str]]:
        """丢出薯条盒，三晃判定。返回 (是否收服, 每晃事件文案)。"""
        escape = self.ESCAPE_RATE.get(sp.rarity, 0.2)
        shakes = []
        for i in range(3):
            if random.random() < escape:
                shakes.append("薯条盒晃了晃……它探出头来！")
                return False, shakes
            shakes.append("稳住没挣脱。")
        shakes.append("叮！锁定完成。")
        return True, shakes

    # ---------- 列表渲染 ----------
    def grid(self, caught_ids: set[str] | None = None) -> str:
        caught = caught_ids or set()
        out = ["📺 麦麦图鉴（捕获率 %d/%d）" % (len(caught & set(self.species)), len(self.species))]
        cur_cat = None
        seen_cats: set[str] = set()
        for s in sorted(self.species.values(), key=lambda x: x.id):
            if s.category != cur_cat:
                cur_cat = s.category
                cont = "（续）" if cur_cat in seen_cats else ""
                seen_cats.add(cur_cat)
                out.append("— %s%s —" % (cur_cat, cont))
            mark = s.emoji if s.id in caught else " ▪ "
            out.append("  %s №%s %-14s %s%s" % (
                mark, s.id, s.name, RARITY_ICON.get(s.rarity, "?"), s.rarity))
        return "\n".join(out)


# ============================================================
# 队伍（订单）与组合技
# ============================================================

@dataclass
class TeamMember:
    species_id: str
    qty: int = 1


class Team:
    """一支出餐队伍 = 一笔订单。捕获即登记。"""

    # 组合技定义：满足条件时的彩蛋文案（键名仅内部使用）
    COMBOS = {
        "burger_fries_coke": "🍔🍟🥤 经典铁三角：堡 + 薯 + 可乐同时在场，发动组合技「套餐的力量」！伤害翻倍，快乐也翻倍。",
        "double_spicy": "🌶️🔥 双辣共鸣：两件及以上辣系同时入场，火气场效应展开，饮饮科支援需求 +200%。",
        "big_mac_index": "🍔📈 巨无霸在场：你的队伍已被计入「巨无霸指数」统计样本，恭喜为经济学做出贡献。",
        "shiny_hunt": "✨ 闪光捕获：队伍中存在活动限定个体！本次出餐将写入《稀有出没观测记录》。",
        "full_burger": "🍔🍔🍔 堡堡科全家福：三件及以上堡堡科同场，发动团队技「一层不够就两层」。",
        "sweet_ending": "🍦 甜品收尾：甜甜科压轴登场，本轮对局以治愈系结局收场。",
        "morning_call": "🌅 晨之队：晨晨科成员在 10:30 前入场，享受「早起的训练师」称号加成。",
    }

    def __init__(self, dex: McDex):
        self.dex = dex
        self.members: list[TeamMember] = []

    def add(self, species_id: str, qty: int = 1) -> str:
        sp = self.dex.by_id(species_id)
        if not sp:
            return "❌ 图鉴里没有这只：%s（试试 search 查编号）" % species_id
        for m in self.members:
            if m.species_id == species_id:
                m.qty += qty
                return "重复捕获 %s ×%d" % (sp.name, m.qty)
        self.members.append(TeamMember(species_id, qty))
        return "🎉 捕获成功！%s %s 加入了队伍！" % (sp.emoji, sp.name)

    def catch_feed(self) -> str:
        """捕获播报：每只成员的完整图鉴卡（种族值 + 官方营养原值）。"""
        if not self.members:
            return "队伍是空的。训练师，先去捕获点什么吧。"
        blocks = []
        for m in self.members:
            sp = self.dex.by_id(m.species_id)
            if not sp:
                continue
            qty_note = " ×%d" % m.qty if m.qty > 1 else ""
            blocks.append(sp.card(owned=True, detail=True) + qty_note)
        return "\n\n".join(blocks)

    def species_list(self) -> list[Species]:
        return [self.dex.by_id(m.species_id) for m in self.members]

    # ---------- 属性合计 ----------
    def totals(self) -> dict:
        t = {"kcal": 0, "protein": 0, "fat": 0, "carbs": 0, "sodium": 0, "calcium": 0, "count": 0}
        for m in self.members:
            sp = self.dex.by_id(m.species_id)
            if not sp:
                continue
            for k in ("kcal", "protein", "fat", "carbs", "sodium", "calcium"):
                t[k] += (getattr(sp, k) or 0) * m.qty
            t["count"] += m.qty
        return t

    def totals_report(self) -> str:
        t = self.totals()
        if not t["count"]:
            return "队伍是空的。训练师，先去捕获点什么吧。"
        rows = ["🧾 队伍合计（%d 只）：" % t["count"]]
        label = {"kcal": "能量 kcal", "protein": "蛋白质 g", "fat": "脂肪 g",
                 "carbs": "碳水 g", "sodium": "钠 mg", "calcium": "钙 mg"}
        for k, v in t.items():
            if k == "count":
                continue
            pct = v / DAILY_REF[k] * 100
            bar = "▓" * min(int(pct / 5), 20)
            rows.append("  %-8s %8.0f  %5.1f%%/日  %s" % (label[k], v, pct, bar))
        return "\n".join(rows)

    # ---------- 组合技检测 ----------
    def combo_report(self, now: Optional[datetime] = None) -> list[str]:
        now = now or datetime.now()
        fires: list[str] = []
        sps = []
        for m in self.members:
            sp = self.dex.by_id(m.species_id)
            if sp:
                sps.extend([sp] * m.qty)
        cats = [sp.category for sp in sps]
        names = [sp.name for sp in sps]
        tags = {tg for sp in sps for tg in sp.tags}

        if cats.count("堡堡科") >= 1 and cats.count("薯薯科") >= 1 and any("可乐" in n for n in names):
            fires.append(self.COMBOS["burger_fries_coke"])
        if sum(1 for tg in tags if tg == "辣") >= 2 or sum(1 for n in names if "麦辣" in n) >= 2:
            fires.append(self.COMBOS["double_spicy"])
        if any("巨无霸" in n for n in names):
            fires.append(self.COMBOS["big_mac_index"])
        if any(sp.rarity == "闪光" for sp in sps):
            fires.append(self.COMBOS["shiny_hunt"])
        if cats.count("堡堡科") >= 3:
            fires.append(self.COMBOS["full_burger"])
        if cats.count("甜甜科") >= 1:
            fires.append(self.COMBOS["sweet_ending"])
        if cats.count("晨晨科") >= 1 and now.hour < 11:
            fires.append(self.COMBOS["morning_call"])
        return fires

    def release(self):
        self.members.clear()


# ============================================================
# 存档
# ============================================================

class SaveFile:
    """极简存档：捕获记录 + 队伍。单机游玩，无账号体系。"""

    def __init__(self, path: Path = SAVE_PATH):
        self.path = Path(path)
        self.caught: dict[str, int] = {}      # species_id -> 累计捕获次数
        self.history: list[dict] = []          # 历史队伍快照
        self._load()

    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.caught = data.get("caught", {})
            self.history = data.get("history", [])
        self._seen_achievements = {name for name, desc, cond in self.ACHIEVEMENTS
                                   if _safe_cond(cond, self)}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"caught": self.caught, "history": self.history},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

    def register_catch(self, team: Team):
        for m in team.members:
            self.caught[m.species_id] = self.caught.get(m.species_id, 0) + m.qty

    def snapshot_team(self, team: Team):
        self.history.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "members": [asdict(m) for m in team.members],
            "totals": team.totals(),
        })
        self.history = self.history[-50:]   # 只留最近 50 次

    # ---------- 成就 ----------
    ACHIEVEMENTS = [
        ("初训师", "捕获第一只麦麦", lambda s: sum(s.caught.values()) >= 1),
        ("十连捕获", "累计捕获 10 只", lambda s: sum(s.caught.values()) >= 10),
        ("图鉴三成", "捕获过图鉴 30% 的种类", lambda s: len(s.caught) >= 6),
        ("图鉴过半", "捕获过图鉴 50% 的种类", lambda s: len(s.caught) >= 10),
        ("全图鉴", "捕获过全部种类", lambda s: s._full()),
        ("闪光猎人", "捕获过任一闪光个体", lambda s: s._has_rarity("闪光")),
        ("史诗猎人", "捕获过任一史诗个体", lambda s: s._has_rarity("史诗")),
        ("麦门常客", "累计捕获 50 只", lambda s: sum(s.caught.values()) >= 50),
    ]

    def _full(self) -> bool:
        dex = McDex()
        return len(set(self.caught) & set(dex.species)) >= len(dex.species)

    def _has_rarity(self, rarity: str) -> bool:
        dex = McDex()
        return any(dex.by_id(sid) and dex.by_id(sid).rarity == rarity for sid in self.caught)

    def achievements_report(self) -> str:
        rows = ["🏅 成就："]
        for name, desc, cond in self.ACHIEVEMENTS:
            try:
                got = bool(cond(self))
            except Exception:
                got = False
            rows.append("  %s %-8s %s" % ("🟩" if got else "⬜", name, desc))
        return "\n".join(rows)

    def check_new_achievements(self) -> list[str]:
        """对比快照，返回本次新达成的成就名。调用时机：捕获动作之后。"""
        cur = {name for name, desc, cond in self.ACHIEVEMENTS
               if _safe_cond(cond, self)}
        newly = cur - set(self._seen_achievements)
        self._seen_achievements = cur
        if newly:
            self.save()
        return sorted(newly)


def _safe_cond(cond, save):
    try:
        return bool(cond(save))
    except Exception:
        return False


# ============================================================
# CLI 入口（离线可玩）
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="麦麦图鉴 · 离线模式")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_grid = sub.add_parser("grid", help="查看全图鉴")
    p_grid.add_argument("--save", action="store_true", help="标注已捕获")

    p_find = sub.add_parser("find", help="查询图鉴条目")
    p_find.add_argument("keyword")

    p_team = sub.add_parser("team", help="编排队伍，示例：team MCD003 MCD009 MCD010")
    p_team.add_argument("ids", nargs="+")

    p_ach = sub.add_parser("achieve", help="查看成就")

    p_coupon = sub.add_parser("coupons", help="券感知：查麦麦省当前券池（只读不领）")

    p_shiny = sub.add_parser("shiny", help="闪光预报：官方活动日历中的上新/限定动向")

    args = parser.parse_args()
    dex = McDex()
    save = SaveFile()

    if args.cmd == "coupons":
        try:
            from .live import coupon_radar
        except ImportError:
            from live import coupon_radar
        names = [dex.by_id(sid).name for sid in save.caught
                 if dex.by_id(sid)]
        coupon_radar(names[:12] if names else [])
        return
    if args.cmd == "shiny":
        try:
            from .live import shiny_forecast
        except ImportError:
            from live import shiny_forecast
        shiny_forecast()
        return

    if args.cmd == "grid":
        caught = set(save.caught) if args.save else None
        print(dex.grid(caught))
    elif args.cmd == "find":
        for kw in ([args.keyword] if isinstance(args.keyword, str) else args.keyword):
            hits = dex.search(kw)
            if not hits:
                print("没有找到：%s" % kw)
            for sp in hits:
                print(sp.card(owned=sp.id in save.caught))
                print()
    elif args.cmd == "team":
        t = Team(dex)
        for sid in args.ids:
            print(t.add(sid))
        print()
        print(t.catch_feed())
        print()
        print(t.totals_report())
        for line in t.combo_report():
            print(line)
        save.register_catch(t)
        save.snapshot_team(t)
        save.save()
        print("\n💾 已存档。")
        print("💡 更多实时情报：python3 mcd_dex/dex_engine.py coupons / shiny（需 MCP Token）")
    elif args.cmd == "achieve":
        print(save.achievements_report())


if __name__ == "__main__":
    main()
