import os
import sys
from pathlib import Path

import streamlit as st

# Add project root to sys.path
# Assuming this file is at src/deep_research/gui.py
# We want to add the directory containing 'src' (which is the project root)
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.deep_research.orchestrator import Orchestrator
from src.deep_research.stream_handler import Event, EventType, StreamHandler


def run_app():
    # 页面配置
    st.set_page_config(page_title="Deep Research Agent", page_icon="🔍", layout="wide")

    st.title("🔍 Deep Research Agent")
    st.markdown("基于大模型的深度自主调研工具")

    # 侧边栏配置
    with st.sidebar:
        st.header("配置")
        api_key = st.text_input("OpenAI API Key", type="password")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

        base_url = st.text_input(
            "Base URL", value=os.getenv("OPENAI_BASE_URL", "https://api-inference.modelscope.cn/v1")
        )
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url

        large_model = st.text_input(
            "Large Model (指挥)",
            value=os.getenv("LARGE_MODEL_NAME", "Qwen/Qwen3-235B-A22B-Instruct-2507"),
        )
        if large_model:
            os.environ["LARGE_MODEL_NAME"] = large_model

        small_model = st.text_input(
            "Small Model (总结)",
            value=os.getenv("SMALL_MODEL_NAME", "Qwen/Qwen3-30B-A3B-Instruct-2507"),
        )
        if small_model:
            os.environ["SMALL_MODEL_NAME"] = small_model

        context_limit = st.text_input(
            "指挥模型的最大上下文",
            value=os.getenv("LARGE_MODEL_CONTEXT_LIMIT", 262144),
        )
        if context_limit:
            os.environ["LARGE_MODEL_CONTEXT_LIMIT"] = context_limit

        max_loops = st.slider("最大循环次数", min_value=1, max_value=20, value=10)

        st.info("指挥模型负责决策，总结模型负责处理长文本和搜索提取。")

    # 初始化状态
    if "running" not in st.session_state:
        st.session_state.running = False
    if "report" not in st.session_state:
        st.session_state.report = None
    if "events" not in st.session_state:
        st.session_state.events = []

    # 主界面逻辑
    goal = st.text_input(
        "请输入您的调研目标:",
        placeholder="例如：2025年全球生成式AI market development trend research",
    )

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
            st.session_state.events = []  # 清空旧事件

            # 调研动态展示区域
            st.subheader("调研动态")
            status_container = st.container()

            # 使用 StreamHandler
            handler = StreamHandler()

            def streamlit_callback(event: Event):
                st.session_state.events.append(event)

                with status_container:
                    if event.type == EventType.WORKFLOW_START:
                        st.info(f"🚀 调研启动: {event.data.get('goal')}")

                    elif event.type == EventType.AGENT_THINK:
                        with st.chat_message("assistant"):
                            st.markdown(
                                f"**思考 (步骤 {event.data.get('step')}):**\n{event.data.get('thought')}"
                            )

                    elif event.type == EventType.TOOL_START:
                        st.status(
                            f"🛠️ 正在调用工具: {event.data.get('tool')}...", expanded=True
                        ).write(f"参数: {event.data.get('parameters')}")

                    elif event.type == EventType.TOOL_END:
                        if event.data.get("status") == "success":
                            st.success(
                                f"✅ 工具 {event.data.get('tool')} 执行完毕 (耗时: {event.data.get('duration', 0):.2f}s)"
                            )
                            with st.expander("查看执行结果"):
                                st.write(event.data.get("result"))
                        else:
                            st.error(
                                f"❌ 工具 {event.data.get('tool')} 执行失败: {event.data.get('error')}"
                            )

                    elif event.type == EventType.INFO:
                        st.toast(event.data.get("message"))

                    elif event.type == EventType.ERROR:
                        st.error(f"⚠️ 错误: {event.data.get('message')}")

                    elif event.type == EventType.WORKFLOW_END:
                        st.success("🏁 调研任务完成！")

            handler.subscribe(streamlit_callback)

            try:
                agent = Orchestrator(user_goal=goal, max_loops=max_loops, stream_handler=handler)

                with st.spinner("Agent 正在执行中..."):
                    final_report = agent.run()
                    st.session_state.report = final_report

            except Exception as e:
                st.error(f"发生致命错误: {e}")
                import traceback

                st.code(traceback.format_exc())
            finally:
                st.session_state.running = False
                if st.session_state.report:
                    st.rerun()

    # 展示结果
    if st.session_state.report:
        st.success("调研完成！")

        # 展示调研报告
        st.divider()
        st.header("调研报告")
        st.markdown(st.session_state.report)

        st.download_button(
            label="下载报告 (Markdown)",
            data=st.session_state.report,
            file_name="research_report.md",
            mime="text/markdown",
        )

        # 展示过程事件记录 (替代旧的日志)
        st.divider()
        with st.expander("查看结构化执行记录", expanded=False):
            for i, event in enumerate(st.session_state.events):
                st.write(f"{i + 1}. **{event.type.value}** - {event.data}")


def main():
    import contextlib
    import subprocess
    import sys
    from pathlib import Path

    # If running inside streamlit, execute the app logic
    if st.runtime.exists():
        run_app()
        return

    # Otherwise, launch streamlit
    file_path = Path(__file__).resolve()
    cmd = [sys.executable, "-m", "streamlit", "run", str(file_path)] + sys.argv[1:]
    with contextlib.suppress(KeyboardInterrupt):
        subprocess.run(cmd)


if __name__ == "__main__":
    main()
