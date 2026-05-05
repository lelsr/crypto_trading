# 加密货币合约趋势及时捕捉系统 v0.3 方案

## 1. 目标与边界

v0.3 目标是从零到一开发一个本地 Mac 可运行的加密货币 USDT 永续合约信号系统。

核心能力：
- 默认每 38 分钟循环扫描一次，可配置。
- 只处理 USDT 永续合约。
- 第一阶段只做做多入场机会判断、飞书提醒、网页看板、信号生命周期复盘。
- 不做实盘自动下单，但预留 `future_order_adapter`。
- 不计算杠杆，只输出推荐入场区间、技术止损位、止损依据、信号理由、后续盈亏追踪、人工复盘归档。
- 适配本地 Mac + 美国网络或美国节点代理环境。

明确不做：
- 不跨交易所合并 K线。
- 不拉取全市场全周期 K线。
- 不把 V1 做成复杂多 Agent 系统。
- 不在 V1 接入 TimesFM。
- 不启用真实下单。

## 2. 参考思想与架构原则

参考开源项目思想：
- NautilusTrader：借鉴事件驱动、backtest/live/sandbox 分层、数据模型标准化；V1 不作为主框架。
- CCXT：作为备用统一交易所适配层，优先官方 REST API，CCXT 只做 fallback 或快速扩展。
- TimesFM：V1 不接入，预留时间序列预测接口。
- AI-Trader / Vibe-Trading：借鉴解释、复盘、研究报告思想，不做复杂多 Agent。

核心原则：
- K线只服务于入场结构与止损位置。
- 活跃度排序使用多交易所 ticker。
- 技术指标只使用 `primary_exchange` 的 K线。
- 交易所接口失败要被隔离，不能拖垮整轮扫描。
- 所有网络请求必须有 timeout、retry、rate limit、fallback cache、error logging、`source_status`、`latency_ms`。

## 3. 数据流

完整扫描流程：

```text
读取配置
→ 各交易所抓 USDT 永续 24h ticker
→ 各交易所内部按 24h quote volume 取 preselect_top_n
→ 合并候选池
→ 统一 symbol
→ 补市值
→ 按用户自定义市值范围过滤
→ 在市值过滤后的池子里重新按活跃度排序
→ 取 final_top_m
→ 为每个 symbol 选择 primary_exchange
→ 只对 final_top_m 拉 primary_exchange 的 15m / 1h / 4h K线
→ 计算技术指标
→ 生成做多信号
→ 写入 SQLite
→ 飞书提醒 + 看板展示 + 每轮报告
→ 生命周期追踪 + 人工复盘归档
```

关键顺序：
- `preselect_top_n_per_exchange` 是性能裁剪，不是最终策略过滤。
- 市值过滤必须发生在合并候选池之后、final Top M 之前。
- 市值过滤后必须重新排序，再取 `final_top_m_after_market_cap`。

## 4. 目录结构

后续实现时创建：

```text
crypto-perp-signal/
├── app/
│   ├── dashboard.py
│   ├── scheduler.py
│   └── feishu_notify.py
├── config/
│   ├── settings.yaml
│   └── strategy_profiles.yaml
├── data/
│   ├── cache/
│   ├── reports/
│   └── signals.db
├── exchanges/
│   ├── base.py
│   ├── binance_futures.py
│   ├── bybit.py
│   ├── okx.py
│   ├── bitget.py
│   ├── kraken.py
│   ├── coinbase.py
│   └── coingecko.py
├── market/
│   ├── symbol_mapper.py
│   ├── activity_ranker.py
│   ├── market_cap_filter.py
│   └── primary_exchange_selector.py
├── strategy/
│   ├── indicators.py
│   ├── support_resistance.py
│   ├── long_signal_v1.py
│   └── scoring.py
├── lifecycle/
│   ├── signal_store.py
│   ├── signal_tracker.py
│   └── manual_review.py
├── scripts/
│   ├── run_cycle.py
│   ├── run_dashboard.py
│   └── init_db.py
├── tests/
│   ├── test_activity_ranker.py
│   ├── test_market_cap_filter.py
│   ├── test_primary_exchange_selector.py
│   ├── test_indicators.py
│   └── test_long_signal_v1.py
├── docs/
│   ├── open_source_review.md
│   ├── data_source_design.md
│   ├── kline_design.md
│   └── plan_v0.3.md
├── .env.example
├── requirements.txt
└── README.md
```

## 5. 默认配置

`config/settings.yaml` 默认值：

```yaml
runtime:
  loop_minutes: 38
  local_mode: true

universe:
  quote_asset: USDT
  contract_type: perpetual
  preselect_top_n_per_exchange: 300
  final_top_m_after_market_cap: 80

market_cap_filter:
  enabled: true
  min_market_cap: 50000000
  max_market_cap: 5000000000
  keep_unknown_market_cap: true

signals:
  push_threshold: 0
  min_score_to_display: 0
  enable_long_signal_v1: true

klines:
  timeframes: ["15m", "1h", "4h"]
  limit: 200

risk:
  enable_leverage: false
  stop_loss_mode: technical_only

feishu:
  enabled: true
```

`.env.example` 默认变量：

```text
FEISHU_WEBHOOK_URL=
ENABLE_FEISHU=true
SIGNAL_PUSH_THRESHOLD=0
HTTP_PROXY=
HTTPS_PROXY=
```

## 6. 数据模型

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ExchangeTicker:
    exchange: str
    raw_symbol: str
    unified_symbol: str
    quote_volume_24h_usd: float | None
    base_volume_24h: float | None
    last_price: float | None
    price_change_pct_24h: float | None
    source_status: str
    latency_ms: int | None
    updated_at: datetime

@dataclass
class UnifiedActivityCandidate:
    symbol: str
    exchanges: list[str]
    primary_exchange: str
    activity_score: float
    global_quote_volume_24h_usd: float | None
    market_cap_usd: float | None
    market_cap_status: str
    source_status: str

@dataclass
class KlineBar:
    exchange: str
    symbol: str
    timeframe: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class LongSignal:
    symbol: str
    primary_exchange: str
    score: float
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    stop_reason: str
    timeframe_alignment: dict
    reasons: list[str]
    invalidation: str
    created_at: datetime

@dataclass
class SignalLifecycleRecord:
    signal_id: str
    symbol: str
    primary_exchange: str
    status: str
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    stop_touched: bool
    target_touched: bool
    duration_minutes: int | None
    manual_verdict: str | None
    manual_notes: str | None
    manual_tags: list[str]
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
```

## 7. 交易所与数据源设计

优先数据源：
- A 类，美国网络友好优先：Kraken、Coinbase。
- B 类，全球主流高流动性行情源：Binance Futures、OKX Swap、Bybit、Bitget。
- C 类，补充层：CoinGecko、CCXT fallback。

每个交易所 adapter 必须实现：

```python
fetch_usdt_perp_tickers()
fetch_klines(symbol, timeframe, limit)
fetch_funding_rate(symbol)        # optional
fetch_open_interest(symbol)       # optional
health_check()
```

V1 实现顺序：
- `exchanges/base.py` 先定义通用接口、请求包装、错误模型、缓存策略。
- Binance Futures、Bybit、OKX Swap、Bitget 实现真实 ticker 和 kline。
- Kraken、Coinbase 先保留 adapter stub，结构完整，`health_check()` 可返回 capability 状态。
- CoinGecko 用于批量补市值。

适配器要求：
- 官方 REST API 优先。
- CCXT 只做 fallback。
- 任何 adapter 报错都必须被转换为失败状态和日志，不得中断整轮扫描。

## 8. 活跃度排序

不同交易所 volume 字段口径不同，禁止简单无脑相加。

活跃度评分：

```text
activity_score =
exchange_rank_score * 0.50
+ normalized_quote_volume_score * 0.25
+ exchange_presence_score * 0.15
+ data_confidence_score * 0.10
```

评分解释：
- `exchange_rank_score`：每个交易所内部按 24h quote volume 排名，排名越靠前分越高。
- `normalized_quote_volume_score`：尽量统一为 USD/USDT 计价成交额，但不能完全依赖。
- `exchange_presence_score`：同一个 symbol 出现在多个大交易所，加分。
- `data_confidence_score`：延迟低、字段完整、近期接口稳定，加分。

实现要点：
- 每交易所先取 `preselect_top_n_per_exchange`。
- symbol mapper 负责统一 BTCUSDT、BTC-USDT-SWAP、BTCUSDTM 等格式。
- 合并候选时保留原始交易所列表和各源状态。
- unknown volume 允许进入候选，但评分降权。

## 9. 市值过滤

默认配置：

```yaml
market_cap_filter:
  enabled: true
  min_market_cap: 50000000
  max_market_cap: 5000000000
  keep_unknown_market_cap: true
```

规则：
- 先做交易所内部 Top N 预裁剪。
- 合并 symbol 后用 CoinGecko 补市值。
- 再执行用户自定义市值范围过滤。
- unknown market cap 可保留，但降低评分。
- 市值过滤后的候选池必须重新按活跃度排序，再取 final Top M。

## 10. Primary Exchange 选择

每个 symbol 必须独立选择 `primary_exchange`，禁止简单粗暴永久固定 Binance。

完整评分目标：

```text
primary_score =
24h_quote_volume_rank_score * 0.45
+ data_quality_score * 0.20
+ spread_quality_score * 0.15
+ kline_availability_score * 0.10
+ exchange_stability_score * 0.10
```

V1 简化评分：

```text
primary_score =
24h_quote_volume_rank_score * 0.60
+ kline_availability_score * 0.20
+ exchange_stability_score * 0.20
```

要求：
- K线技术分析只能使用 `primary_exchange`。
- 其他交易所 K线只做辅助验证，不参与主技术指标计算。
- `primary_exchange_selector.py` 必须独立可测试。

## 11. K线与技术指标

只对 final Top M 拉 K线。

周期用途：
- 15m：具体入场结构。
- 1h：日内趋势确认。
- 4h：大周期支撑与背景。

技术指标：
- EMA20。
- EMA60。
- MACD。
- Bollinger Bands。
- volume moving average。
- recent swing low。
- support level。

关键限制：
- 不拉取全市场 K线。
- 不跨交易所合并 K线。
- `KlineBar.exchange` 必须等于该 symbol 的 `primary_exchange`。

## 12. 做多信号 V1

4h 判断：
- 价格不处于明显瀑布下跌。
- close 高于 EMA60，或接近关键支撑后企稳。
- 找到最近有效支撑。

1h 判断：
- close 高于 EMA20，或重新站回 EMA20。
- MACD 柱体转强或金叉。
- 成交量不萎缩。

15m 判断：
- 回踩 EMA20、布林中轨或结构支撑后反弹。
- close 重新站上关键短线位。
- 不追过度远离 EMA20 的价格。

止损位置优先级：
1. 4h 关键支撑下方。
2. 1h 最近 swing low 下方。
3. 15m 布林带下轨下方。
4. 15m/1h EMA60 下方。

输出要求：
- 推荐入场区间。
- 技术止损位。
- 止损依据。
- 15m、1h、4h 判断。
- 信号理由。
- 失效条件。

## 13. 信号生命周期

每个信号必须进入 SQLite。

状态：
- `created`
- `notified`
- `monitoring`
- `tp1_hit`
- `stopped`
- `expired`
- `manual_reviewed`

必须记录：
- 最大浮盈。
- 最大浮亏。
- 是否触及止损。
- 是否达到目标位。
- 信号持续时间。
- 人工复盘结果。
- 人工备注。
- 人工标签。

人工复盘字段：

```python
manual_verdict: str  # good / bad / neutral / missed / false_breakout
manual_notes: str
manual_tags: list[str]
reviewed_at: datetime
```

## 14. 飞书提醒

使用飞书群机器人 webhook。

环境变量：

```text
FEISHU_WEBHOOK_URL=
ENABLE_FEISHU=true
SIGNAL_PUSH_THRESHOLD=0
```

规则：
- V1 只要有 signal 且达到阈值就推送。
- webhook 为空时安全跳过，并记录 skip 原因。
- 推送失败不得导致整轮扫描失败。

推送内容必须包括：
- symbol。
- primary_exchange。
- score。
- entry zone。
- stop loss。
- stop reason。
- 15m / 1h / 4h 判断。
- reasons。
- dashboard 本地地址。

## 15. Streamlit 网页看板

本地启动：

```bash
streamlit run app/dashboard.py
```

页面：
- 当前信号。
- 活跃合约排行。
- 市值过滤结果。
- 信号生命周期。
- 人工复盘。
- 数据源健康状态。
- 策略表现统计。

要求：
- 看板从 SQLite 和每轮 report 读取数据。
- 人工复盘入口可以更新信号状态和复盘字段。
- 数据源健康状态展示每个交易所的 `source_status`、`latency_ms`、最近错误。

## 16. 循环调度

运行方式：
- 手动运行一次：`python scripts/run_cycle.py --once`。
- 持续循环：`python scripts/run_cycle.py --loop`。
- 默认循环间隔：38 分钟。

每轮 report：
- 输出到 `data/reports/`。
- 文件名包含 UTC 时间戳。
- 内容包含候选池摘要、市值过滤摘要、final Top M、信号、数据源健康、错误摘要。

调度要求：
- 单轮异常要被捕获并写入 report。
- 下一轮继续运行。
- SIGINT 时优雅退出。

## 17. 开发顺序

必须按顺序开发：
1. Phase 1：项目骨架。
2. Phase 2：数据模型。
3. Phase 3：交易所适配器。
4. Phase 4：活跃度排序。
5. Phase 5：市值过滤。
6. Phase 6：主交易所选择。
7. Phase 7：K线与指标。
8. Phase 8：做多信号。
9. Phase 9：生命周期。
10. Phase 10：飞书 + 看板。
11. Phase 11：循环调度。

## 18. 测试计划

单元测试：
- `test_activity_ranker.py`：交易所内部 Top N、symbol 合并、多交易所出现加分、缺失字段降权。
- `test_market_cap_filter.py`：市值范围、unknown 保留、unknown 排除、过滤后重排。
- `test_primary_exchange_selector.py`：成交量排名、K线可用性、交易所稳定性、禁止固定 Binance。
- `test_indicators.py`：EMA、MACD、Bollinger Bands、长度不足。
- `test_long_signal_v1.py`：多周期对齐、止损优先级、无信号场景。

集成测试：
- mock 单交易所失败，整轮扫描继续。
- mock Feishu webhook 为空，推送安全跳过。
- mock final Top M，只拉 primary exchange K线。
- SQLite 写入、状态更新、人工复盘保存。

## 19. 官方资料依据

- Binance USD-M Futures Kline/Candlestick Data: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data
- Binance USD-M Futures 24hr Ticker Price Change Statistics: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics
- Bybit V5 Get Kline: https://bybit-exchange.github.io/docs/v5/market/kline
- OKX API v5 Docs: https://www.okx.com/docs-v5/en/
- Bitget Get Kline/Candlestick Data: https://www.bitget.com/api-doc/uta/public/Get-Candle-Data
- Kraken Futures Market Candles: https://docs.kraken.com/api/docs/futures-api/charts/candles/
- Coinbase Advanced Trade Perpetual Futures: https://docs.cdp.coinbase.com/coinbase-business/advanced-trade-apis/guides/perpetual
- CoinGecko Coins Markets API: https://docs.coingecko.com/reference/coins-markets

## 20. 最终自检清单

- [ ] 是否避免了全市场 K线拉取？
- [ ] 是否没有跨交易所合并 K线？
- [ ] 是否支持每交易所 Top N 预裁剪？
- [ ] 是否在市值过滤后重新排序？
- [ ] 是否支持 unknown market cap 保留？
- [ ] 是否单个交易所失败不会导致整轮失败？
- [ ] 是否记录了 source_status 和 latency_ms？
- [ ] 是否支持 Feishu webhook 为空时安全跳过？
- [ ] 是否支持本地 Streamlit 看板？
- [ ] 是否 SQLite 记录了完整信号生命周期？
- [ ] 是否人工复盘可以保存？
- [ ] 是否 V1 完全不计算杠杆？
- [ ] 是否止损来自技术结构？
- [ ] 是否 primary_exchange 逻辑独立可测试？
- [ ] 是否每个核心模块有单元测试？
- [ ] 是否 README 写清楚 Mac 本地启动步骤？
- [ ] 是否 .env.local 不会被提交？
- [ ] 是否 API 请求有 timeout/retry/cache？
- [ ] 是否每轮循环生成可读报告？
- [ ] 是否未来 order_adapter 只是预留，未启用实盘交易？
