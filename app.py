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

    max_loops = st.slider("最大循环次数", min_value=1, max_value=20, value=5)

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

        # 容器用于显示动态进展
        progress_container = st.container()
        findings_container = st.container()

        try:
            agent = ResearchAgent(user_goal=goal, max_loops=max_loops)

            # 使用占位符实现动态刷新
            with st.spinner("调研中..."):
                # 注意：为了让 Streamlit 能实时展示内容，这里需要修改 agent 逻辑或者在循环中读取文件
                # 简单方案：在一个线程中运行 agent，在主线程轮询文件
                # 创空间方案：直接运行并定期刷新页面显示

                # 运行 agent (阻塞直到完成)
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

# 实时进展展示区域 (如果正在运行或已完成但想看中间过程)
if goal:
    st.divider()
    c1, c2 = st.columns(2)

    state = StateManager()

    with c1:
        st.subheader("实时进度 (Progress)")
        progress_text = state.read_progress()
        st.text_area("Progress Content", progress_text, height=300, label_visibility="collapsed")

    with c2:
        st.subheader("中间发现 (Findings)")
        findings_text = state.read_findings()
        st.markdown(findings_text)
