# 使用官方 uv 镜像
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV STREAMLIT_SERVER_PORT=7860
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# 安装基础系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 拷贝依赖文件
COPY pyproject.toml uv.lock ./

# 使用 uv 同步依赖
RUN uv sync --frozen --no-install-project --no-dev

# 拷贝项目源码
COPY . .

# 安装项目本身
RUN uv sync --frozen --no-dev

# 安装 Playwright 浏览器及其系统依赖
RUN uv run playwright install --with-deps chromium

# 暴露端口
EXPOSE 7860

# 启动命令

CMD ["uv", "run", "dr", "--server.port=7860", "--server.address=0.0.0.0"]