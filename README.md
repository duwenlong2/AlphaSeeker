# AlphaSeeker

基于 Python 的个人智能选股辅助系统（先盯盘、后评估、再迭代）。

## 当前阶段：Shadow Mode（只给建议，不下单）

目标：连续运行 7~14 天，稳定输出每日候选股票代码、理由、风险提示，并对建议做事后评估。

### 核心流程

1. `watchlist`（股票池）
2. 行情快照 + 新闻事件
3. 估值/质量/催化/趋势打分
4. 风险门过滤
5. 输出 TopN 推荐（代码 + 解释）
6. 生成日报 JSON，便于后续复盘

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m alphaseeker.cli scan --watchlist data/watchlist.txt --topn 5
```

运行后会在 `data/reports/` 生成当日推荐文件。

预览页面（可选）：

```bash
streamlit run src/alphaseeker/preview_app.py
```

页面说明：

- 主页：股票扫描与结果预览
- Settings：模型配置与环境变量管理（仅写入 Windows 用户环境变量）
- 测试功能：LLM 连通性测试（Azure/DeepSeek）

## 目录

- `src/alphaseeker/providers`：数据源接口与 mock 数据
- `src/alphaseeker/skills`：打分与风控能力
- `src/alphaseeker/pipelines`：扫描与评估流程
- `src/alphaseeker/cli.py`：命令行入口

## 能力总览

已整理完整能力清单（`skills` / `pipelines` / `providers`）：

- docs 能力文档：`docs/capabilities.md`

其中包含：
- `skills`：估值分、质量分、趋势分、新闻催化分、风险惩罚、综合排序
- `pipelines`：一次性盯盘扫描、TopN 输出、报告落盘
- `providers`：行情与新闻接口定义，mock 供联调

## 预览页面建议（API Key + 模型选择）

建议添加预览页面，但采用“安全优先”策略：

1. **默认只用系统环境变量**（推荐）
	- 页面仅显示 Key 状态：已设置/未设置
	- 不显示明文、不落盘保存
2. **模型与提供商可在页面切换**
	- `LLM_PROVIDER`: `azure` / `deepseek`
	- 模型名（或 deployment）可选
3. **页面可触发扫描并展示 TopN**
	- 方便你每天盯盘观察效果

> 结论：要加预览页面，但不要把 Key 长久存储在页面配置里。

## 下一步建议

- 接入真实行情（AkShare/Tushare 等）
- 接入新闻源（公告/财经新闻）
- 接入 Telegram Bot（推送 `/top` `/why`）
- 加入回测与收益归因
