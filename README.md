---
deployspec:
  entry_file: src/deep_research/gui.py
license: MIT
---
# Deep Research Agent

A deep autonomous research agent powered by Large Language Models.

## Configuration

To run this agent, you need to configure the following environment variables in the ModelScope Studio settings:

- `OPENAI_API_KEY`: Your OpenAI API key (or compatible).
- `OPENAI_BASE_URL`: (Optional) Base URL for the LLM API (default: `https://api-inference.modelscope.cn/v1`).
- `MODEL_NAME`: (Optional) Model name to use (default: `Qwen/Qwen3-30B-A3B-Instruct-2507`).

## Features

- **Autonomous Research**: Breaks down complex topics into sub-tasks.
- **Deep Web Search**: scours the web for relevant information.
- **Synthesis**: Compiles findings into a comprehensive report.
- **UI**: Easy to use Streamlit interface.

## Local Development

```bash
# Install dependencies
uv sync

# Run the CLI
uv run deep-research "Your research goal"

# Run the GUI
uv run streamlit run src/deep_research/gui.py
```