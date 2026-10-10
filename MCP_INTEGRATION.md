# MCP 接入说明（McDonald's MCP Integration）

## 1. 使用的 MCP Server

| 项 | 内容 |
|---|---|
| Server | 麦当劳中国官方 MCP Server（远程托管） |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（`streamablehttp`） |
| 鉴权 | 请求头 `Authorization: Bearer <MCP Token>`，Token 于 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 申请 |
| 指南仓库 | [M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server) |

## 2. 实际使用的 Tools

| Tool | 用途 | 在本项目中的角色 |
|---|---|---|
| `list-nutrition-foods` | 餐品营养信息列表 | **核心数据源**。图鉴 160 只物种的营养数值（能量/蛋白质/脂肪/碳水/钠/钙）全部来自该工具返回值，用于计算种族值面板、捕获播报与队伍合计 |
| `available-coupons` | 麦麦省优惠券列表 | **券感知**。`coupons` 命令拉取当前券池，与玩家已捕获物种名做关键词匹配，提示「你图鉴里的这只今天有券」。只读，绝不代领 |
| `campaign-calendar` | 活动日历查询 | **闪光预报**。`shiny` 命令解析官方营销日历，识别「上新/限定/联名/回归」动向，输出限定个体出没预警（如「蓝莓爆爆珠麦旋风上新」） |
| `query-meals` | 查询门店可售餐品 | 规划中：按门店校验「队伍成员当前是否可捕获」 |
| `query-meal-detail` | 餐品详情 | 规划中：补充套餐组成（组合技的官方依据） |

> 当前版本已实际接入三个工具：`list-nutrition-foods`（图鉴数据同步）、`available-coupons`（券感知）、`campaign-calendar`（闪光预报）；其余工具为已规划的能力扩展，见 README「已知边界」。

## 3. 调用流程

```
用户执行 scripts/fetch_dex.py
        │
        ▼
McHttpClient（mcd_dex/mcp_client.py，urllib 零依赖实现）
        │  ① initialize 握手（protocolVersion 2025-03-26，携带 Bearer Token）
        │  ② notifications/initialized 通知
        │  ③ tools/call → list-nutrition-foods
        ▼
解析返回（兼容 JSON 与 SSE 两种返回体）
        │
        ▼
编目规则（scripts/fetch_dex.py）
  · 科属/稀有度/进化线：规则表启发式映射（项目自定义，非官方分类）
  · 营养数值：原样入库，不做任何编造
        │
        ▼
写入 data/dex.json（覆盖前自动备份 .bak）
        │
        ▼
图鉴引擎（dex_engine.py）
  · Species.stats() 由官方营养值线性映射为种族值（映射规则公开）
  · Team.totals() / combo_report() 基于官方数值计算合计与组合技
```

实时情报链路（mcd_dex/live.py，均只读）：

```
dex_engine.py coupons ──► available-coupons ──► parse_coupons() ──► match_coupons(已捕获物种名)
                                                                     │
                                              输出：券池概览 + 与你图鉴相关的券（不代领，领券走官方渠道）

dex_engine.py shiny ───► campaign-calendar ───► parse_campaigns() ──► shiny_report()
                                                                     │
                                              输出：上新/限定/联名/回归 动向预警（✨标记）
```

认证信息处理：Token 一律通过环境变量 `MCD_MCP_TOKEN` 注入，仓库内不出现任何真实凭据（详见参赛声明）。

## 4. 业务价值

1. **给「营养信息」换了一种被消费的方式。** 官方营养数据通常躺在详情页角落，劝退感十足；在麦麦图鉴里，同一份数据变成种族值面板——用户查看属性、对比强度的过程，就是主动阅读营养数据的过程。健康知情权以游戏化形式被自然行使。
2. **给菜单探索提供了新动线。** 图鉴的「未捕获剪影」「进化线」「稀有度」天然制造收集动机，引导用户关注菜单上从未尝试过的品类（如早餐限时品、季节限定品），与 `campaign-calendar`（活动日历）联动后可进一步指向限时尝新。
3. **给点餐决策提供了量化依据。** 队伍合计报表将一整单的营养构成对照每日参考值可视化（百分比条），「这顿吃超了多少」一目了然——先看清，再决定，而非事后焦虑。
4. **可扩展性。** MCP 工具覆盖点餐、领券、积分、活动全链路，图鉴体系（捕获=消费、成就=忠诚度）可自然生长为「会员游戏化」场景：`available-coupons`/`auto-bind-coupons` 可做「图鉴补全礼包」运营位，`query-my-account` 积分可对接「图鉴抽奖」。

## 5. 复现步骤

```bash
export MCD_MCP_TOKEN=你的Token
python3 scripts/fetch_dex.py          # 同步官方营养数据
python3 mcd_dex/dex_engine.py coupons # 券感知（只读）
python3 mcd_dex/dex_engine.py shiny   # 闪光预报
python3 -m mcd_dex.mcp_client         # 自检握手 + 列出全部工具
python3 tests/test_engine.py          # 引擎自测（离线，无需 Token）
```

接口限流提示：官方限 600 次/分钟，本项目的同步脚本为一次性全量拉取，单次运行 3 个请求（initialize + initialized + tools/call），远低于限额。
