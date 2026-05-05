# PLANS.md

本文档记录加密货币 USDT 永续合约趋势及时捕捉系统 v0.3 的开发阶段、当前状态和验收清单。当前仓库根目录为 `/Users/claw/Documents/Cryp_trading`；后续业务代码默认放入 `crypto-perp-signal/` 目录。

## 当前状态

- 仓库级规范：已补齐 `AGENTS.md`。
- v0.3 详细计划：已创建 `docs/plan_v0.3.md`。
- 架构确认：已创建并通过 `docs/architecture_review.md`。
- 当前任务说明：已创建 `docs/TASK.md`。
- Phase 0 - Phase 14：已完成并通过测试，最近验证结果为 `pytest` 122 passed。
- 当前阶段：Phase 14 completed，pending push to origin/main。
- 当前任务：文档同步，等待确认推送到 origin/main。
- 停止点：完成文档同步后停止，等待确认 push。

## 核心约束

- 活跃度排序使用多交易所 24h ticker，不使用 K线。
- 技术分析只使用每个 symbol 的 `primary_exchange` K线。
- 禁止跨交易所合并 K线计算 EMA、MACD、Bollinger Bands 或支撑位。
- K线只在 Final Top M 之后拉取。
- 禁止先全市场拉 K线。
- 数据流必须先做每交易所 Top N 预裁剪，再补市值，再市值过滤，再重新排序取 Final Top M。
- V1 只做做多入场机会判断、飞书提醒、网页看板、信号生命周期复盘。
- V1 不计算杠杆、不自动下单，只预留未来扩展点。
- 单个交易所失败不能导致整轮扫描失败，必须记录 `source_status` 和 `latency_ms`。
- 代码必须按 `docs/architecture_review.md` 的 Interface、Application、Domain、Infrastructure 四层组织。

## Phase 0: 仓库级上下文

状态：completed

交付物：
- `AGENTS.md`
- `PLANS.md`
- `docs/TASK.md`
- `docs/plan_v0.3.md`
- `docs/architecture_review.md`

验收点：
- 仓库规则、开发阶段、当前任务和架构约束可被后续开发直接读取。
- 与 `docs/architecture_review.md` 不冲突。
- 未进入业务代码开发。

## Phase 1: 项目骨架

状态：completed

交付物：
- 创建 `crypto-perp-signal/` 目录结构。
- 创建 `requirements.txt`、`README.md`、`.env.example`。
- 创建 `config/settings.yaml`、`config/strategy_profiles.yaml`。
- 创建 `data/cache/`、`data/reports/`，但不提交本地运行生成的数据文件。

验收点：
- README 写清楚 Mac 本地安装、初始化数据库、运行一次扫描、启动看板、配置飞书。
- `.env.example` 只放变量名和示例占位，不包含真实 webhook、token、密钥。
- `.env.local` 和真实数据库文件必须被 git ignore。
- 目录结构支持 Interface、Application、Domain、Infrastructure 分层。

## Phase 2: 数据模型与事件模型

状态：completed

交付物：
- 定义 `ExchangeTicker`。
- 定义 `UnifiedActivityCandidate`。
- 定义 `KlineBar`。
- 定义 `LongSignal`。
- 定义 `SignalLifecycleRecord`。
- 定义事件对象：`ScanStarted`、`TickerFetched`、`CandidatePoolBuilt`、`MarketCapEnriched`、`CandidatesFiltered`、`PrimaryExchangeSelected`、`KlinesFetched`、`IndicatorsComputed`、`SignalGenerated`、`SignalNotified`、`SignalTracked`、`ManualReviewSubmitted`、`ScanCompleted`、`ScanFailed`。

验收点：
- 模型字段与 `docs/plan_v0.3.md` 和 `docs/architecture_review.md` 保持一致。
- 时间字段使用 timezone-aware `datetime`。
- 金额、价格、成交额允许 `None`，缺失时由评分模块降权处理。
- V1 内部按事件流组织，但不引入复杂消息队列。

## Phase 3: 交易所适配器与基础设施

状态：completed

交付物：
- 先实现 Exchange Adapter base。
- 再实现 Binance Futures、Bybit、OKX Swap、Bitget adapter。
- Kraken、Coinbase 先保留结构完整的 adapter stub。
- CoinGecko adapter 用于补充市值。
- SQLite Repository、Cache Store、Logging / Metrics 基础设施。

验收点：
- 每个交易所 adapter 返回统一模型。
- 每个请求支持 timeout、retry、rate limit、fallback cache、error logging。
- 每个响应记录 `source_status`、`latency_ms`。
- 单交易所失败时返回失败状态，不抛出导致整轮扫描中断的异常。

## Phase 4: 活跃度排序

状态：completed

交付物：
- 各交易所内部按 24h quote volume 取 `preselect_top_n_per_exchange`。
- 使用 symbol mapper 合并候选池。
- 计算 `activity_score`。
- 输出多交易所候选列表。

验收点：
- `preselect_top_n_per_exchange` 只是性能裁剪，不是最终策略过滤。
- 不同交易所 volume 字段不简单无脑相加。
- 单元测试覆盖交易所内部排序、symbol 合并、多交易所出现加分、缺失数据降权。

## Phase 5: 市值过滤

状态：completed

交付物：
- 接入 CoinGecko 获取 market cap。
- 实现 `market_cap_filter` 配置。
- 支持 unknown market cap 保留和降权。

验收点：
- 市值过滤发生在交易所 Top N 预裁剪之后、Final Top M 之前。
- 市值过滤后必须重新按活跃度排序。
- 单元测试覆盖范围内、范围外、unknown 保留、unknown 排除。

## Phase 6: 主交易所选择与 Kline Policy

状态：completed

交付物：
- 实现 `primary_exchange_selector`。
- 实现 `kline_policy`，强制 K线只来自 `primary_exchange`。
- V1 使用简化评分：24h volume rank、K线可用性、交易所稳定性。
- 后续预留 spread quality、data quality 扩展字段。

验收点：
- 禁止永久固定 Binance。
- 每个 symbol 独立选择 `primary_exchange`。
- 不跨交易所合并 K线。
- 单元测试覆盖不同交易所可用性、稳定性、成交量排名变化和 K线来源校验。

## Phase 7: K线与指标

状态：completed

交付物：
- 只对 Final Top M 拉取 15m、1h、4h K线。
- K线来源只使用 `primary_exchange`。
- 实现 EMA20、EMA60、MACD、Bollinger Bands、volume moving average。
- 实现 recent swing low 和 support level 识别。

验收点：
- 不拉取全市场 K线。
- 不跨交易所合并 K线。
- 单元测试覆盖指标计算、边界长度不足、支撑位识别。

## Phase 8: 做多信号

状态：completed

交付物：
- 实现 `long_signal_v1`。
- 输出 `entry_zone`、`stop_loss`、`stop_reason`、`timeframe_alignment`、`reasons`、`invalidation`。
- 实现 technical-only 止损优先级。

验收点：
- V1 只输出做多入场机会。
- 不计算杠杆。
- 不追过度远离 EMA20 的价格。
- 单元测试覆盖 4h、1h、15m 对齐、止损位置优先级和无信号场景。

## Phase 9: 信号生命周期、人工复盘、策略反馈

状态：completed

交付物：
- 初始化 SQLite schema：`scan_runs`、`exchange_health`、`ticker_snapshots`、`activity_candidates`、`market_caps`、`signals`、`signal_tracking`、`manual_reviews`、`strategy_feedback`。
- 信号写入、状态更新、盈亏追踪。
- 人工复盘字段和保存逻辑。
- 策略反馈记录，V1 只记录不自动改策略。

验收点：
- 支持状态：created、notified、monitoring、tp1_hit、stopped、expired、manual_reviewed。
- 记录最大浮盈、最大浮亏、是否触及止损、是否达到目标位、持续时间。
- 记录 `manual_verdict`、`manual_notes`、`manual_tags`、`reviewed_at`。

## Phase 10: 飞书提醒 + 本地 Streamlit 看板

状态：completed

交付物：
- 飞书 webhook 推送模块。
- Streamlit 本地看板。
- 当前信号、生命周期、人工复盘、数据源健康、策略表现统计页面。

验收点：
- `FEISHU_WEBHOOK_URL` 为空时安全跳过。
- A/B `signal_level` 推送，C 级只在看板展示。
- 推送内容包含 symbol、primary exchange、score、entry zone、stop loss、stop reason、15m/1h/4h 判断、reasons、本地 dashboard 地址。
- Streamlit 数据加载函数可测试，不依赖真实 UI。

## Phase 11: 扫描编排、手动运行、循环调度、报告生成

状态：completed

交付物：
- Scan Orchestrator 串联 ticker、activity ranking、market cap、primary exchange、K线计划、结构分析、long signal、持久化、飞书、生命周期初始化。
- 支持默认每 38 分钟循环扫描。
- 支持手动运行一次。
- 支持持续循环。
- 每轮生成 markdown report。

验收点：
- 单轮扫描目标耗时不超过 3 分钟。
- 单轮失败不影响下一轮调度。
- 失败交易所不能阻塞整轮。
- 每轮 report 包含候选池、过滤结果、信号、数据源健康、错误摘要。
- README 命令与实际脚本一致。

## Phase 12: V1 验收与首次提交准备

状态：completed

交付物：
- 同步 `PLANS.md`、`docs/TASK.md`、`crypto-perp-signal/README.md`。
- 运行全量 `pytest`。
- 检查 `git status`。
- 输出建议首次 commit message。

验收点：
- 不新增交易所功能。
- 不修改策略逻辑。
- 不写实盘下单。
- 不改变架构边界。
- README 覆盖本地安装、初始化数据库、单轮扫描、循环扫描、启动看板、飞书配置和 V1 禁止事项。

## Phase 13: 信号质量分析与参数优化

状态：completed

交付物：
- `lifecycle/signal_quality_analyzer.py`：信号质量评分、胜率分析、信号衰减分析。
- `lifecycle/parameter_optimizer.py`：策略参数优化建议，基于历史复盘数据。
- `application/quality_report_service.py`：生成信号质量分析报告。
- 对应测试：`test_signal_quality_analyzer.py`、`test_parameter_optimizer.py`、`test_quality_report_service.py`。

验收点：
- 质量分析覆盖 scoring 分布、signal level 分布、RR 分布、止损距离分布。
- 参数优化建议可追溯、可解释。
- 报告为 markdown 格式，可读。
- 不自动修改策略参数，只记录建议。

## Phase 14: 多策略体系

状态：completed

交付物：
- `domain/strategies/long_signal_trend_v2.py`：趋势策略 v2，改进版做多入场逻辑。
- `domain/strategies/long_signal_breakout_v1.py`：突破策略，识别关键位突破入场。
- `domain/strategies/long_signal_mean_reversion_v1.py`：均值回归策略，识别超卖反弹机会。
- `lifecycle/strategy_selector.py`：策略选择器，根据市场状态选择适用策略。
- `lifecycle/strategy_comparator.py`：策略对比器，回测不同策略表现并排名。
- 对应测试：`test_strategy_selector.py`、`test_strategy_comparator.py`。

验收点：
- 三大策略独立可测试，输入输出接口统一。
- Selector 基于市场状态（波动率、趋势强度、成交量）选择策略。
- Comparator 可横向对比策略表现（胜率、平均 RR、最大回撤）。
- 新策略不破坏原有 `long_signal_v1` 和信号生命周期流程。

## 未来只预留、不实现

- `order_adapter/`
- `paper_trading/`
- `timesfm_predictor/`
- `agent_research/`
- `portfolio_risk/`

这些模块 V1 不启用，不接真实密钥，不触发实盘交易。

## 最终自检清单

- [x] 是否避免了全市场 K线拉取？
- [x] 是否没有跨交易所合并 K线？
- [x] 是否支持每交易所 Top N 预裁剪？
- [x] 是否在市值过滤后重新排序？
- [x] 是否支持 unknown market cap 保留？
- [x] 是否单个交易所失败不会导致整轮失败？
- [x] 是否记录了 source_status 和 latency_ms？
- [x] 是否支持 Feishu webhook 为空时安全跳过？
- [x] 是否支持本地 Streamlit 看板？
- [x] 是否 SQLite 记录了完整信号生命周期？
- [x] 是否人工复盘可以保存？
- [x] 是否 V1 完全不计算杠杆？
- [x] 是否止损来自技术结构？
- [x] 是否 primary_exchange 逻辑独立可测试？
- [x] 是否 kline_policy 防止跨交易所合并 K线？
- [x] 是否每个核心模块有单元测试？
- [x] 是否 README 写清楚 Mac 本地启动步骤？
- [x] 是否 .env.local 不会被提交？
- [x] 是否 API 请求有 timeout/retry/cache？
- [x] 是否每轮循环生成可读报告？
- [x] 是否未来 order_adapter 只是预留，未启用实盘交易？
