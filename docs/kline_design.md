# Kline Design

本文档是 Phase 8 前的 K线设计确认，只定义策略、边界和测试要求，不包含代码实现。

说明：当前仓库不存在 `docs/plan_v1_architecture.md`。本设计基于 `AGENTS.md`、`PLANS.md`、`docs/architecture_review.md`、`docs/plan_v0.3.md` 和当前已实现的 Phase 1-7 约束。

## 1. K线拉取策略

K线只服务于入场结构、趋势背景和止损位置，不参与市场活跃度排序。

拉取顺序必须是：

```text
Exchange Ticker
→ Exchange Local Top N
→ Unified Candidate Pool
→ Market Cap Enrichment
→ Market Cap Filter
→ Activity Re-rank
→ Final Top M
→ Primary Exchange Selection
→ Kline Fetch Plan
→ Kline Fetch
→ Indicator Calculation
```

避免 API 爆炸的规则：
- 只对 Final Top M 拉 K线，默认最多 80 个 symbol。
- 每个 symbol 只拉一个 `primary_exchange`。
- 默认只拉 3 个周期：15m、1h、4h。
- 每周期默认 `limit=200`。
- 最大请求预算约为 `80 * 3 = 240` 个 K线请求，不允许按交易所全市场预拉。
- K线请求必须按 exchange 分组，并使用 adapter 的 timeout、retry、rate limit、fallback cache。
- 如果 symbol 没有 `primary_exchange`，直接跳过 K线计划。
- 如果 `primary_exchange` 不支持该 symbol 的 K线，直接跳过该 symbol，不从其他交易所混合补齐。

Kline Fetch Plan 应先生成计划，再由 infrastructure adapter 执行。计划字段建议包含：
- `symbol`
- `primary_exchange`
- `timeframe`
- `limit`
- `cache_key`
- `required`
- `reason`

## 2. 多周期结构设计

15m / 1h / 4h 的职责必须分离。

多周期必须基于同一时间点，禁止不同时间点混用。

时间对齐规则：
- 使用最近一根已收盘 15m K线作为 `analysis_anchor_time`。
- 1h K线必须选择覆盖该 `analysis_anchor_time` 且已经收盘的那根 K线。
- 4h K线必须选择覆盖该 `analysis_anchor_time` 且已经收盘的那根 K线。
- 如果对应 1h 或 4h K线尚未收盘，则回退到该周期最近一根已收盘 K线，并记录 `alignment_status="lagged_closed_bar"`。
- 如果 15m、1h、4h 的时间对齐关系无法确定，必须跳过该 symbol 的完整信号判断。
- 所有 `IndicatorSnapshot` 必须记录同一个 `analysis_anchor_time` 或可追溯到同一个 anchor。

示例：
- 当前时间是 10:37，最近已收盘 15m 是 10:30。
- 1h 使用 10:00-11:00 这根时，必须确认它已经收盘；如果未收盘，则使用 09:00-10:00 并标记 lagged。
- 4h 同理，只能使用已收盘且与 anchor 可解释对齐的 K线。

4h：大周期背景
- 判断是否处于明显瀑布下跌。
- 判断价格是否高于 EMA60，或接近关键支撑后企稳。
- 识别最近有效大周期支撑。
- 主要输出：`higher_context`、`major_support`、`trend_risk`。

1h：日内趋势确认
- 判断 close 是否高于 EMA20，或重新站回 EMA20。
- 判断 MACD 柱体是否转强或金叉。
- 判断成交量是否明显萎缩。
- 主要输出：`intraday_trend`、`momentum_state`、`volume_state`。

15m：入场结构
- 判断是否回踩 EMA20、布林中轨或结构支撑后反弹。
- 判断 close 是否重新站上短线关键位。
- 判断是否过度远离 EMA20，避免追高。
- 主要输出：`entry_structure`、`entry_zone`、`short_term_invalid_level`。

多周期对齐原则：
- 4h 提供背景和主要支撑。
- 1h 提供趋势确认。
- 15m 提供具体入场结构。
- 任一周期缺失时不得伪造判断，必须输出明确的 missing reason。
- 任一周期使用了不同分析时间点，必须拒绝信号生成。

## 3. 指标计算方式

指标计算只使用 `primary_exchange` 的 K线。

输入要求：
- 每个 `KlineBar.exchange` 必须等于对应 symbol 的 `primary_exchange`。
- 每个周期必须按 `open_time` 升序计算。
- 数据长度不足时返回 `None` 或明确的 insufficient data 状态，不补零、不插值。

EMA：
- EMA20 和 EMA60 使用标准指数移动平均。
- smoothing factor：`alpha = 2 / (period + 1)`。
- 初始值建议使用前 `period` 根 close 的 SMA。
- 如果 K线数量小于 period，输出 `None`。

MACD：
- fast EMA：12。
- slow EMA：26。
- signal EMA：9。
- `macd = ema_fast - ema_slow`。
- `macd_signal = EMA(macd, 9)`。
- `macd_histogram = macd - macd_signal`。
- 如果有效长度不足，输出 `None`。

Bollinger Bands：
- period：20。
- stddev multiplier：2。
- `middle = SMA(close, 20)`。
- `upper = middle + 2 * stddev(close, 20)`。
- `lower = middle - 2 * stddev(close, 20)`。
- 如果 K线数量小于 20，输出 `None`。

Volume MA：
- 默认 period：20。
- 使用 volume 的 SMA。
- 如果数量不足，输出 `None`。

输出建议使用 `IndicatorSnapshot`：
- `exchange`
- `symbol`
- `timeframe`
- `calculated_at`
- `close`
- `ema20`
- `ema60`
- `macd`
- `macd_signal`
- `macd_histogram`
- `bollinger_upper`
- `bollinger_middle`
- `bollinger_lower`
- `volume_ma`
- `recent_swing_low`
- `support_level`

## 4. 支撑位识别算法

支撑位算法必须可实现、可测试、可解释，V1 不使用复杂机器学习。

Recent Swing Low：
- 对每根 K线 `i`，使用左右窗口识别局部低点。
- 默认窗口：left=2、right=2。
- 条件：`low[i] <= low[i-left:i]` 且 `low[i] <= low[i+1:i+right+1]`。
- 排除最近尚未确认的右侧不足窗口 K线。
- 输出最近一个有效 swing low。

Support Level：
- 先提取最近 N 根 K线的 swing lows，默认 N=120。
- 将价格相近的 swing lows 聚类，默认容忍度 `tolerance_pct=0.5%`。
- 每个聚类计算：
  - touch_count：触及次数。
  - recency_score：越近越高。
  - volume_score：触及时成交量越高越高。
- 支撑强度建议：

```text
support_score =
touch_count_score * 0.50
+ recency_score * 0.30
+ volume_score * 0.20
```

- 选择当前价格下方且距离最近的高分支撑。
- 如果没有当前价格下方支撑，可返回最近 swing low 作为弱支撑，并标记 `support_status="weak"`。

实现边界：
- 不跨交易所合并 swing lows。
- 不使用未来 K线确认当前信号。
- 数据不足时返回 missing support，不强行生成。

## 5. 止损生成规则

止损必须来自技术结构，且必须可解释。V1 不计算杠杆，不按固定亏损比例生成止损。

止损优先级：
1. 4h 关键支撑下方。
2. 1h 最近 swing low 下方。
3. 15m Bollinger lower 下方。
4. 15m 或 1h EMA60 下方。

缓冲规则：
- 默认 stop buffer 可使用 `0.2% - 0.5%`，后续配置化。
- 对高波动币种可使用 `max(固定百分比, recent ATR fraction)`，但 V1 可以先只使用固定百分比。
- stop_loss 必须小于 entry_zone_low，否则信号无效。

解释字段：
- `stop_loss`
- `stop_reason`
- `stop_source_timeframe`
- `stop_source_price`
- `buffer_pct`
- `invalidation`

示例：
- `stop_reason="4h support 98.20 minus 0.3% buffer"`
- `invalidation="15m close below stop_loss or 1h close below 4h support"`

## 6. 数据缓存策略

缓存目标：
- 降低重复请求。
- 支持交易所临时失败时 fallback。
- 不伪装实时数据。

缓存 key：

```text
kline:{exchange}:{symbol}:{timeframe}:{limit}
```

缓存内容：
- 原始 adapter response。
- 标准化 `KlineBar` 列表。
- `source_status`
- `latency_ms`
- `fetched_at`

TTL 建议：
- 15m：3-5 分钟。
- 1h：10-15 分钟。
- 4h：30-60 分钟。

fallback cache 规则：
- 实时请求失败时可读取未过期缓存。
- 使用缓存必须标记 `source_status="stale_cache"`。
- stale cache 可用于展示和保守分析，但信号理由必须注明使用缓存。
- 缓存过期或不存在时，该周期标记失败，不从其他交易所拼接替代。

## 7. 失败降级策略

单周期失败：
- 如果 15m 失败：不能生成入场结构，symbol 不生成新入场信号。
- 如果 1h 失败：不能确认日内趋势，symbol 不生成新入场信号，除非后续明确允许 degraded mode。
- 如果 4h 失败：不能确认大周期背景和关键支撑，symbol 不生成新入场信号。

部分 K线不足：
- 返回 `insufficient_data`。
- 指标字段为 `None`。
- 不补零、不插值、不用其他交易所混合补齐。

primary_exchange 请求失败：
- 记录 `KlinesFetched` 事件，状态为 `failed` 或 `partial`。
- 记录 exchange health。
- 如果有合法 fallback cache，可使用缓存并标记 stale。
- 如果无缓存，该 symbol 跳过指标计算。

多 symbol 部分失败：
- 允许 partial success。
- 失败 symbol 不影响其他 symbol。
- 本轮 report 必须记录失败 symbol、exchange、timeframe、错误原因。

## 8. 性能预算

默认预算：
- 单轮扫描目标耗时：不超过 3 分钟。
- 默认循环间隔：38 分钟。
- Final Top M：80。
- 周期：15m / 1h / 4h。
- 每周期 limit：200。
- 最大 K线请求：约 240。

执行建议：
- 按 `primary_exchange` 分组请求。
- 每个 exchange 内部限速。
- 交易所之间可有限并发。
- 单请求必须有 timeout。
- 每个 exchange 的失败不阻塞其他 exchange。
- 对已经有新鲜缓存的 K线，可跳过实时请求或降低请求优先级。

预算失败处理：
- 超过单轮剩余时间预算时停止新增 K线请求。
- 已完成的 symbol 可继续后续计算。
- 未完成的 symbol 标记 skipped，并写入 report。

## 9. 测试策略

Kline Policy 测试：
- 只为 Final Top M 生成 K线计划。
- 无 `primary_exchange` 的 candidate 被跳过。
- 每个 symbol 只使用自己的 `primary_exchange`。
- 非 primary exchange K线输入被拒绝。
- 禁止跨交易所合并。
- 15m、1h、4h 必须基于同一个 `analysis_anchor_time`。
- 不同时间点混用必须被拒绝。

指标测试：
- EMA20 / EMA60 正常计算。
- MACD 正常计算。
- Bollinger Bands 正常计算。
- 数据长度不足返回 `None`。
- 输入 K线乱序时先排序或明确拒绝，行为必须固定。

支撑位测试：
- 能识别 recent swing low。
- 能聚类相近 swing lows。
- 当前价格下方支撑优先。
- 无有效支撑返回 weak/missing 状态。

止损测试：
- 优先使用 4h 支撑下方。
- 4h 不可用时使用 1h swing low。
- 再退到 15m Bollinger lower。
- 再退到 EMA60。
- stop_loss 不得高于 entry_zone_low。
- stop_reason 必须可读。

失败降级测试：
- 15m / 1h / 4h 任一周期失败时，不生成完整新信号。
- fallback cache 使用时标记 stale。
- 单 symbol 失败不影响其他 symbol。

## 10. 禁止行为

- 禁止先全市场拉 K线。
- 禁止在活跃度排序阶段拉 K线。
- 禁止跨交易所合并 K线计算 EMA、MACD、Bollinger Bands、支撑位或止损。
- 禁止用非 `primary_exchange` 的 K线替代主技术指标输入。
- 禁止在没有 Final Top M 的情况下拉 K线。
- 禁止没有 `primary_exchange` 时拉 K线。
- 禁止 K线失败时静默跳过并继续假装数据完整。
- 禁止用补零、插值、复制上一根等方式伪造 K线或指标。
- 禁止 V1 使用杠杆或实盘下单。
- 禁止在 K线模块中写飞书、Streamlit、数据库业务流程或交易所活跃度排序逻辑。
- 禁止把 K线拉取、指标计算、信号策略、通知、持久化混成一个文件。
