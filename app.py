import streamlit as st
import os
import time
from src.agent import ResearchAgent
from src.state_manager import StateManager
from pathlib import Path

# 页面配置
st.set_page_config(
    page_title="Deep Research Agent",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 Deep Research Agent")
st.markdown("基于大模型的深度自主调研工具")

# 侧边栏配置
with st.sidebar:
    st.header("配置")
    api_key = st.text_input("OpenAI API Key", type="password", help="在此输入您的 OpenAI API Key")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    base_url = st.text_input("Base URL", value=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"), help="API 基础地址，例如 https://api.deepseek.com/v1")
    if base_url:
        os.environ["OPENAI_BASE_URL"] = base_url

    model_name = st.text_input("Model Name", value=os.getenv("MODEL_NAME", "gpt-4o"), help="模型名称，例如 deepseek-chat")
    if model_name:
        os.environ["MODEL_NAME"] = model_name

    max_loops = st.slider("最大循环次数", min_value=1, max_value=20, value=10)

    st.info("该工具会自动搜索网络信息并整合为深度调研报告。")

# 初始化状态
if "running" not in st.session_state:
    st.session_state.running = False
if "report" not in st.session_state:
    st.session_state.report = None

# 主界面逻辑
goal = st.text_input("请输入您的调研目标:", placeholder="例如：2024年全球生成式AI市场发展趋势调研")

col1, col2 = st.columns(2)

with col1:
    start_btn = st.button("开始调研", disabled=st.session_state.running)

with col2:
    if st.session_state.running:
        st.warning("调研进行中，请耐心等待...")

if start_btn and goal:
    if not os.environ.get("OPENAI_API_KEY"):
        st.error("请先在左侧输入 OpenAI API Key")
    else:
        st.session_state.running = True
        st.session_state.report = None

        # 模拟控制台输出区域
        st.subheader("调研日志")
        log_placeholder = st.empty()
        log_buffer = []

        class StreamlitSink:
            def write(self, text):
                if text.strip():  # 避免过多的空行刷新
                    log_buffer.append(text)
                    # 实时刷新日志区域，保留最新的 200 行以防页面卡顿
                    log_placeholder.code("".join(log_buffer[-200:]), language=None)

            def flush(self):
                pass

        try:
            from rich.console import Console

            agent = ResearchAgent(user_goal=goal, max_loops=max_loops)

            # 重定向 agent 的 console 输出到 Streamlit 界面
            # force_terminal=False 确保输出纯文本（无 ANSI 颜色代码）
            # width=80 适配一般的显示宽度
            agent.console = Console(file=StreamlitSink(), force_terminal=False, width=100)

            # 使用 spinner 提示正在运行，但不占用主输出区
            with st.spinner("Agent 正在思考和调研中..."):
                final_report = agent.run()
                st.session_state.report = final_report

        except Exception as e:
            st.error(f"发生错误: {e}")
        finally:
            st.session_state.running = False
            st.rerun()

# 展示结果
if st.session_state.report:
    st.success("调研完成！")
    st.divider()
    st.header("调研报告")
    st.markdown(st.session_state.report)

    st.download_button(
        label="下载报告 (Markdown)",
        data=st.session_state.report,
        file_name="research_report.md",
        mime="text/markdown"
    )
