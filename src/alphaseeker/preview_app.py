from __future__ import annotations

import json
import os
import subprocess
import winreg
from pathlib import Path

import streamlit as st
from openai import AzureOpenAI, OpenAI

from alphaseeker.pipelines.shadow_scan import run_shadow_scan
from alphaseeker.providers.mock_provider import MockMarketDataProvider, MockNewsProvider


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
        recs = content.get("recommendations", [])
        if recs:
            st.dataframe(recs, width="stretch")
            chart_data = {r.get("symbol", "N/A"): r.get("total_score", 0) for r in recs}
            st.bar_chart(chart_data)
    except Exception as e:
        st.warning(f"读取报告失败：{e}")


def _home_page() -> None:
    st.title("AlphaSeeker")
    st.subheader("今日盯盘")
    st.caption("主页聚焦股票扫描与结果预览。")

    default_watchlist = st.session_state.get("watchlist_path", "data/watchlist.txt")
    default_topn = int(st.session_state.get("topn", 5))

    col1, col2 = st.columns([3, 1])
    with col1:
        watchlist_path = st.text_input("股票池文件", value=default_watchlist)
    with col2:
        topn = st.number_input("TopN", min_value=1, max_value=50, value=default_topn, step=1)

    st.session_state["watchlist_path"] = watchlist_path
    st.session_state["topn"] = int(topn)

    if st.button("运行扫描", type="primary"):
        symbols = _load_watchlist(watchlist_path)
        if not symbols:
            st.error("股票池为空或文件不存在。")
            return

        report = run_shadow_scan(
            watchlist=symbols,
            market_provider=MockMarketDataProvider(),
            news_provider=MockNewsProvider(),
            topn=int(topn),
        )

        st.success(f"扫描完成，报告文件：{report['file']}")
        recs = report["recommendations"]
        st.dataframe(recs, width="stretch")
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

    with st.sidebar:
        st.header("导航")
        page = st.radio("页面", ["主页", "Settings", "测试功能"], index=0)
        st.caption("建议将密钥配置在系统环境变量。")

    if page == "主页":
        _home_page()
    elif page == "Settings":
        _settings_page()
    else:
        _llm_test_page()


if __name__ == "__main__":
    main()
