# TASK.md

本文档记录当前仓库任务、执行边界和下一步停止点。

## 当前任务

当前任务 = V1 acceptance。

本轮只执行验收、文档同步和首次提交准备：
- 更新 `PLANS.md`，将 Phase 0 - Phase 12 标记为 completed。
- 更新 `docs/TASK.md`，标记当前任务为 V1 acceptance。
- 更新 `crypto-perp-signal/README.md`，补齐本地运行、飞书配置和 V1 禁止事项。
- 运行全量 `pytest`。
- 运行 `git status`。
- 输出建议首次 commit message。

## 当前状态

- Phase 0：仓库级上下文，completed。
- Phase 1：项目骨架，completed。
- Phase 2：domain models/events，completed。
- Phase 3：SQLite schema + repository，completed。
- Phase 4：HTTP/cache/exchange adapter 基础设施，completed。
- Phase 5：activity_ranker，completed。
- Phase 6：market_cap_filter，completed。
- Phase 7：primary_exchange_selector，completed。
- Phase 8：kline_policy / indicators / support_resistance / structure_analyzer / long_signal_v1，completed。
- Phase 9：signal lifecycle / manual review / strategy feedback，completed。
- Phase 10：Feishu notifier / local Streamlit dashboard，completed。
- Phase 11：scan orchestrator / scheduler / reports / CLI entrypoints，completed。
- Phase 12：V1 acceptance 与首次提交准备，completed。
- 最近验证结果：`pytest` 106 passed。

## 本轮不做

- 不新增交易所功能。
- 不修改策略逻辑。
- 不写实盘下单。
- 不改架构边界。
- 不修改 `.env`、密钥、token、CI/CD 配置。
- 不提交、不推送 git，等待用户确认。

## 后续开发必须遵守

- 严格按 `AGENTS.md` 的规则执行。
- 严格按 `PLANS.md` 的阶段顺序开发。
- 严格按 `docs/architecture_review.md` 的四层架构实现。
- 不允许跨交易所合并 K线。
- 不允许先全市场拉 K线。
- 不允许实盘下单。
- 不允许写成单文件脚本。
- 必须本地 Mac 可运行。
- 必须支持飞书提醒和 Streamlit 看板。

## 下一步等待确认

本轮完成后停止，等待用户确认是否执行首次 git commit。
