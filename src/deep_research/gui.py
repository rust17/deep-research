import os
import queue
import sys
import threading
import time
from pathlib import Path

import streamlit as st

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.deep_research.orchestrator import Orchestrator
from src.deep_research.stream_handler import Event, Pulse, StreamHandler


def run_agent_thread(goal, max_loops, event_queue, stop_event):
    """Worker thread function to run the agent."""
    try:
        handler = StreamHandler()
        # Forward pulses to the main thread via queue
        handler.subscribe(lambda pulse: event_queue.put(pulse))

        agent = Orchestrator(
            user_goal=goal,
            max_loops=max_loops,
            stream_handler=handler,
            stop_event=stop_event,
        )
        # run() returns the final report, but we also rely on the FINISH event
        agent.run()
    except Exception as e:
        # Send error to queue so UI can show it
        event_queue.put(Pulse(type=Event.ERROR, content=str(e), name="Fatal Error"))


def render_event(pulse, index, completed_actions, status_container, status_stack):
    """Renders a single event to the container."""
    with status_container:
        if pulse.type == Event.INIT:
            st.info(f"🚀 调研启动: {pulse.content.get('goal')}")

        elif pulse.type == Event.THOUGHT:
            with st.chat_message("assistant"):
                # 为子智能体的思考增加标识
                is_sub = pulse.name.startswith("[SubAgent]")
                prefix = "🧪 **子任务思考**" if is_sub else "🤔 **思考**"
                step = pulse.metadata.get("step", "?")
                st.markdown(f"{prefix} (步骤 {step}):\n{pulse.content}")

        elif pulse.type == Event.ACTION:
            # 检查该动作是否在后续事件中已完成
            final_pulse = completed_actions.get(index)

            if final_pulse:
                # 已完成的动作：直接渲染最终状态
                if final_pulse.type == Event.OBSERVATION:
                    label = f"✅ 工具 {pulse.name} 执行完毕 (耗时: {final_pulse.metadata.get('duration', 0):.2f}s)"
                    state = "complete"
                else:
                    label = f"❌ 工具执行出错: {pulse.name}"
                    state = "error"

                with st.status(label, state=state, expanded=False):
                    st.write(f"**参数:** {pulse.content}")
                    if final_pulse.type == Event.OBSERVATION:
                        st.write("**结果:**")
                        # 如果结果是字典且包含 text，优先显示 text
                        obs_content = final_pulse.content
                        if isinstance(obs_content, dict) and "text" in obs_content:
                            st.write(obs_content["text"])
                            if "metadata" in obs_content:
                                with st.expander("查看详细数据"):
                                    st.write(obs_content["metadata"])
                        else:
                            st.write(obs_content)
                    else:
                        st.error(f"**错误:** {final_pulse.content}")
            else:
                # 正在运行的动作
                status = st.status(
                    f"🛠️ 正在调用工具: {pulse.name}...", expanded=True, state="running"
                )
                status.write(f"参数: {pulse.content}")
                status_stack.append(status)

        elif pulse.type == Event.OBSERVATION:
            if status_stack:
                status = status_stack.pop()
                status.update(
                    label=f"✅ 工具 {pulse.name} 执行完毕 (耗时: {pulse.metadata.get('duration', 0):.2f}s)",
                    state="complete",
                )
                with status:
                    obs_content = pulse.content
                    if isinstance(obs_content, dict) and "text" in obs_content:
                        st.write(obs_content["text"])
                    else:
                        st.write(obs_content)

        elif pulse.type == Event.STEP:
            # st.divider()
            pass

        elif pulse.type == Event.INFO:
            # 只有短文本才使用 toast
            if isinstance(pulse.content, str) and len(pulse.content) < 100:
                st.toast(f"{pulse.name}: {pulse.content}" if pulse.name else pulse.content)
            else:
                with st.expander(f"ℹ️ 状态更新: {pulse.name or '详情'}", expanded=False):
                    st.write(pulse.content)

        elif pulse.type == Event.WARN:
            st.warning(pulse.content)

        elif pulse.type == Event.ERROR:
            if status_stack:
                status = status_stack.pop()
                status.update(label=f"❌ 工具执行出错: {pulse.name}", state="error")
            st.error(f"⚠️ 错误: {pulse.content}")

        elif pulse.type == Event.FINISH:
            st.success("🏁 调研任务完成！")


def run_app():
    # 页面配置
    st.set_page_config(page_title="Deep Research Agent", page_icon="🔍", layout="wide")

    st.title("🔍 Deep Research Agent")

    # 侧边栏配置
    with st.sidebar:
        st.header("配置")
        api_key = st.text_input("OpenAI API Key", type="password")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

        base_url = st.text_input(
            "Base URL",
            value=os.getenv("OPENAI_BASE_URL", "https://api-inference.modelscope.cn/v1"),
            autocomplete="off",
        )
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url

        model_name = st.text_input(
            "模型名称 (Model Name)",
            value=os.getenv("MODEL_NAME", "Qwen/Qwen3.5-122B-A10B"),
            autocomplete="off",
        )
        if model_name:
            os.environ["MODEL_NAME"] = model_name

        st.slider("最大循环次数", min_value=1, max_value=20, value=10, key="max_loops_slider")

        st.info(f"默认使用 {model_name} 进行研究，你也可以配置模型进行深度调研")

    # 初始化状态
    if "running" not in st.session_state:
        st.session_state.running = False
    if "report" not in st.session_state:
        st.session_state.report = None
    if "events" not in st.session_state:
        st.session_state.events = []
    if "event_queue" not in st.session_state:
        st.session_state.event_queue = queue.Queue()
    if "stop_event" not in st.session_state:
        st.session_state.stop_event = threading.Event()
    if "research_thread" not in st.session_state:
        st.session_state.research_thread = None

    # 主界面逻辑
    st.text_input("请输入您的调研目标:", key="goal_input", autocomplete="off")

    col1, col2 = st.columns(2)

    def start_research():
        st.session_state.running = True
        st.session_state.report = None
        st.session_state.events = []
        st.session_state.stop_event.clear()
        # 清除之前的线程引用（如果是重新开始）
        st.session_state.research_thread = None
        # 清空队列
        while not st.session_state.event_queue.empty():
            st.session_state.event_queue.get()

    def stop_research():
        st.session_state.stop_event.set()

    with col1:
        st.button("开始调研", on_click=start_research, disabled=st.session_state.running)

    with col2:
        if st.session_state.running:
            st.button("停止调研", on_click=stop_research, type="primary")

    if st.session_state.running:
        if not st.session_state.goal_input:
            st.error("请输入调研目标")
            st.session_state.running = False
            st.rerun()
            return

        if not os.environ.get("OPENAI_API_KEY"):
            st.error("请先在左侧输入 OpenAI API Key")
            st.session_state.running = False
            st.rerun()
            return

        # 启动线程（如果尚未运行）
        if (
            st.session_state.research_thread is None
            or not st.session_state.research_thread.is_alive()
        ):
            if len(st.session_state.events) == 0:
                t = threading.Thread(
                    target=run_agent_thread,
                    args=(
                        st.session_state.goal_input,
                        st.session_state.max_loops_slider,
                        st.session_state.event_queue,
                        st.session_state.stop_event,
                    ),
                    daemon=True,
                )
                t.start()
                st.session_state.research_thread = t

        # 调研动态展示区域
        st.subheader("调研动态")
        status_container = st.container()

        # 处理队列中的新事件
        while not st.session_state.event_queue.empty():
            pulse = st.session_state.event_queue.get()
            st.session_state.events.append(pulse)
            if pulse.type == Event.FINISH:
                st.session_state.report = pulse.content
                st.session_state.running = False

        # 预处理事件列表：找出已完成的 ACTION 及其对应的结束事件（OBSERVATION 或 ERROR）
        completed_actions = {}  # index of ACTION -> final Pulse (OBSERVATION/ERROR)
        action_stack = []
        for i, pulse in enumerate(st.session_state.events):
            if pulse.type == Event.ACTION:
                action_stack.append(i)
            elif pulse.type in [Event.OBSERVATION, Event.ERROR] and action_stack:
                idx = action_stack.pop()
                completed_actions[idx] = pulse

        # 渲染所有事件（回放）
        status_stack = []
        for i, pulse in enumerate(st.session_state.events):
            render_event(pulse, i, completed_actions, status_container, status_stack)

        # 自动刷新以获取新事件
        if st.session_state.running:
            time.sleep(1)
            st.rerun()

    # 展示结果
    if st.session_state.report:
        if st.session_state.running:
            # 如果 report 存在但 running 仍为 True（可能是刚刚 finish 还没设为 False），在上面循环里应该已经处理了
            pass
        else:
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

            # 展示过程事件记录
            st.divider()
            with st.expander("查看结构化执行记录", expanded=False):
                for i, pulse in enumerate(st.session_state.events):
                    st.write(f"{i + 1}. **{pulse.type.value}** - {pulse.to_dict()}")


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
