# AlphaSeeker 能力说明（MVP）

## 1) `skills` 能力

`skills` 负责“可复用的单点能力”，输入清晰、输出结构化，便于后续组合成多条流程。

### `valuation_score()`
- 作用：计算估值分（PE/PB 简化版）
- 输入：`StockSnapshot`
- 输出：`0~100` 分
- 特点：估值越低分数越高（MVP 版本）

### `quality_score()`
- 作用：计算质量分（ROE + 营收增速）
- 输入：`StockSnapshot`
- 输出：`0~100` 分
- 特点：偏向基本面稳健公司

### `trend_score()`
- 作用：计算趋势分（20日涨跌幅 + 量比）
- 输入：`StockSnapshot`
- 输出：`0~100` 分
- 特点：避免“便宜但一直下跌”

### `catalyst_scores()`
- 作用：新闻催化打分（关键词正负面）
- 输入：`list[NewsItem]`
- 输出：`dict[symbol, score]`
- 特点：正面新闻加分，负面新闻减分

### `risk_penalty()`
- 作用：风险惩罚与风险说明
- 输入：`StockSnapshot` + 该股票新闻
- 输出：`(risk_penalty, risk_note)`
- 特点：高风险可直接降低排名，后续可扩展为一票否决

### `rank_stocks()`
- 作用：多维度综合排序并产出候选
- 输入：行情快照、新闻、配置、`topn`
- 输出：`Recommendation` 列表
- 特点：统一权重计算 + 风险过滤

---

## 2) `pipelines` 能力

`pipelines` 负责“端到端流程编排”，把 provider + skills 串起来，产出可消费结果。

### `run_shadow_scan()`
- 作用：执行一次盯盘扫描（Shadow Mode）
- 步骤：
  1. 拉取股票池快照
  2. 拉取新闻
  3. 调用 `rank_stocks()` 排序
  4. 生成报告 JSON（`data/reports/`）
- 输出：
  - 终端 TopN 结果
  - 报告文件路径

---

## 3) `providers` 能力

### `MarketDataProvider`
- 定义行情快照接口 `get_snapshots()`

### `NewsProvider`
- 定义新闻接口 `get_news()`

### `MockMarketDataProvider` / `MockNewsProvider`
- 作用：本地联调与流程验证
- 价值：先验证打分逻辑和流程稳定性，再替换真实数据源

---

## 4) 建议的预览页面（是否要加）

建议添加，但分两期：

### 第一期（建议立即做）
- 只做“预览与调参面板”，不保存密钥
- 展示：
  - 环境变量是否已设置（仅显示已设置/未设置）
  - 提供商选择：`azure` / `deepseek`
  - 模型选择（非密钥项）
  - 一键触发扫描并查看 TopN

### 第二期（谨慎做）
- 页面可临时输入 Key（仅当前会话内存，不落盘）
- 默认仍建议系统环境变量方式

> 安全建议：不要把 API Key 写入仓库、配置文件、日志或数据库。
