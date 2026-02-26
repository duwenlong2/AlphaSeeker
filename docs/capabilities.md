# AlphaSeeker 能力说明（当前实现）

## 1) 核心分析能力（skills）

### 基础因子评分
- `valuation_score()`：估值分（PE/PB）
- `quality_score()`：质量分（ROE + 营收增速）
- `trend_score()`：趋势分（20日涨跌幅 + 量比）

### 新闻结构化分析
- `deduplicate_news()`：按“代码 + 标题归一化”去重新闻
- `extract_news_events()`：将新闻标题映射为结构化事件（事件类型/情绪/置信度/时效衰减）
- `build_symbol_news_signals()`：生成股票级新闻信号（`news_score`、事件数量、摘要）
- 事件影响差异化：不同事件类型使用不同冲击系数（如退市违约 > 合规风险 > 中性信息）

当前事件字典（稳定代码）：
- 正向：`earnings_growth`、`new_order`、`buyback`、`innovation`、`policy_support`
- 负向：`shareholder_reduction`、`earnings_drop`、`compliance_risk`、`delist_or_default`

### 综合排序与风控
- `risk_penalty()`：风险惩罚与风险说明
- `market_regime_signal()`：从股票池整体涨跌与广度推断市场环境（偏多/震荡/偏空）
- `rank_stocks()`：融合估值/质量/趋势/新闻催化并输出 `Recommendation`
  - 催化分由“关键词分 + 结构化新闻分”自适应融合（随事件数量提高结构化权重）
  - 总分额外叠加市场环境调整分（regime adjustment）
  - 推荐结果包含 `news_score`、`news_event_count`、`news_summary`

---

## 2) 流程编排能力（pipelines）

### `run_shadow_scan()`
- 端到端流程：行情 -> 新闻 -> 排序 -> 仓位分配 -> 报告落盘
- 报告输出：`data/reports/scan_*.json`
- 诊断能力：每环节 `status/duration/error`，支持 `ok/degraded/failed`
- 新闻诊断：新增 `news_signal` 诊断项（推荐覆盖率、平均新闻分）
- 行情诊断：新增 `market_regime` 诊断项（环境类型与调整分）
- 策略参数：报告 `policy` 包含新闻融合参数（权重/步长/时效半衰期）

---

## 3) 数据接入能力（providers）

### 行情源
- `mock`
- `akshare`
- `yfinance`
- `baostock`（当前可用主真实源）

### 新闻源
- `mock`
- `akshare`
- `auto`
- `none`

---

## 4) 产品化能力（Streamlit）

### 主页
- 运行扫描、展示推荐、展示执行诊断

### 持仓页
- 交易记录、持仓估值、快照对比、历史流水

### 观察评估页（闭环）
- 指标：样本数、胜率、平均收益、中位收益
- 分析：分数桶表现（70+/60-70/<60）
- 归因：新闻事件归因（事件标签的样本数/胜率/平均收益）
- 过滤：支持按事件标签筛选评估样本
- 分层：持有时长归因（0-1天 / 1-3天 / 3-7天 / 7天+）
- 趋势：按日/周/月的收益与胜率趋势
- 可视化：分数桶收益图 + 事件归因收益图 + 时间趋势图
- 可观测：数据质量体检（样本量、新闻覆盖率、事件多样性）
- 调试：报告诊断趋势面板（分环节状态与平均耗时）

### Settings + 测试功能
- Azure / DeepSeek 用户级环境变量配置
- LLM 连通性测试

---

## 5) 已知边界

- 不同网络环境下，新闻源可用性可能波动；系统会降级并保留诊断信息。
- 当前新闻事件识别主要依赖标题规则，后续可升级为正文级 NLP 抽取。
- 当前评估为观察型回测，不包含完整撮合与滑点建模。
