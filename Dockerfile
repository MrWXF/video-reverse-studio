# ReelReverse 生产镜像
# 构建在腾讯云服务器上执行，默认使用国内 PyPI 镜像加速。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

# ffmpeg/ffprobe：分镜检测、关键帧抽取、音频提取依赖
# curl：容器健康检查依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app

# 依赖以 pyproject.toml 为唯一来源，避免清单漂移。
# 运行时使用 /app/app 源码（shadow site-packages 中的安装副本），
# 保证 templates/static/prompts 与源码完全一致。
RUN pip install --no-cache-dir .

EXPOSE 8900

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8900/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8900"]
