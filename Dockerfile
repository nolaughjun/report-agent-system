# Dockerfile - 生产环境部署
# 报告智能体系统 v2.0

FROM python:3.11-slim

# 元数据
LABEL maintainer="Report Agent Team"
LABEL version="2.0"
LABEL description="并发版本报告智能体系统"

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # 应用环境
    APP_HOME=/app \
    # 安全配置
    DEBUG=false \
    # 日志级别
    LOG_LEVEL=INFO

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # LaTeX 支持（PDF 导出）
    texlive-xetex \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-lang-chinese \
    # Pandoc（文档转换）
    pandoc \
    # 字体支持
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    # 其他工具
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建应用目录
WORKDIR ${APP_HOME}

# 创建非 root 用户
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    # 安全检查工具
    && pip install pip-audit safety

# 复制应用代码
COPY . .

# 创建必要目录并设置权限
RUN mkdir -p outputs logs \
    && chown -R appuser:appgroup ${APP_HOME}

# 切换到非 root 用户
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# 暴露端口
EXPOSE ${PORT:-8000}

# 启动命令
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "${PORT:-8000}"]
