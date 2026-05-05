# Crypto Perp Signal

本项目是本地 Mac 可运行的加密货币 USDT 永续合约趋势及时捕捉系统。V1 只做做多入场机会判断、飞书提醒、Streamlit 看板、信号生命周期复盘和人工复盘，不做实盘自动下单，不计算杠杆。

## 当前状态

Phase 0 - Phase 12 已完成，当前进入 V1 acceptance 与首次提交准备。

当前全量测试：

```bash
pytest
```

最近结果：`106 passed`。

## 当前完成能力

- 仓库规范、阶段计划和架构文档。
- 分层目录结构：domain、infrastructure、application、app、lifecycle、scripts、tests。
- Domain models 和 scan events。
- SQLite schema、repository、cache store、HTTP client。
- Exchange adapter 基础设施和部分行情源 adapter。
- 多交易所 24h ticker 活跃度排序。
- CoinGecko 市值补充与市值过滤。
- Primary exchange selection。
- Kline fetch policy：只对 Final Top M、只拉 primary_exchange、不跨交易所合并。
- EMA20、EMA60、MACD、Bollinger Bands、volume MA。
- Support / resistance 和 structure analyzer。
- `long_signal_v1`：结构锚定 entry zone、技术止损、RR 过滤、gating、cooldown、signal_level。
- Signal lifecycle：created、notified、monitoring、tp1_hit、stopped、expired、manual_reviewed。
- MFE / MAE、TP1 / TP2 / TP3 观察值。
- Manual review 和 strategy feedback 汇总。
- Feishu webhook notifier：A/B 推送，C 仅看板展示。
- 本地 Streamlit dashboard。
- Scan orchestrator、手动运行、循环调度、markdown report。

## 架构约束

后续代码必须遵守仓库根目录中的：
- `AGENTS.md`
- `PLANS.md`
- `docs/architecture_review.md`
- `docs/plan_v0.3.md`
- `docs/kline_design.md`
- `docs/long_signal_v1_design.md`

核心约束：
- 活跃度排序使用多交易所 ticker。
- K线只在 Final Top M 之后拉取。
- K线只拉每个 symbol 的 `primary_exchange`。
- 禁止跨交易所合并 K线计算主技术指标。
- 禁止先全市场拉 K线。
- 禁止实盘下单。
- 禁止计算杠杆。
- 禁止写成单文件脚本。
- 必须按 Interface、Application、Domain、Infrastructure 四层组织。

## 本地安装

```bash
cd /Users/claw/Documents/Cryp_trading/crypto-perp-signal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置

```bash
cp .env.example .env.local
```

`.env.local` 只保存在本地，不提交 git。

飞书配置：

```bash
ENABLE_FEISHU=true
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook
SIGNAL_PUSH_THRESHOLD=0
```

禁用飞书：

```bash
ENABLE_FEISHU=false
FEISHU_WEBHOOK_URL=
```

webhook 为空或 `ENABLE_FEISHU=false` 时会安全跳过通知。A/B `signal_level` 推送，C 级只在看板展示。

## 初始化数据库

```bash
python scripts/init_db.py
```

可指定数据库路径：

```bash
python scripts/init_db.py --db-path data/signals.db
```

## 手动运行一次扫描

```bash
python scripts/run_cycle.py --once
```

可指定配置文件：

```bash
python scripts/run_cycle.py --once --config config/settings.yaml
```

说明：当前 `run_cycle.py` 已提供 CLI 和调度入口；真实 adapter 装配仍需在后续接入运行环境时配置，测试使用 fake adapters 覆盖编排行为。

## 循环扫描

默认循环间隔为 38 分钟：

```bash
python scripts/run_cycle.py --loop
```

指定间隔：

```bash
python scripts/run_cycle.py --loop --loop-minutes 38
```

Scheduler 支持优雅停止，不允许后台失控运行。

## 启动看板

```bash
streamlit run app/dashboard.py
```

或通过脚本入口：

```bash
python scripts/run_dashboard.py
```

看板页面包含：
- Overview
- Current Signals
- Signal Lifecycle
- Manual Review
- Exchange Health
- Strategy Feedback

## 报告

每轮扫描会生成 markdown report，包含：
- `scan_id`
- 候选数量
- 信号数量
- 失败交易所
- 跳过 symbol
- 推送结果

默认报告目录：`data/reports/`。

## V1 禁止事项

- 不实盘下单。
- 不计算杠杆。
- 不实现 order adapter。
- 不跨交易所合并 K线。
- 不绕过 `primary_exchange`。
- 不先全市场拉 K线。
- 不把 API 请求、指标计算、飞书推送、数据库写入混在一个文件里。
- 不把真实 webhook、token、密钥写入代码或 commit。
