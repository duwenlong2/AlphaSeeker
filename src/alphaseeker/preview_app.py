from __future__ import annotations

import json
import os
import subprocess
import winreg
from datetime import datetime
from pathlib import Path

import streamlit as st
from openai import AzureOpenAI, OpenAI

from alphaseeker.pipelines.shadow_scan import run_shadow_scan
from alphaseeker.providers.factory import build_market_provider, build_news_provider
from alphaseeker.storage import (
    apply_trade,
    delete_holding,
    init_storage,
    list_holdings,
    list_snapshot_times,
    list_trades,
    load_snapshot,
    save_holdings_snapshot,
    upsert_holding,
)


ENV_KEYS = [
    "LLM_PROVIDER",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
]


def _get_user_env(name: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            if isinstance(value, str) and value.strip():
                return value
    except OSError:
        return None
    return None


def _cfg(name: str, default: str = "") -> str:
    # 优先使用当前进程（页面临时输入），其次读取用户环境变量
    v = os.getenv(name)
    if v:
        return v
    user_v = _get_user_env(name)
    if user_v:
        return user_v
    return default


def _sync_runtime_env_from_user() -> None:
    # 每次 rerun 同步一遍，确保“读取来自用户环境变量”
    for key in ENV_KEYS:
        if not os.getenv(key):
            uv = _get_user_env(key)
            if uv:
                os.environ[key] = uv


def _env_status(name: str) -> str:
    return "已设置" if _cfg(name) else "未设置"


def _load_watchlist(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _status_text(status: str) -> str:
    s = status.strip().lower()
    if s == "ok":
        return "正常"
    if s == "warning":
        return "警告"
    if s == "error":
        return "错误"
    if s == "failed":
        return "失败"
    if s == "degraded":
        return "降级"
    return status


def _provider_label(kind: str, provider: str) -> str:
    market_map = {
        "mock": "mock（演示数据）",
        "baostock": "baostock（A股实盘优先）",
        "akshare": "akshare（A股扩展）",
        "yfinance": "yfinance（海外兼容）",
    }
    news_map = {
        "auto": "auto（自动选择）",
        "mock": "mock（演示新闻）",
        "akshare": "akshare（真实新闻）",
        "none": "none（不使用新闻）",
    }
    if kind == "market":
        return market_map.get(provider, provider)
    return news_map.get(provider, provider)


def _format_diagnostics_rows(diagnostics: list[dict]) -> list[dict]:
    return [
        {
            "环节": str(item.get("stage", "-")),
            "状态": _status_text(str(item.get("status", "unknown"))),
            "耗时(ms)": item.get("duration_ms", "-"),
            "说明": item.get("detail") or item.get("error") or "",
        }
        for item in diagnostics
    ]


def _format_recommendation_rows(recs: list[dict]) -> list[dict]:
    rows = []
    for r in recs:
        rows.append(
            {
                "代码": r.get("symbol"),
                "名称": r.get("name"),
                "总分": r.get("total_score"),
                "新闻分": r.get("news_score", 50.0),
                "建议仓位(%)": round(float(r.get("suggested_weight", 0) or 0) * 100, 2),
                "入场价": r.get("entry_price"),
                "事件摘要": r.get("news_summary", ""),
                "风险说明": r.get("risk_note", ""),
                "推荐理由": r.get("reason", ""),
            }
        )
    return rows


def _provider_env_panel() -> None:
    st.subheader("环境变量状态")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"AZURE_OPENAI_ENDPOINT: {_env_status('AZURE_OPENAI_ENDPOINT')}")
        st.write(f"AZURE_OPENAI_API_KEY: {_env_status('AZURE_OPENAI_API_KEY')}")
        st.write(f"AZURE_OPENAI_DEPLOYMENT: {_env_status('AZURE_OPENAI_DEPLOYMENT')}")
    with c2:
        st.write(f"DEEPSEEK_BASE_URL: {_env_status('DEEPSEEK_BASE_URL')}")
        st.write(f"DEEPSEEK_API_KEY: {_env_status('DEEPSEEK_API_KEY')}")
        st.write(f"DEEPSEEK_MODEL: {_env_status('DEEPSEEK_MODEL')}")


def _mask_value(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:4]}{'*' * (len(v) - 8)}{v[-4:]}"


def _provider_select_panel() -> None:
    st.subheader("模型提供商设置（会话级）")
    st.caption("仅写入当前 Streamlit 进程环境变量，不会写入系统环境变量。")
    provider = st.selectbox(
        "LLM_PROVIDER",
        options=["azure", "deepseek"],
        index=0 if _cfg("LLM_PROVIDER", "azure") == "azure" else 1,
    )
    os.environ["LLM_PROVIDER"] = provider

    if provider == "azure":
        deployment = st.text_input(
            "AZURE_OPENAI_DEPLOYMENT",
            value=_cfg("AZURE_OPENAI_DEPLOYMENT", ""),
            help="Azure 使用 deployment 名称",
        )
        api_key = st.text_input(
            "AZURE_OPENAI_API_KEY（可选：仅当前会话）",
            value="",
            type="password",
        )
        endpoint = st.text_input(
            "AZURE_OPENAI_ENDPOINT（可选：仅当前会话）",
            value=_cfg("AZURE_OPENAI_ENDPOINT", ""),
        )

        if deployment:
            os.environ["AZURE_OPENAI_DEPLOYMENT"] = deployment
        if endpoint:
            os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint
        if api_key:
            os.environ["AZURE_OPENAI_API_KEY"] = api_key
    else:
        model = st.text_input(
            "DEEPSEEK_MODEL",
            value=_cfg("DEEPSEEK_MODEL", "deepseek-chat"),
        )
        base_url = st.text_input(
            "DEEPSEEK_BASE_URL",
            value=_cfg("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        )
        api_key = st.text_input(
            "DEEPSEEK_API_KEY（可选：仅当前会话）",
            value="",
            type="password",
        )

        os.environ["DEEPSEEK_MODEL"] = model
        os.environ["DEEPSEEK_BASE_URL"] = base_url
        if api_key:
            os.environ["DEEPSEEK_API_KEY"] = api_key


def _show_latest_report() -> None:
    report_dir = Path("data/reports")
    if not report_dir.exists():
        st.info("尚未生成报告。请先运行一次扫描。")
        return

    files = sorted(report_dir.glob("scan_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not files:
        st.info("尚未生成报告。请先运行一次扫描。")
        return

    latest = files[0]
    st.caption(f"最新报告：{latest.as_posix()}")
    try:
        content = json.loads(latest.read_text(encoding="utf-8"))
        generated_at = str(content.get("generated_at", ""))
        providers = content.get("providers", {})
        p1, p2, p3 = st.columns(3)
        p1.metric("报告时间", generated_at.replace("T", " ")[:19] if generated_at else "-")
        p2.metric("行情源", _provider_label("market", str(providers.get("market", "-"))))
        p3.metric("新闻源", _provider_label("news", str(providers.get("news", "-"))))

        status = content.get("status", "ok")
        if status == "failed":
            st.error(f"最近报告状态：FAILED（环节：{content.get('failed_stage', 'unknown')}）")
        elif status == "degraded":
            st.warning("最近报告状态：DEGRADED（有环节降级）")
        else:
            st.success("最近报告状态：OK")

        diagnostics = content.get("diagnostics", [])
        if diagnostics:
            with st.expander("最近报告诊断详情", expanded=False):
                st.dataframe(_format_diagnostics_rows(diagnostics), width="stretch")

        recs = content.get("recommendations", [])
        if recs:
            st.dataframe(_format_recommendation_rows(recs), width="stretch")
            chart_data = {r.get("symbol", "N/A"): r.get("total_score", 0) for r in recs}
            st.bar_chart(chart_data)
    except Exception as e:
        st.warning(f"读取报告失败：{e}")


def _load_reports(limit: int = 30) -> list[dict]:
    report_dir = Path("data/reports")
    if not report_dir.exists():
        return []

    files = sorted(report_dir.glob("scan_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
    reports: list[dict] = []
    for file in files:
        try:
            reports.append(json.loads(file.read_text(encoding="utf-8")))
        except Exception:
            continue
    return reports


def _holdings_page() -> None:
    st.title("持仓")
    st.caption("交易操作 + 持仓估值 + 历史对比。")

    trade_tab, compare_tab, history_tab = st.tabs(["交易操作", "持仓对比", "历史交易"]) 

    with trade_tab:
        with st.form("apply_trade"):
            c1, c2, c3 = st.columns(3)
            with c1:
                side = st.selectbox("方向", options=["buy", "sell"], format_func=lambda x: "买入" if x == "buy" else "卖出")
                symbol = st.text_input("代码", placeholder="如 600519.SH")
            with c2:
                name = st.text_input("名称", placeholder="如 贵州茅台")
                quantity = st.number_input("数量", min_value=0.0, value=100.0, step=100.0)
            with c3:
                price = st.number_input("成交价", min_value=0.0, value=100.0, step=0.1)
                fee = st.number_input("手续费", min_value=0.0, value=0.0, step=1.0)

            note = st.text_input("备注", placeholder="可选：策略信号/手工备注")
            submitted_trade = st.form_submit_button("记录交易并更新持仓")

            if submitted_trade:
                try:
                    apply_trade(
                        side=side,
                        symbol=symbol.strip().upper(),
                        name=name.strip() or symbol.strip().upper(),
                        quantity=float(quantity),
                        price=float(price),
                        fee=float(fee),
                        note=note.strip(),
                    )
                    st.success("交易已记录，持仓已更新。")
                except Exception as e:
                    st.error(f"交易记录失败：{e}")

        st.divider()

    with st.form("add_holding"):
        col1, col2 = st.columns(2)
        with col1:
            symbol = st.text_input("代码", placeholder="如 600519.SH")
            quantity = st.number_input("持仓数量", min_value=0.0, value=100.0, step=100.0)
        with col2:
            name = st.text_input("名称", placeholder="如 贵州茅台")
            cost_price = st.number_input("成本价", min_value=0.0, value=100.0, step=0.1)

        submitted = st.form_submit_button("保存/更新持仓")
        if submitted:
            if not symbol.strip() or not name.strip() or quantity <= 0 or cost_price <= 0:
                st.error("请填写有效持仓信息。")
            else:
                upsert_holding(symbol.strip().upper(), name.strip(), float(quantity), float(cost_price))
                st.success("持仓已保存。")

        holdings = list_holdings()
        if not holdings:
            st.info("暂无持仓。")
        else:
            delete_symbol = st.selectbox("删除持仓", options=[h["symbol"] for h in holdings])
            if st.button("删除选中持仓"):
                delete_holding(delete_symbol)
                st.success(f"已删除 {delete_symbol}")
                st.rerun()

        quote_provider = st.selectbox("估值行情源", options=["baostock", "mock", "akshare", "yfinance"], index=0)
        symbols = [h["symbol"] for h in holdings]

        try:
            market_provider = build_market_provider(quote_provider)
            snapshots = market_provider.get_snapshots(symbols) if symbols else []
        except Exception as e:
            st.warning(f"行情估值失败：{e}")
            snapshots = []

        snapshot_map = {s.symbol: s for s in snapshots}

        rows = []
        total_cost = 0.0
        total_market_value = 0.0
        for h in holdings:
            qty = float(h["quantity"])
            cost = float(h["cost_price"])
            total_cost += qty * cost

            snap = snapshot_map.get(h["symbol"])
            current_price = float(snap.price) if snap else None
            market_value = qty * current_price if current_price is not None else None
            if market_value is not None:
                total_market_value += market_value

            pnl_pct = None
            if current_price is not None and cost > 0:
                pnl_pct = (current_price / cost - 1) * 100

            rows.append(
                {
                    "symbol": h["symbol"],
                    "name": h["name"],
                    "quantity": qty,
                    "cost_price": cost,
                    "current_price": current_price,
                    "market_value": market_value,
                    "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
                    "updated_at": h["updated_at"],
                }
            )

        c1, c2, c3 = st.columns(3)
        c1.metric("持仓成本", f"{total_cost:,.2f}")
        c2.metric("持仓市值", f"{total_market_value:,.2f}")
        total_pnl_pct = ((total_market_value / total_cost - 1) * 100) if total_cost and total_market_value else 0.0
        c3.metric("组合盈亏%", f"{total_pnl_pct:.2f}%")

        if rows:
            st.dataframe(rows, width="stretch")
            if st.button("保存当前持仓快照"):
                snap_time = save_holdings_snapshot(rows, snapshot_time=datetime.utcnow().isoformat())
                st.success(f"快照已保存：{snap_time}")

    with compare_tab:
        holdings = list_holdings()
        if not holdings:
            st.info("暂无持仓，无法对比。")
        else:
            quote_provider = st.selectbox(
                "对比行情源",
                options=["baostock", "mock", "akshare", "yfinance"],
                index=0,
                key="compare_quote_provider",
            )
            symbols = [h["symbol"] for h in holdings]
            try:
                snapshots = build_market_provider(quote_provider).get_snapshots(symbols)
            except Exception as e:
                st.error(f"获取当前行情失败：{e}")
                snapshots = []

            current_map = {s.symbol: float(s.price) for s in snapshots}

            snap_times = list_snapshot_times(limit=100)
            if not snap_times:
                st.warning("暂无历史快照。请先在“交易操作”页保存一次快照。")
            else:
                base_time = st.selectbox("对比基准快照", options=snap_times)
                base_rows = load_snapshot(base_time)
                base_map = {r["symbol"]: r for r in base_rows}

                compare_rows = []
                for h in holdings:
                    symbol = h["symbol"]
                    qty = float(h["quantity"])
                    cost = float(h["cost_price"])
                    curr_price = current_map.get(symbol)
                    curr_mv = qty * curr_price if curr_price is not None else None

                    base = base_map.get(symbol)
                    base_qty = float(base["quantity"]) if base else 0.0
                    base_mv = float(base["market_value"]) if base and base.get("market_value") is not None else None

                    qty_delta = qty - base_qty
                    mv_delta = (curr_mv - base_mv) if (curr_mv is not None and base_mv is not None) else None

                    compare_rows.append(
                        {
                            "symbol": symbol,
                            "name": h["name"],
                            "qty_now": qty,
                            "qty_base": base_qty,
                            "qty_delta": round(qty_delta, 2),
                            "mv_now": curr_mv,
                            "mv_base": base_mv,
                            "mv_delta": round(mv_delta, 2) if mv_delta is not None else None,
                            "cost_price": cost,
                            "current_price": curr_price,
                        }
                    )

                st.dataframe(compare_rows, width="stretch")

    with history_tab:
        st.caption("最近交易流水")
        limit = st.slider("显示条数", min_value=20, max_value=1000, value=200, step=20)
        trades = list_trades(limit=limit)
        if not trades:
            st.info("暂无交易流水。")
        else:
            st.dataframe(trades, width="stretch")


def _evaluation_page() -> None:
    st.title("观察评估")
    st.caption("这里用于看策略是否有效：先看胜率/收益，再看原因和样本明细。")

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        lookback = st.slider("评估报告数量", min_value=5, max_value=200, value=30)
    with c2:
        trend_granularity = st.selectbox("趋势粒度", options=["日", "周", "月"], index=1)
    with c3:
        quote_provider = st.selectbox("评估行情源", options=["baostock", "mock", "akshare", "yfinance"], index=0)

    reports = _load_reports(limit=lookback)
    if not reports:
        st.info("暂无可评估报告。")
        return

    # 可观测性：先基于报告做健康体检，避免“看起来有图但结论不可靠”
    total_report_recs = 0
    report_recs_with_news = 0
    event_counter: dict[str, int] = {}
    diagnostics_rows: list[dict] = []
    for report in reports:
        report_time = str(report.get("generated_at", ""))
        for d in report.get("diagnostics", []):
            diagnostics_rows.append(
                {
                    "time": report_time,
                    "stage": d.get("stage"),
                    "status": d.get("status"),
                    "duration_ms": d.get("duration_ms"),
                    "detail": d.get("detail") or d.get("error") or "",
                }
            )
        for rec in report.get("recommendations", []):
            total_report_recs += 1
            if int(rec.get("news_event_count", 0) or 0) > 0:
                report_recs_with_news += 1
            event_name = str(rec.get("news_summary") or "").split("、")[0].strip() or "无有效新闻事件"
            event_counter[event_name] = event_counter.get(event_name, 0) + 1

    news_coverage_ratio = (report_recs_with_news / total_report_recs) if total_report_recs else 0.0
    event_diversity = len([k for k in event_counter.keys() if k and k != "无有效新闻事件"])

    obs1, obs2, obs3 = st.columns(3)
    obs1.metric("报告样本(推荐)", str(total_report_recs))
    obs2.metric("新闻覆盖率", f"{news_coverage_ratio * 100:.2f}%")
    obs3.metric("事件多样性", str(event_diversity))

    quality_alerts: list[str] = []
    if total_report_recs < 30:
        quality_alerts.append("样本量偏少（<30），统计稳定性不足。")
    if news_coverage_ratio < 0.5:
        quality_alerts.append("新闻覆盖率偏低（<50%），建议提升真实新闻源可用性。")
    if event_diversity < 3:
        quality_alerts.append("事件多样性偏低（<3），归因结果可能过拟合单一事件。")

    if quality_alerts:
        st.warning("评估数据质量告警：" + "；".join(quality_alerts))
    else:
        st.success("评估数据质量正常：样本量、覆盖率、事件多样性均达到基本阈值。")

    with st.expander("调试面板：报告诊断趋势", expanded=False):
        if diagnostics_rows:
            display_diag = [
                {
                    "时间": d.get("time"),
                    "环节": d.get("stage"),
                    "状态": _status_text(str(d.get("status", "unknown"))),
                    "耗时(ms)": d.get("duration_ms"),
                    "说明": d.get("detail"),
                }
                for d in diagnostics_rows
            ]
            st.dataframe(display_diag, width="stretch")
            stage_avg: dict[str, list[float]] = {}
            for dr in diagnostics_rows:
                stage = str(dr.get("stage") or "unknown")
                dur = dr.get("duration_ms")
                if isinstance(dur, (int, float)):
                    stage_avg.setdefault(stage, []).append(float(dur))
            avg_rows = [
                {
                    "环节": k,
                    "平均耗时(ms)": round(sum(v) / len(v), 2),
                    "样本数": len(v),
                }
                for k, v in stage_avg.items()
                if v
            ]
            if avg_rows:
                st.caption("各环节平均耗时")
                st.dataframe(avg_rows, width="stretch")
        else:
            st.info("暂无可用诊断记录。")

    rows = []
    symbols: set[str] = set()
    for report in reports:
        ts = report.get("generated_at", "")
        for rec in report.get("recommendations", []):
            entry_price = rec.get("entry_price")
            symbol = rec.get("symbol")
            if not symbol or entry_price in (None, 0):
                continue
            rows.append(
                {
                    "generated_at": ts,
                    "symbol": symbol,
                    "name": rec.get("name"),
                    "total_score": rec.get("total_score"),
                    "regime_adjustment": rec.get("regime_adjustment", 0.0),
                    "news_score": rec.get("news_score", 50.0),
                    "news_event_count": rec.get("news_event_count", 0),
                    "news_summary": rec.get("news_summary", ""),
                    "entry_price": float(entry_price),
                }
            )
            symbols.add(symbol)

    if not rows:
        st.info("报告中暂无可评估推荐（可能是旧报告无 entry_price 字段）。")
        return

    event_options = sorted({
        (str(r.get("news_summary") or "").split("、")[0].strip() or "无有效新闻事件")
        for r in rows
    })
    selected_events = st.multiselect(
        "事件过滤（可多选）",
        options=event_options,
        default=[],
        help="不选=全部样本；已选=仅看指定事件",
    )

    try:
        market_provider = build_market_provider(quote_provider)
        snapshots = market_provider.get_snapshots(sorted(symbols))
    except Exception as e:
        st.error(f"评估行情获取失败：{e}")
        return

    current_map = {s.symbol: float(s.price) for s in snapshots}
    eval_rows = []
    returns = []
    bucket_stats: dict[str, list[float]] = {"70+": [], "60-70": [], "<60": []}
    news_attribution: dict[str, list[float]] = {}
    age_buckets: dict[str, list[float]] = {"0-1天": [], "1-3天": [], "3-7天": [], "7天+": []}
    trend_returns: dict[str, list[float]] = {}
    trend_wins: dict[str, list[int]] = {}

    def _trend_key(ts: str) -> str:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return "unknown"

        if trend_granularity == "日":
            return dt.strftime("%Y-%m-%d")
        if trend_granularity == "周":
            y, w, _ = dt.isocalendar()
            return f"{y}-W{w:02d}"
        return dt.strftime("%Y-%m")

    for row in rows:
        summary = str(row.get("news_summary") or "")
        event_tag = summary.split("、")[0].strip() if summary else "无有效新闻事件"
        if selected_events and event_tag not in selected_events:
            continue

        cp = current_map.get(row["symbol"])
        if cp is None or row["entry_price"] <= 0:
            continue
        ret = (cp / row["entry_price"] - 1) * 100
        returns.append(ret)

        total_score = float(row.get("total_score") or 0)
        if total_score >= 70:
            bucket_stats["70+"].append(ret)
        elif total_score >= 60:
            bucket_stats["60-70"].append(ret)
        else:
            bucket_stats["<60"].append(ret)

        if event_tag:
            news_attribution.setdefault(event_tag, []).append(ret)

        try:
            report_dt = datetime.fromisoformat(str(row.get("generated_at") or "").replace("Z", "+00:00"))
            age_days = max(0.0, (datetime.utcnow() - report_dt.replace(tzinfo=None)).total_seconds() / 86400)
            if age_days < 1:
                age_buckets["0-1天"].append(ret)
            elif age_days < 3:
                age_buckets["1-3天"].append(ret)
            elif age_days < 7:
                age_buckets["3-7天"].append(ret)
            else:
                age_buckets["7天+"].append(ret)
        except Exception:
            pass

        tk = _trend_key(str(row.get("generated_at") or ""))
        trend_returns.setdefault(tk, []).append(ret)
        trend_wins.setdefault(tk, []).append(1 if ret > 0 else 0)

        eval_rows.append(
            {
                **row,
                "current_price": cp,
                "return_pct": round(ret, 2),
            }
        )

    if not eval_rows:
        st.warning("有推荐记录，但当前行情源未返回对应代码价格，无法评估。")
        return

    win_rate = sum(1 for r in returns if r > 0) / len(returns) * 100
    avg_ret = sum(returns) / len(returns)
    med_ret = sorted(returns)[len(returns) // 2]
    avg_regime_adj = sum(float(r.get("regime_adjustment") or 0.0) for r in eval_rows) / len(eval_rows)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("评估样本数", str(len(eval_rows)))
    c2.metric("胜率", f"{win_rate:.2f}%")
    c3.metric("平均收益", f"{avg_ret:.2f}%")
    c4.metric("中位收益", f"{med_ret:.2f}%")
    st.caption(f"平均市场环境调整分：{avg_regime_adj:+.2f}")

    overview_tab, attribution_tab, detail_tab = st.tabs(["总览", "归因", "样本明细"])

    bucket_rows = []
    for bucket_name, bucket_returns in bucket_stats.items():
        if not bucket_returns:
            continue
        bucket_win = sum(1 for r in bucket_returns if r > 0) / len(bucket_returns) * 100
        bucket_avg = sum(bucket_returns) / len(bucket_returns)
        bucket_rows.append(
            {
                "分数桶": bucket_name,
                "样本数": len(bucket_returns),
                "胜率(%)": round(bucket_win, 2),
                "平均收益(%)": round(bucket_avg, 2),
            }
        )

    event_rows = []
    for event_name, event_returns in sorted(news_attribution.items(), key=lambda x: len(x[1]), reverse=True):
        if not event_returns:
            continue
        event_win = sum(1 for r in event_returns if r > 0) / len(event_returns) * 100
        event_avg = sum(event_returns) / len(event_returns)
        event_rows.append(
            {
                "事件": event_name,
                "样本数": len(event_returns),
                "胜率(%)": round(event_win, 2),
                "平均收益(%)": round(event_avg, 2),
            }
        )

    age_rows = []
    for bucket_name, bucket_returns in age_buckets.items():
        if not bucket_returns:
            continue
        age_rows.append(
            {
                "持有时长": bucket_name,
                "样本数": len(bucket_returns),
                "平均收益(%)": round(sum(bucket_returns) / len(bucket_returns), 2),
                "胜率(%)": round(sum(1 for r in bucket_returns if r > 0) / len(bucket_returns) * 100, 2),
            }
        )

    trend_rows = []
    for k in sorted(trend_returns.keys()):
        rs = trend_returns.get(k, [])
        ws = trend_wins.get(k, [])
        if not rs:
            continue
        trend_rows.append(
            {
                "周期": k,
                "样本数": len(rs),
                "平均收益(%)": round(sum(rs) / len(rs), 2),
                "胜率(%)": round(sum(ws) / len(ws) * 100, 2) if ws else 0.0,
            }
        )

    with overview_tab:
        if trend_rows:
            st.subheader("趋势概览")
            left, right = st.columns(2)
            with left:
                st.caption("平均收益趋势(%)")
                trend_ret_chart = {row["周期"]: row["平均收益(%)"] for row in trend_rows}
                st.line_chart(trend_ret_chart)
            with right:
                st.caption("胜率趋势(%)")
                trend_win_chart = {row["周期"]: row["胜率(%)"] for row in trend_rows}
                st.line_chart(trend_win_chart)
            with st.expander("查看趋势明细", expanded=False):
                st.dataframe(trend_rows, width="stretch")

        if bucket_rows:
            st.subheader("分数桶表现")
            left, right = st.columns([1.2, 1])
            with left:
                st.dataframe(bucket_rows, width="stretch")
            with right:
                bucket_chart = {
                    row["分数桶"]: row["平均收益(%)"] for row in bucket_rows
                }
                st.bar_chart(bucket_chart)

    with attribution_tab:
        left, right = st.columns(2)
        with left:
            st.subheader("新闻事件归因")
            if event_rows:
                st.dataframe(event_rows[:15], width="stretch")
                event_chart = {
                    row["事件"]: row["平均收益(%)"] for row in event_rows[:10]
                }
                st.bar_chart(event_chart)
            else:
                st.info("当前筛选下暂无事件归因样本。")
        with right:
            st.subheader("持有时长归因")
            if age_rows:
                st.dataframe(age_rows, width="stretch")
                age_chart = {row["age_bucket"]: row["avg_return_pct"] for row in age_rows}
                age_chart = {row["持有时长"]: row["平均收益(%)"] for row in age_rows}
                st.bar_chart(age_chart)
            else:
                st.info("当前筛选下暂无持有时长归因样本。")

    with detail_tab:
        st.subheader("样本明细")
        detail_rows = sorted(
            eval_rows,
            key=lambda x: (str(x.get("generated_at", "")), float(x.get("total_score") or 0.0)),
            reverse=True,
        )
        display_rows = [
            {
                "时间": r.get("generated_at"),
                "代码": r.get("symbol"),
                "名称": r.get("name"),
                "总分": r.get("total_score"),
                "新闻分": r.get("news_score"),
                "事件": r.get("news_summary"),
                "事件数": r.get("news_event_count"),
                "入场价": r.get("entry_price"),
                "现价": r.get("current_price"),
                "收益%": r.get("return_pct"),
                "市场调整": r.get("regime_adjustment", 0.0),
            }
            for r in detail_rows
        ]
        st.dataframe(display_rows, width="stretch")


def _home_page() -> None:
    st.title("AlphaSeeker")
    st.subheader("今日盯盘")
    st.caption("给新手的一键盯盘页：输入股票池，选择数据源，点运行就能看到候选股票。")

    with st.expander("第一次使用先看这里", expanded=True):
        st.markdown(
            """
            1. **股票池文件**：每行一个股票代码（例：`600519.SH`）  
            2. **行情数据源**：建议先选 `baostock`（A股更稳）  
            3. **新闻数据源**：建议先选 `mock` 验证流程，再换真实源  
            4. 点击 **运行扫描**，看“扫描状态 + 推荐表 + 诊断详情”
            """
        )

    default_watchlist = st.session_state.get("watchlist_path", "data/watchlist.txt")
    default_topn = int(st.session_state.get("topn", 5))
    default_market_provider = st.session_state.get("market_provider", "mock")
    default_news_provider = st.session_state.get("news_provider", "auto")

    col1, col2 = st.columns([3, 1])
    with col1:
        watchlist_path = st.text_input(
            "股票池文件",
            value=default_watchlist,
            help="文本文件路径，每行一个股票代码，例如 600519.SH",
        )
    with col2:
        topn = st.number_input("输出数量(TopN)", min_value=1, max_value=50, value=default_topn, step=1)

    preview_symbols = _load_watchlist(watchlist_path)
    st.caption(
        f"股票池预览：共 {len(preview_symbols)} 只"
        + (f"，示例：{', '.join(preview_symbols[:5])}" if preview_symbols else "（文件为空或不存在）")
    )

    col3, col4 = st.columns(2)
    with col3:
        market_options = ["mock", "akshare", "baostock", "yfinance"]
        market_provider_kind = st.selectbox(
            "行情数据源",
            options=market_options,
            index=market_options.index(default_market_provider)
            if default_market_provider in market_options
            else 0,
            format_func=lambda x: _provider_label("market", x),
        )
    with col4:
        news_options = ["auto", "mock", "akshare", "none"]
        news_provider_kind = st.selectbox(
            "新闻数据源",
            options=news_options,
            index=news_options.index(default_news_provider) if default_news_provider in news_options else 0,
            format_func=lambda x: _provider_label("news", x),
        )

    st.session_state["watchlist_path"] = watchlist_path
    st.session_state["topn"] = int(topn)
    st.session_state["market_provider"] = market_provider_kind
    st.session_state["news_provider"] = news_provider_kind

    if st.button("运行扫描", type="primary"):
        symbols = _load_watchlist(watchlist_path)
        if not symbols:
            st.error("股票池为空或文件不存在。")
            return

        try:
            market_provider = build_market_provider(market_provider_kind)
            news_provider = build_news_provider(news_provider_kind, market_provider_kind)
        except Exception as e:
            st.error(f"数据源初始化失败：{e}")
            return

        try:
            report = run_shadow_scan(
                watchlist=symbols,
                market_provider=market_provider,
                news_provider=news_provider,
                topn=int(topn),
            )
        except Exception as e:
            st.error(f"扫描失败：{e}")
            return

        st.success(f"扫描完成，报告文件：{report['file']}")
        status = report.get("status", "ok")
        if status == "failed":
            st.error(f"扫描失败，失败环节：{report.get('failed_stage', 'unknown')}")
        elif status == "degraded":
            st.warning("扫描降级完成：部分环节失败，已使用降级路径。")
        else:
            st.success("扫描状态：OK")

        diagnostics = report.get("diagnostics", [])
        if diagnostics:
            with st.expander("本次执行诊断详情", expanded=True):
                st.dataframe(_format_diagnostics_rows(diagnostics), width="stretch")

        recs = report["recommendations"]
        st.subheader("本次推荐结果")
        st.dataframe(_format_recommendation_rows(recs), width="stretch")
        if recs:
            chart_data = {r.get("symbol", "N/A"): r.get("total_score", 0) for r in recs}
            st.bar_chart(chart_data)

    st.divider()
    st.subheader("最近一次结果")
    _show_latest_report()


def _settings_page() -> None:
    st.title("Settings")
    st.caption("集中管理提供商、模型和环境状态。")

    _provider_env_panel()
    st.divider()
    _provider_select_panel()

    with st.expander("当前会话变量（掩码展示）", expanded=False):
        st.write(f"LLM_PROVIDER: {_cfg('LLM_PROVIDER', 'azure')}")
        st.write(f"AZURE_OPENAI_ENDPOINT: {_cfg('AZURE_OPENAI_ENDPOINT', '')}")
        st.write(f"AZURE_OPENAI_DEPLOYMENT: {_cfg('AZURE_OPENAI_DEPLOYMENT', '')}")
        st.write(f"AZURE_OPENAI_API_KEY: {_mask_value(_cfg('AZURE_OPENAI_API_KEY', ''))}")
        st.write(f"DEEPSEEK_BASE_URL: {_cfg('DEEPSEEK_BASE_URL', '')}")
        st.write(f"DEEPSEEK_MODEL: {_cfg('DEEPSEEK_MODEL', '')}")
        st.write(f"DEEPSEEK_API_KEY: {_mask_value(_cfg('DEEPSEEK_API_KEY', ''))}")

    st.divider()
    st.subheader("写入当前用户环境变量")
    st.caption("仅写入 User 级别，不支持系统级。保存后重启终端/应用进程生效。")

    def _persist_env_windows(name: str, value: str) -> tuple[bool, str]:
        if not value:
            return False, f"跳过 {name}（空值）"

        cmd = ["setx", name, value]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            ok = proc.returncode == 0
            if ok:
                return True, f"已写入 {name}"
            err = (proc.stderr or proc.stdout or "未知错误").strip()
            return False, f"写入 {name} 失败: {err}"
        except Exception as e:
            return False, f"写入 {name} 失败: {e}"

    if st.button("保存当前配置到 Windows 环境变量"):
        provider = _cfg("LLM_PROVIDER", "azure")

        to_save: list[tuple[str, str]] = [("LLM_PROVIDER", provider)]
        if provider == "azure":
            to_save.extend(
                [
                    ("AZURE_OPENAI_ENDPOINT", _cfg("AZURE_OPENAI_ENDPOINT", "")),
                    ("AZURE_OPENAI_API_KEY", _cfg("AZURE_OPENAI_API_KEY", "")),
                    ("AZURE_OPENAI_DEPLOYMENT", _cfg("AZURE_OPENAI_DEPLOYMENT", "")),
                    (
                        "AZURE_OPENAI_API_VERSION",
                        _cfg("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                    ),
                ]
            )
        else:
            to_save.extend(
                [
                    ("DEEPSEEK_BASE_URL", _cfg("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")),
                    ("DEEPSEEK_API_KEY", _cfg("DEEPSEEK_API_KEY", "")),
                    ("DEEPSEEK_MODEL", _cfg("DEEPSEEK_MODEL", "deepseek-chat")),
                ]
            )

        results = [_persist_env_windows(k, v) for k, v in to_save]
        ok_count = sum(1 for ok, _ in results if ok)
        fail_msgs = [msg for ok, msg in results if not ok]

        if fail_msgs:
            st.warning(f"已成功 {ok_count}/{len(results)} 项。")
            for msg in fail_msgs:
                st.write(f"- {msg}")
        else:
            st.success(f"已成功写入 {ok_count} 项。请重启终端/应用使其读取到新环境变量。")


def _create_llm_client_from_env() -> tuple[object, str, str]:
    provider = _cfg("LLM_PROVIDER", "azure").strip().lower()
    if provider == "azure":
        endpoint = _cfg("AZURE_OPENAI_ENDPOINT")
        api_key = _cfg("AZURE_OPENAI_API_KEY")
        deployment = _cfg("AZURE_OPENAI_DEPLOYMENT")
        api_version = _cfg("AZURE_OPENAI_API_VERSION", "2024-10-21")

        if not endpoint or not api_key or not deployment:
            raise ValueError("Azure 配置不完整：需要 ENDPOINT / API_KEY / DEPLOYMENT")

        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        return client, deployment, "azure"

    if provider == "deepseek":
        api_key = _cfg("DEEPSEEK_API_KEY")
        base_url = _cfg("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        model = _cfg("DEEPSEEK_MODEL", "deepseek-chat")
        if not api_key:
            raise ValueError("DeepSeek 配置不完整：需要 DEEPSEEK_API_KEY")

        client = OpenAI(base_url=base_url, api_key=api_key)
        return client, model, "deepseek"

    raise ValueError(f"不支持的 LLM_PROVIDER: {provider}")


def _llm_test_page() -> None:
    st.title("测试功能")
    st.caption("验证当前用户环境变量配置的 LLM 连通性。")

    st.write(f"当前提供商: {_cfg('LLM_PROVIDER', 'azure')}")

    prompt = st.text_area("测试提示词", value="请只回复：OK", height=100)
    max_tokens = st.slider("max_completion_tokens", min_value=16, max_value=512, value=64)

    if st.button("执行 LLM 连通性测试", type="primary"):
        try:
            client, model, provider = _create_llm_client_from_env()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_tokens,
            )

            text = (resp.choices[0].message.content or "").strip()
            st.success(f"测试成功：provider={provider}, model={model}")
            st.text_area("模型响应", value=text, height=180)
        except Exception as e:
            st.error(f"测试失败：{e}")


def main() -> None:
    st.set_page_config(page_title="AlphaSeeker Preview", layout="wide")
    _sync_runtime_env_from_user()
    init_storage()

    with st.sidebar:
        st.header("导航")
        page = st.radio("页面", ["主页", "持仓", "观察评估", "Settings", "测试功能"], index=0)
        st.caption("建议将密钥配置在系统环境变量。")

    if page == "主页":
        _home_page()
    elif page == "持仓":
        _holdings_page()
    elif page == "观察评估":
        _evaluation_page()
    elif page == "Settings":
        _settings_page()
    else:
        _llm_test_page()


if __name__ == "__main__":
    main()
