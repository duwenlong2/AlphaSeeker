# AlphaSeeker MVP 蓝图（第一性原则）

## 1. 核心目标

- 不是追求“抄顶逃顶”，而是拿到中段稳健利润。
- 先控制回撤，再提高收益。
- AI 负责信息压缩和解释，风控规则负责最终约束。

## 2. 我们相对开源项目的差异化

### 借鉴对象与吸收点

- Freqtrade：交易流程完整、风控与 Telegram 运维体验好
- vn.py：事件驱动架构成熟、交易模块拆分清晰
- Qlib：研究闭环强（数据-因子-模型-回测）
- LangGraph/AutoGen：多技能编排和状态化执行

### 我们要做的“个人投资者优势”

- 账户级个性化风险参数（资金规模、回撤容忍度）
- “不赚最后一段”的纪律化执行
- 决策可解释、可回放、可审计

## 3. MVP 必备能力

- 数据层：行情快照 + 新闻事件 + 基础面（先 mock，再真实源）
- 选股层：估值/质量/催化/趋势评分
- 风控层：最低总分、追高过滤、风险惩罚上限
- 组合层：现金缓冲 + 单票上限 + 最大持仓数
- 执行层：先 Shadow Mode（只推荐、不下单）
- 复盘层：日报 JSON + 周月统计

## 4. 关键规则（当前默认）

- 最低综合分：55
- 20日涨幅追高过滤：>35% 不新开
- 现金缓冲：20%
- 最大持仓：5
- 单票上限：20%
- 止损：8%
- 止盈：18%
- 回撤止盈（追踪止盈）：8%

## 5. 需要设计的 Skills

- UniverseFilterSkill：可交易股票池过滤
- FactorScoringSkill：估值/质量/趋势/催化打分
- RiskGateSkill：规则风控与一票否决
- AllocationSkill：目标仓位计算
- ThesisSkill：可解释推荐理由
- EvaluationSkill：绩效归因与参数检视

## 6. 可接入 MCP（按优先级）

- MarketData MCP
- News MCP
- Fundamentals MCP
- LLM MCP（Azure/DeepSeek）
- Notification MCP（Telegram）
- Storage MCP
- Broker Paper MCP（第二阶段）

## 7. 实施节奏

- 第1周：稳定产出 TopN 报告，验证规则可解释
- 第2-3周：接真实数据源，做周/月复盘口径
- 第4周：模拟交易回放，验证回撤与执行纪律
