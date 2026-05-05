# Long Signal V1 Design

本文档定义 Phase 9 前的 `long_signal_v1` 信号设计，仅描述规则，不包含代码实现。设计基于 `docs/kline_design.md`、`docs/architecture_review.md`、当前 domain 模型，以及 Phase 8 已实现的 `kline_policy`、`indicators`、`support_resistance`、`structure_analyzer`。

## 1. 目标与边界

`long_signal_v1` 只生成 USDT 永续合约做多入场机会，输出 `LongSignal`，不计算杠杆、不下单、不推送、不写数据库。

输入必须来自同一个 `primary_exchange`：
- `StructureAnalysis`
- 15m / 1h / 4h 的 `IndicatorSnapshot`
- 15m / 1h / 4h 的支撑位、swing low、Bollinger Bands、EMA60
- 同一个 `analysis_anchor_time` 下的已收盘 K线

硬约束：
- 禁止跨交易所合并 K线。
- 禁止使用未收盘 K线。
- 禁止在 Final Top M 之前拉 K线。
- `trend_broken=True`、`high_volatility=True`、`chase_risk=True`、`support_too_close=True` 时不得生成做多信号。
- `4h_bearish_gate=True` 时不得生成做多信号。
- 预期风险收益比 `rr < 2.0` 时不得生成做多信号。
- 同一 `symbol` 在 cooldown 窗口内不得重复生成同类做多信号。

## 2. 信号触发条件

信号触发必须同时满足 4h、1h、15m 条件，并通过风险过滤。所有条件都使用已收盘 K线和当前 `StructureAnalysis.indicators`。

### 4h 条件

4h 负责大周期背景和主要支撑，满分 25 分。

必须满足以下任一背景条件：
- `4h.close >= 4h.ema60`。
- 或 `4h.support_level is not None` 且 `(4h.close - 4h.support_level) / 4h.close <= 0.03`。

必须满足以下风险条件：
- `4h.ema60 is not None`。
- `4h.support_level is not None`。
- `4h.close > 4h.support_level`。
- 如果 `4h.close < 4h.ema60`，则 `4h.close` 距离 `4h.support_level` 不得超过 3%，否则不视为支撑企稳。

4h 分项量化：
- `close >= ema60`：10 分。
- `support_level` 存在且在当前 close 下方：8 分。
- `(close - support_level) / close <= 0.03`：4 分。
- `4h.close >= 4h.ema20`：3 分。

### 1h 条件

1h 负责日内趋势和动能确认，满分 25 分。

必须满足：
- `1h.ema20 is not None` 且 `1h.ema60 is not None`。
- `1h.macd is not None`、`1h.macd_signal is not None`、`1h.macd_histogram is not None`。
- `1h.volume_ma is not None`。
- `1h.close >= 1h.ema20` 或 `1h.close >= 1h.ema60`。
- `trend_broken=False`。

1h 分项量化：
- `1h.close >= 1h.ema20`：8 分。
- `1h.ema20 >= 1h.ema60`：6 分。
- `1h.macd_histogram > 0`：5 分。
- `1h.macd >= 1h.macd_signal`：3 分。
- 最近已收盘 1h K线 `volume >= 0.8 * volume_ma`：3 分。

### 15m 条件

15m 负责入场结构，满分 25 分。

必须满足：
- `15m.ema20 is not None`。
- `15m.bollinger_middle is not None` 且 `15m.bollinger_lower is not None`。
- `15m.support_level is not None`。
- `15m.close >= 15m.ema20` 或 `15m.close >= 15m.bollinger_middle`。
- `(15m.close - 15m.support_level) / 15m.close >= 0.005`。
- `(15m.close - 15m.ema20) / 15m.ema20 <= 0.02`。
- `high_volatility=False`。

15m 分项量化：
- `15m.close >= 15m.ema20`：8 分。
- `15m.close >= 15m.bollinger_middle`：5 分。
- `15m.support_level` 存在且在 close 下方：5 分。
- `0.005 <= (close - support_level) / close <= 0.03`：4 分。
- `abs(close - ema20) / ema20 <= 0.01`：3 分。

## 3. Entry Zone

入场必须是 `entry_zone`，不得使用单点价格。`entry_zone` 必须基于结构位生成，只允许使用 EMA20、Bollinger middle 和支撑位，不允许用当前价格做固定百分比偏移生成入场区间。

默认计算：
- `structural_mid = median(15m.ema20, 15m.bollinger_middle, 15m.support_level * 1.005)`。
- `entry_zone_low = max(15m.support_level * 1.002, structural_mid * 0.997)`。
- `entry_zone_high = min(15m.ema20 * 1.003, 15m.bollinger_middle * 1.003, structural_mid * 1.003)`。

结构有效性要求：
- `15m.support_level < 15m.ema20 * 1.02`。
- `15m.support_level < 15m.bollinger_middle * 1.02`。
- `entry_zone_low >= 15m.support_level * 1.002`。
- `entry_zone_high <= max(15m.ema20, 15m.bollinger_middle) * 1.003`。

有效性要求：
- `entry_zone_low <= entry_zone_high`。
- `(entry_zone_high - entry_zone_low) / entry_zone_high <= 0.015`。
- `entry_zone_low > stop_loss`。
- `entry_zone_low > 15m.support_level`。
- `15m.close <= entry_zone_high * 1.02`，否则当前价格已经脱离结构入场区，原因记为 `price_above_entry_zone`。

如果区间宽度超过 1.5%，则不生成信号，原因记为 `entry_zone_too_wide`。如果 `entry_zone_low > entry_zone_high`，则不生成信号，原因记为 `invalid_entry_zone`。

## 4. 止损生成

止损必须来自技术结构，按以下优先级选择第一个可用来源：

1. 4h support 下方：
   - 条件：`4h.support_level is not None` 且 `4h.support_level < entry_zone_low`。
   - `stop_loss = 4h.support_level * 0.997`。
   - `stop_reason = "4h support minus 0.3% buffer"`。

2. 1h recent swing low 下方：
   - 条件：`1h.recent_swing_low is not None` 且 `1h.recent_swing_low < entry_zone_low`。
   - `stop_loss = 1h.recent_swing_low * 0.997`。
   - `stop_reason = "1h swing low minus 0.3% buffer"`。

3. 15m Bollinger lower 下方：
   - 条件：`15m.bollinger_lower is not None` 且 `15m.bollinger_lower < entry_zone_low`。
   - `stop_loss = 15m.bollinger_lower * 0.997`。
   - `stop_reason = "15m Bollinger lower minus 0.3% buffer"`。

4. 15m 或 1h EMA60 下方：
   - 候选：`15m.ema60`、`1h.ema60` 中低于 `entry_zone_low` 的最高值。
   - `stop_loss = selected_ema60 * 0.997`。
   - `stop_reason = "EMA60 minus 0.3% buffer"`。

止损有效性要求：
- `stop_loss < entry_zone_low`。
- `(entry_zone_low - stop_loss) / entry_zone_low >= 0.005`。
- `(entry_zone_low - stop_loss) / entry_zone_low <= 0.08`。

如果没有任何止损来源满足条件，则不生成信号，原因记为 `missing_stop_source`。如果止损距离小于 0.5% 或大于 8%，则不生成信号，原因分别记为 `stop_too_close` 或 `stop_too_far`。

## 5. RR 过滤

V1 必须在生成信号前计算可回测的预期风险收益比，`rr < 2.0` 时不生成信号。

目标价使用结构目标，不使用任意百分比固定目标：
- `target_candidate_1 = 1h.bollinger_upper`，要求 `target_candidate_1 > entry_zone_high`。
- `target_candidate_2 = 4h.close + (4h.close - 4h.support_level)`，要求 `4h.support_level is not None` 且 `target_candidate_2 > entry_zone_high`。
- `target_price = min(valid_target_candidates)`，选择最近的可回测上方结构目标。

RR 计算：
- `entry_for_rr = entry_zone_high`。
- `risk = entry_for_rr - stop_loss`。
- `reward = target_price - entry_for_rr`。
- `rr = reward / risk`。

有效性要求：
- `risk > 0`。
- `reward > 0`。
- `rr >= 2.0`。

如果没有有效上方结构目标，则不生成信号，原因记为 `missing_target_source`。如果 `rr < 2.0`，则不生成信号，原因记为 `rr_below_2`。

## 6. Gating 机制

Gating 在评分前执行，任一 gate 命中直接返回 no signal，不进入评分。

必须实现的 gate：
- `trend_broken_gate`：`StructureAnalysis.trend_broken=True`。
- `high_volatility_gate`：`StructureAnalysis.high_volatility=True`。
- `chase_risk_gate`：`StructureAnalysis.chase_risk=True`。
- `support_too_close_gate`：`StructureAnalysis.support_too_close=True`。
- `four_hour_bearish_gate`：4h 明显空头。
- `rr_gate`：`rr < 2.0`。
- `cooldown_gate`：同一 `symbol` 在 cooldown 窗口内已有未失效做多信号。

4h 明显空头的量化定义：
- `4h.close < 4h.ema60`。
- 且 `4h.ema20 < 4h.ema60`。
- 且 `4h.ema20` 当前值低于上一根 4h EMA20。

以上 3 条同时成立时，`4h_bearish_gate=True`，禁止做多。该规则只使用已收盘 4h K线，可回测。

## 7. Invalidation 条件

`invalidation` 必须可回测，使用收盘价判断：

- 15m close below `stop_loss`。
- 或 1h close below selected stop source price。
- 或 15m 连续 3 根 lower low，触发 `trend_broken=True`。
- 或 1h EMA20 < EMA60 且 EMA20 当前值低于上一根 EMA20，触发 `trend_broken=True`。
- 或 15m 最新已收盘 K线 `(high - low) / close > 0.05`，触发 `high_volatility=True`。

输出文案格式：

```text
15m close below stop_loss OR 1h close below stop source OR trend_broken OR high_volatility
```

## 8. 风险过滤

以下任一条件命中，直接不生成 `LongSignal`：

- `insufficient_data`：任一必要周期缺失 `IndicatorSnapshot`；EMA20 少于 50 根 K线；MACD 少于 100 根 K线；Bollinger Bands、volume MA 或 support 缺失。
- `chase_risk=True`：`(15m.close - 15m.ema20) / 15m.ema20 > 0.02`。
- `support_too_close=True`：`(15m.close - 15m.support_level) / 15m.close < 0.005`。
- `trend_broken=True`：15m 连续 3 根 lower low，或 1h EMA20 < EMA60 且 EMA20 向下。
- `high_volatility=True`：15m 最新已收盘 K线 `(high - low) / close > 0.05`。
- `4h_bearish_gate=True`：4h close < EMA60，4h EMA20 < EMA60，且 4h EMA20 当前值低于上一根 4h EMA20。
- `rr_below_2`：`reward / risk < 2.0`。
- `cooldown_active`：同一 symbol 在 4-8 小时 cooldown 窗口内已有同类未失效信号。
- `cross_exchange_input`：任一 KlineBar 的 `exchange != primary_exchange`。
- `timeframe_alignment_invalid`：15m / 1h / 4h 无法基于同一个 `analysis_anchor_time` 对齐。

这些过滤项只阻止信号生成，不修改候选池、不触发交易、不写数据库。

## 9. Cooldown 规则

Cooldown 防止同一 symbol 在短时间内重复生成同类信号，必须可回测。

规则：
- 默认 cooldown 窗口：6 小时。
- 可配置范围：4 到 8 小时。
- 同一 `symbol` 若存在最近一个 `LongSignal.created_at`，且 `analysis_anchor_time - created_at < cooldown_hours`，则不生成新信号。
- 如果最近信号已经触发 `invalidation`，允许在 cooldown 窗口内重新评估，但新信号仍必须满足全部 gating、RR 和评分规则。
- 不同 `primary_exchange` 不解除 cooldown，因为 V1 的信号对象按统一 symbol 管理。

输出 no signal 原因：
- `cooldown_active:{remaining_minutes}`。

## 10. 信号评分机制

信号总分为 100 分。低于 70 分不生成信号；70 分及以上可生成 `LongSignal`。

评分结构：

```text
score =
4h_context_score      max 25
+ 1h_confirmation_score max 25
+ 15m_entry_score       max 25
+ risk_quality_score    max 25
```

4h、1h、15m 分数按第 2 节分项累计。

Risk Quality 满分 25 分：
- `chase_risk=False`：6 分。
- `support_too_close=False`：4 分。
- `trend_broken=False`：5 分。
- `high_volatility=False`：4 分。
- `4h_bearish_gate=False`：4 分。
- `rr >= 2.0`：4 分。
- 止损距离在 1% 到 5% 之间：2 分。

硬过滤命中时，不进入评分输出；评分仅用于已通过硬过滤的候选。

## 11. Signal Level

`signal_level` 是对已生成信号的 A/B/C 分级，不替代 `score`，用于展示、推送优先级和后续复盘分组。

分级规则：
- A：`score >= 85` 且 `rr >= 3.0` 且 stop distance 在 1% 到 5% 之间。
- B：`75 <= score < 85` 且 `rr >= 2.5`。
- C：`70 <= score < 75` 且 `rr >= 2.0`。
- `score < 70`：不生成信号，原因记为 `score_below_threshold`。

输出约束：
- 当前 `LongSignal` 模型没有独立 `signal_level` 字段时，`signal_level` 写入 `reasons`，格式为 `signal_level:A`、`signal_level:B` 或 `signal_level:C`。
- 后续若扩展模型，可将 `signal_level` 提升为显式字段，但不得改变评分和 gating 口径。

分数解释：
- A 级：强信号，可展示和推送。
- B 级：普通信号，可展示，是否推送由 `signals.push_threshold` 决定。
- C 级：弱信号，只展示和复盘，不默认推送。
- `score < 70`：不生成信号，原因记为 `score_below_threshold`。

## 12. LongSignal 输出结构

当前 domain 模型 `LongSignal` 字段赋值如下：

- `symbol`：来自 `StructureAnalysis.symbol`。
- `primary_exchange`：来自 `StructureAnalysis.primary_exchange`。
- `score`：第 7 节计算得到的 0-100 分。
- `entry_zone_low`：第 3 节计算得到的区间下沿。
- `entry_zone_high`：第 3 节计算得到的区间上沿。
- `stop_loss`：第 4 节计算得到的技术止损价。
- `stop_reason`：第 4 节选中的止损来源和 buffer 文案。
- `timeframe_alignment`：来自 `StructureAnalysis.timeframe_alignment`，必须包含 15m / 1h / 4h 的对齐状态。
- `reasons`：包含触发分项、gating 通过信息、RR 和 signal level，例如 `4h_close_above_ema60`、`1h_macd_histogram_positive`、`15m_support_confirmed`、`gates_passed`、`rr:2.45`、`signal_level:B`。
- `invalidation`：第 5 节定义的可回测失效条件。
- `created_at`：使用 timezone-aware datetime，建议等于 `analysis_anchor_time` 或信号生成时的 UTC 时间；必须可追溯。

`LongSignal` 不包含订单方向、杠杆、仓位、交易所下单参数或真实 API 密钥。

## 13. 降级策略

V1 不生成降级做多信号。降级只用于解释为什么没有信号。

处理规则：
- 任一周期缺失：返回 no signal，原因 `missing_timeframe:{timeframe}`。
- 任一必要指标为 `None`：返回 no signal，原因 `insufficient_data:{timeframe}:{indicator}`。
- 15m / 1h / 4h 对齐失败：返回 no signal，原因 `timeframe_alignment_invalid`。
- primary exchange K线失败：返回 no signal，原因 `primary_exchange_kline_failed`；不得使用其他交易所 K线替代。
- fallback cache 被使用：允许计算结构，但 `reasons` 必须包含 `source_status:stale_cache`；如果同时命中任一硬过滤，不生成信号。
- support 缺失：返回 no signal，原因 `missing_support`。
- stop source 缺失：返回 no signal，原因 `missing_stop_source`。
- 上方结构目标缺失：返回 no signal，原因 `missing_target_source`。
- cooldown 命中：返回 no signal，原因 `cooldown_active:{remaining_minutes}`。

所有 no signal 结果必须可写入报告或日志，但不得伪造成 `LongSignal`。

## 14. 性能预算

`long_signal_v1` 不发起网络请求，不拉 K线，不访问数据库。它只消费 Phase 8 已完成的结构分析结果。

预算：
- 单个 symbol 的信号判断目标耗时：小于 2 ms。
- Final Top M 默认 80 个 symbol，总信号判断目标耗时：小于 200 ms。
- 评分、entry zone、stop loss、invalidation 均为 O(1) 计算。
- 不允许在信号策略内重新扫描全量 K线；需要 recent swing low、support、指标时使用 Phase 8 输出。
- 不允许在信号策略内访问交易所 API、SQLite、Feishu webhook 或 Streamlit。
- cooldown 检查只消费调用方传入的最近信号元数据，不在策略函数内查询数据库。

## 15. 测试策略

单元测试必须覆盖以下场景：

- 4h 触发：
  - `4h.close >= 4h.ema60` 得分。
  - `4h.close < 4h.ema60` 但距离 support 不超过 3% 得分。
  - 缺失 `4h.support_level` 不生成信号。

- 1h 触发：
  - `1h.close >= 1h.ema20` 得分。
  - `1h.macd_histogram > 0` 得分。
  - `1h.volume < 0.8 * volume_ma` 不得获得 volume 分。

- 15m 触发：
  - `15m.close >= ema20` 得分。
  - `15m.close >= bollinger_middle` 得分。
  - support 距离在 0.5% 到 3% 之间得分。
  - entry zone 基于 EMA20、Bollinger middle 和 support 生成，不使用当前价格固定偏移。
  - entry zone 宽度超过 1.5% 不生成信号。

- 风险过滤：
  - `chase_risk=True` 不生成信号。
  - `support_too_close=True` 不生成信号。
  - `trend_broken=True` 不生成信号。
  - `high_volatility=True` 不生成信号。
  - `4h_bearish_gate=True` 不生成信号。
  - `rr < 2.0` 不生成信号。
  - cooldown active 不生成重复信号。
  - 任一必要指标为 `None` 不生成信号。

- 止损生成：
  - 优先使用 4h support。
  - 4h support 不可用时使用 1h recent swing low。
  - 再使用 15m Bollinger lower。
  - 再使用 15m / 1h EMA60。
  - `stop_loss >= entry_zone_low` 不生成信号。
  - 止损距离小于 0.5% 或大于 8% 不生成信号。

- 输出结构：
  - `entry_zone_low <= entry_zone_high`。
  - `score` 在 0 到 100。
  - `rr >= 2.0`。
  - `signal_level` 为 A、B、C 之一，并写入 `reasons`。
  - `timeframe_alignment` 包含 15m / 1h / 4h。
  - `reasons` 包含触发原因。
  - `invalidation` 包含 stop、trend_broken、high_volatility。

- 架构约束：
  - 不访问交易所 adapter。
  - 不访问 SQLite repository。
  - 不调用 Feishu notifier。
  - 不接受跨交易所 K线生成信号。
  - 不生成杠杆、仓位或订单字段。
