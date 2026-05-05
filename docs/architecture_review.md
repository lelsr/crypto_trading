# Architecture Review v0.3

本文档是 v0.3 开发前的架构确认。已阅读 `PLANS.md`、`docs/plan_v0.3.md`；当前仓库内未发现实际落盘的 `AGENTS.md`，本次按对话中提供的 AGENTS 指令执行。

## 1. 系统边界

V1 是本地 Mac 可运行的 USDT 永续合约趋势捕捉系统，负责扫描行情、筛选活跃合约、选择主交易所、拉取 K线、计算指标、生成做多入场信号、发送飞书提醒、展示 Streamlit 看板、记录信号生命周期和人工复盘。

V1 明确不做：
- 不实盘下单。
- 不计算杠杆。
- 不做空策略。
- 不做跨交易所 K线合并。
- 不先全市场拉 K线。
- 不做复杂多 Agent 系统。
- 不启用 TimesFM 预测。
- 不把项目写成单文件脚本。

最重要边界：
- 活跃度来自多交易所 ticker。
- K线只在 Final Top M 之后拉取。
- K线只拉每个 symbol 的 `primary_exchange`。
- 其他交易所只可做辅助验证，不参与主技术指标计算。

## 2. 建议分层架构

必须按四层组织，不允许把 API 请求、指标计算、飞书推送、数据库写入混在一个文件里。

Interface Layer：
- Streamlit Dashboard：读取 SQLite 和报告，展示当前信号、排行、健康状态、生命周期、人工复盘。
- Feishu Notifier：只负责消息格式化和 webhook 发送。
- CLI：提供初始化数据库、单次扫描、循环扫描、启动看板入口。

Application Layer：
- Scheduler：负责 38 分钟周期调度、手动运行一次、持续循环。
- Scan Orchestrator：编排完整扫描流程和事件流。
- Signal Lifecycle Service：负责信号状态推进、盈亏追踪、过期判断。
- Manual Review Service：负责人工复盘提交、标签、备注和反馈记录。

Domain Layer：
- Activity Ranking：交易所内 Top N、候选合并、活跃度评分。
- Market Cap Filtering：市值补全、范围过滤、unknown market cap 处理。
- Primary Exchange Selection：独立选择每个 symbol 的主交易所。
- Kline Analysis：K线策略约束、指标输入校验、指标计算结果组织。
- Long Signal Strategy：做多入场决策、入场区间、技术止损、理由。
- Signal Evaluation：生命周期表现评价、复盘反馈、策略评分输入。

Infrastructure Layer：
- Exchange Adapters：Binance Futures、Bybit、OKX Swap、Bitget、Kraken、Coinbase。
- CoinGecko Adapter：市值补充。
- SQLite Repository：所有表读写。
- Cache Store：ticker、market cap、Kline fallback cache。
- Logging / Metrics：结构化日志、耗时、错误、健康状态。

## 3. 完整数据流

```text
Ticker Snapshot
→ Exchange Local Top N
→ Unified Candidate Pool
→ Market Cap Enrichment
→ Market Cap Filter
→ Activity Re-rank
→ Final Top M
→ Primary Exchange Selection
→ Kline Fetch
→ Indicator Calculation
→ Long Signal Decision
→ Signal Persistence
→ Feishu Notification
→ Dashboard Display
→ Lifecycle Tracking
→ Manual Review
→ Strategy Feedback
```

强制规则：
- `Kline Fetch` 只能发生在 `Final Top M` 之后。
- `Kline Fetch` 只能使用 `Primary Exchange Selection` 得到的 `primary_exchange`。
- 技术指标输入必须校验所有 `KlineBar.exchange == primary_exchange`。
- 活跃度排序阶段不得读取 K线。
- 市值过滤后必须重新排序，再取最终技术分析对象。

## 4. 事件模型

V1 不需要复杂消息队列，但内部代码必须按事件流组织。事件对象至少包含 `event_id`、`scan_run_id`、`event_type`、`created_at`、`payload`、`source_status`、`latency_ms`、`error`。

事件对象：
- `ScanStarted`：扫描开始，记录配置快照。
- `TickerFetched`：单交易所 ticker 获取完成或失败。
- `CandidatePoolBuilt`：统一候选池构建完成。
- `MarketCapEnriched`：市值补全完成。
- `CandidatesFiltered`：市值过滤完成。
- `PrimaryExchangeSelected`：每个 symbol 的主交易所选择完成。
- `KlinesFetched`：primary exchange K线拉取完成或部分失败。
- `IndicatorsComputed`：指标计算完成。
- `SignalGenerated`：做多信号生成。
- `SignalNotified`：飞书推送完成、失败或跳过。
- `SignalTracked`：信号生命周期追踪完成。
- `ManualReviewSubmitted`：人工复盘提交。
- `ScanCompleted`：扫描成功完成，允许 partial success。
- `ScanFailed`：扫描发生不可恢复失败。

实现原则：
- Scan Orchestrator 负责创建和串联事件。
- Domain 模块只接收输入并返回结果，不直接发飞书、不写数据库。
- Infrastructure 负责持久化事件和健康状态。

## 5. 数据库表设计

至少创建以下 SQLite 表：

`scan_runs`：
- 记录每轮扫描开始、结束、状态、耗时、配置快照、错误摘要。
- 用于回答某轮为什么失败或为什么没有推送。

`exchange_health`：
- 记录交易所、接口类型、`source_status`、`latency_ms`、错误码、错误信息、最近成功时间。
- 用于分析哪个交易所经常失败。

`ticker_snapshots`：
- 记录每轮每交易所的 ticker 快照、原始 symbol、统一 symbol、24h quote volume、last price、数据状态。
- 用于复盘候选池来源。

`activity_candidates`：
- 记录统一候选、出现交易所、活跃度评分、市值状态、primary exchange、是否进入 Final Top M。
- 用于解释候选为什么被保留或淘汰。

`market_caps`：
- 记录 CoinGecko 市值、状态、更新时间、是否 unknown、是否命中过滤范围。
- 用于复盘市值过滤效果。

`signals`：
- 记录信号主体、score、entry zone、stop loss、stop reason、reasons、timeframe alignment、invalidation。
- 用于回答某个信号当时为什么生成。

`signal_tracking`：
- 记录状态推进、最大浮盈、最大浮亏、是否触及止损、是否达到目标、持续时间。
- 用于评估信号后来是否有效。

`manual_reviews`：
- 记录人工结论、备注、标签、复盘时间、关联 signal。
- 用于保存人工复盘。

`strategy_feedback`：
- 记录人工复盘和真实表现对策略评分、过滤规则、信号理由的反馈。
- V1 只记录，不自动改策略。

建议所有表包含：
- `id` 或业务主键。
- `scan_run_id`。
- `created_at`、`updated_at`。
- 关键 JSON 字段存储配置快照、原始响应摘要或理由列表。

## 6. 关键失败场景与降级策略

交易所 ticker 失败：
- 标记该交易所 `source_status=failed`。
- 记录 structured logging 和 `exchange_health`。
- 使用 fallback cache 时标记 `source_status=stale_cache`。
- 继续处理其他交易所，实现 partial success。

CoinGecko 市值失败：
- market cap 标记 unknown。
- 根据 `keep_unknown_market_cap` 决定保留或剔除。
- 保留 unknown 时必须降权。

Primary exchange K线失败：
- 不跨交易所合并 K线替代。
- 可按 primary 选择器的候选顺序尝试下一个交易所，但必须重新标记新的 `primary_exchange` 并记录原因。
- 如果无可用主交易所，则该 symbol 不进入指标计算。

指标计算数据不足：
- 返回无信号和明确原因。
- 不用补零或伪造指标。

飞书 webhook 为空或失败：
- webhook 为空时安全跳过。
- webhook 失败只影响通知状态，不影响信号入库。

SQLite 写入失败：
- 对该阶段标记失败。
- 扫描 report 必须记录错误。
- 不应继续假装已持久化信号。

调度重启或上轮超时：
- 使用 APScheduler 时配置单任务最大并发为 1。
- 使用 misfire/coalesce 策略，避免重启后堆积多轮扫描。
- 单轮异常写入 `ScanFailed`，下一轮继续。

稳定性组件：
- timeout：所有 HTTP 请求必须配置。
- retry：只对网络超时、临时 5xx、限流类错误重试。
- rate limit：官方 REST adapter 自己实现节流；CCXT fallback 保持 `enableRateLimit=True` 并复用 exchange instance。
- fallback cache：只用于降级，不用于伪装实时数据。
- partial success：允许部分交易所失败。
- health status：每个数据源独立记录健康状态。
- structured logging：日志字段包含 scan_run_id、exchange、symbol、timeframe、event_type、latency_ms、source_status。

## 7. 性能预算

默认预算：
- 单轮扫描目标耗时：不超过 3 分钟。
- 默认循环间隔：38 分钟。
- 每交易所预选：Top 300。
- 最终技术分析：Top 80。
- K线周期：15m / 1h / 4h。
- 每周期 limit：200。
- 失败交易所不能阻塞整轮。

性能策略：
- ticker 阶段可并发请求各交易所，但每交易所内部必须限速。
- K线只对 Final Top M 拉取，最多约 80 * 3 个 K线请求。
- K线请求按交易所分组限速，避免同时打爆单一交易所。
- Streamlit 看板查询使用 `st.cache_data` 缓存数据库查询和可序列化结果，设置合理 TTL。
- 每轮生成 markdown report，避免看板反复做重计算。

## 8. 单元测试计划

必须测试模块：
- `activity_ranker`。
- `market_cap_filter`。
- `primary_exchange_selector`。
- `kline_policy`。
- `long_signal_v1`。
- `signal_lifecycle`。
- `manual_review`。

重点测试：
- 不跨交易所合并 K线。
- K线只在 Final Top M 之后拉取。
- K线只拉 `primary_exchange`。
- 市值过滤后重新排序。
- unknown market cap 是否按配置保留。
- 单一交易所失败是否继续运行。
- Feishu webhook 为空是否安全跳过。
- 信号生命周期是否完整记录状态、最大浮盈、最大浮亏、人工复盘。
- V1 是否完全不计算杠杆、不触发 order adapter。

建议集成测试：
- mock 多交易所 ticker，验证 Top N、合并、市值过滤、Final Top M 顺序。
- mock primary exchange K线失败，验证不跨交易所混算。
- mock SQLite，验证 signals、signal_tracking、manual_reviews、strategy_feedback 写入路径。

## 9. V1 必须实现模块

必须实现：
- 项目骨架和配置加载。
- 数据模型和事件模型。
- Binance Futures、Bybit、OKX Swap、Bitget adapter。
- Kraken、Coinbase adapter stub 和健康状态。
- CoinGecko market cap adapter。
- Activity Ranking。
- Market Cap Filtering。
- Primary Exchange Selection。
- Kline Policy 和 Kline Fetch 编排。
- EMA20、EMA60、MACD、Bollinger Bands、volume moving average、recent swing low、support level。
- Long Signal Strategy V1。
- SQLite Repository 和初始化脚本。
- Signal Lifecycle Service。
- Manual Review Service。
- Feishu Notifier。
- Streamlit Dashboard。
- CLI。
- Scheduler / Scan Orchestrator。
- 每轮 markdown report。
- 核心单元测试。

## 10. 只预留、不实现模块

V1 只创建接口或目录占位，不启用真实功能：
- `order_adapter/`：未来真实下单适配，不接任何私钥，不发真实订单。
- `paper_trading/`：未来模拟交易。
- `timesfm_predictor/`：未来时间序列预测。
- `agent_research/`：未来研究报告或解释增强。
- `portfolio_risk/`：未来组合风险和仓位管理。

这些模块不得影响 V1 主流程，也不得引入实盘交易配置。

## 资料依据

- CCXT Manual Rate Limit: https://github.com/ccxt/ccxt/wiki/manual
- APScheduler User Guide: https://apscheduler.readthedocs.io/en/3.x/userguide.html
- APScheduler master User Guide: https://apscheduler.readthedocs.io/en/master/userguide.html
- Streamlit `st.cache_data`: https://docs.streamlit.io/1.51.0/develop/api-reference/caching-and-state/st.cache_data
- Streamlit Caching Overview: https://docs.streamlit.io/develop/concepts/architecture/caching
