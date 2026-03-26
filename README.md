---
tags:
  - Agent
  - Research
  - LLM
  - DeepResearch
deployspec:
  entry_file: src/deep_research/gui.py
license: MIT
---

# Deep Research Agent

An autonomous research assistant powered by LLMs, designed to perform deep information gathering, multi-step reasoning, and structured report synthesis.

[**🌐 Try it Online**](https://modelscope.cn/studios/rust17/deep-research)

## 🌟 Key Features

- **Autonomous Orchestration**: The `Orchestrator` engine recursively breaks down complex user goals into actionable sub-tasks.
- **Real-time Event Streaming**: Powered by a custom `StreamHandler`, providing live feedback on Thoughts, Actions, and tool outputs.
- **Powerful Toolset**:
  - **Smart Search**: Integrated with DuckDuckGo for up-to-date web discovery.
  - **High-Precision Scraping**: Uses `Trafilatura` and `Playwright` for clean content extraction and JavaScript rendering support.
  - **Multi-Format Parsing**: Built-in support for PDF analysis and Markdown conversion via `MarkItDown`.
- **Interactive UI**: A modern Streamlit-based dashboard for visualizing the research process and managing loops.

## 🛠️ Technical Stack

- **Core**: Python 3.12+
- **Agent Framework**: Custom orchestration with OpenAI-compatible API integration.
- **UI**: Streamlit
- **Package Management**: [uv](https://github.com/astral-sh/uv)

## 🚀 Quick Start

### 1. Installation

Ensure you have [uv](https://github.com/astral-sh/uv) installed, then run:

```bash
# Clone the repository
git clone <repo-url>
cd deep-research

# Install dependencies and setup virtual environment
uv sync
```

### 2. Configuration

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o  # Or your preferred model
```

### 3. Usage

Start the interactive research interface:

```bash
uv run dr
```

## 📂 Project Structure

- `src/deep_research/`
  - `orchestrator.py`: Main logic for the autonomous research loop.
  - `gui.py`: Streamlit frontend implementation.
  - `stream_handler.py`: Event-driven system for real-time UI updates.
  - `tools/`: Extensible tool modules (Search, Visit, etc.).
  - `llm_client.py`: Unified LLM interaction layer.

## 🔗 Reference

- [MiroThinker](https://github.com/MiroMindAI/MiroThinker)

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
