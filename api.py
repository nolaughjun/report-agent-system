# API 服务 - 生产环境部署
"""API 服务

提供 REST API 接口用于：
- 创建报告任务（异步）
- 查询任务状态
- 管理模型配置
- 数据源管理
- 安全审计

支持并发：
- 任务提交到 Celery 队列
- Redis 状态持久化
- API 限流和用户配额
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# 配置日志
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 安全认证
security = HTTPBearer(auto_error=False)

# 限流配置
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", 60))  # 每分钟请求数


# ══════════════════════════════════════════════════════════════
# 请求/响应模型
# ══════════════════════════════════════════════════════════════

class CreateReportRequest(BaseModel):
    """创建报告请求"""
    topic: str = Field(..., min_length=1, max_length=200, description="报告主题")
    abstract: str = Field("", max_length=500, description="报告概要")
    report_type: str = Field("research", description="报告类型")
    language: str = Field("中文", description="语言")
    quality_threshold: float = Field(0.55, ge=0.0, le=1.0, description="质量阈值")
    max_retry: int = Field(3, ge=0, le=10, description="最大重试次数")
    max_concurrent: int = Field(5, ge=1, le=10, description="最大并发数")
    model: Optional[str] = Field(None, description="使用的模型")


class ReportResponse(BaseModel):
    """报告响应"""
    thread_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    thread_id: str
    current_step: str
    retry_count: int
    draft_length: int
    quality_score: Optional[float]
    export_path: Optional[str]
    token_usage: dict


class ModelInfo(BaseModel):
    """模型信息"""
    id: str
    name: str
    provider: str
    available: bool


class DataSourceInfo(BaseModel):
    """数据源信息"""
    id: str
    name: str
    source_type: str
    available: bool
    priority: int


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    timestamp: str
    version: str
    model: str
    data_sources: list[str]


# ══════════════════════════════════════════════════════════════
# 应用生命周期
# ══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("[API] 报告智能体服务启动")
    logger.info("[API] 可用模型: %s", get_available_models())
    logger.info("[API] 可用数据源: %s", get_available_data_sources())
    logger.info("[API] 限流状态: %s", "启用" if RATE_LIMIT_ENABLED else "禁用")

    # 检查 Redis 连接
    if os.environ.get("REDIS_URL"):
        try:
            from redis_client import check_redis_connection
            if check_redis_connection():
                logger.info("[API] Redis 连接正常")
            else:
                logger.warning("[API] Redis 连接失败，使用降级模式")
        except Exception as e:
            logger.warning(f"[API] Redis 检查失败: {e}")

    # 初始化数据库
    if os.environ.get("DATABASE_URL"):
        try:
            from database import init_database, check_database_connection
            if check_database_connection():
                init_database()
                logger.info("[API] 数据库初始化完成")
        except Exception as e:
            logger.warning(f"[API] 数据库初始化失败: {e}")

    # 运行安全检查
    from security import run_security_audit
    report = run_security_audit()
    if not report.passed:
        logger.warning("[API] 安全检查发现问题: %s", report.summary)
    else:
        logger.info("[API] 安全检查通过")

    yield

    # 关闭时
    logger.info("[API] 报告智能体服务关闭")


# ══════════════════════════════════════════════════════════════
# FastAPI 应用
# ══════════════════════════════════════════════════════════════

app = FastAPI(
    title="报告智能体 API",
    description="并发版本报告智能体系统 REST API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
# 请求日志中间件
# ══════════════════════════════════════════════════════════════

from starlette.middleware.base import BaseHTTPMiddleware
import time


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件

    记录每个请求的方法、路径、状态码和处理时间。
    """

    async def dispatch(self, request: Request, call_next):
        # 记录请求开始
        start_time = time.perf_counter()

        # 获取客户端 IP
        client_ip = request.headers.get("X-Forwarded-For", "")
        if client_ip:
            client_ip = client_ip.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host
        else:
            client_ip = "unknown"

        # 处理请求
        response = await call_next(request)

        # 计算处理时间
        process_time = (time.perf_counter() - start_time) * 1000

        # 记录请求日志
        logger.info(
            "[API] %s %s - %d - %.2fms - %s",
            request.method,
            request.url.path,
            response.status_code,
            process_time,
            client_ip
        )

        # 添加处理时间头
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

        return response


# 添加请求日志中间件
app.add_middleware(RequestLoggingMiddleware)


# ══════════════════════════════════════════════════════════════
# 依赖注入
# ══════════════════════════════════════════════════════════════

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证 API Key"""
    if not credentials:
        # 如果没有配置认证，跳过
        if not os.environ.get("API_KEY"):
            return None
        raise HTTPException(status_code=401, detail="Missing API Key")

    expected_key = os.environ.get("API_KEY", "")
    if expected_key and credentials.credentials != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    return credentials.credentials


async def check_rate_limit(request: Request):
    """检查限流"""
    if not RATE_LIMIT_ENABLED:
        return None

    from rate_limit import check_rate_limit_ip, get_client_ip

    ip = get_client_ip(request)
    allowed, info = check_rate_limit_ip(ip, RATE_LIMIT_REQUESTS)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Too Many Requests",
                "message": f"请求过于频繁，请 {info.get('retry_after', 60)} 秒后重试",
                "retry_after": info.get("retry_after", 60),
            },
            headers={"Retry-After": str(info.get("retry_after", 60))}
        )

    return info


async def check_user_quota_dependency(request: Request, api_key: str = Depends(verify_api_key)):
    """检查用户配额"""
    # 从请求头获取用户 ID
    user_id = request.headers.get("X-User-ID") or api_key

    if user_id:
        from rate_limit import check_user_quota

        allowed, info = check_user_quota(user_id)

        if not allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Quota Exceeded",
                    "message": info.get("message", "用户配额已用尽"),
                    **info
                }
            )

        return {"user_id": user_id, "quota_info": info}

    return {"user_id": None, "quota_info": {"quota": "unlimited"}}


# ══════════════════════════════════════════════════════════════
# 延迟导入（避免启动时加载所有模块）
# ══════════════════════════════════════════════════════════════

def get_available_models():
    from tools.llm import get_available_models
    return get_available_models()


def get_available_data_sources():
    from tools.llm import get_available_data_sources
    return get_available_data_sources()


# ══════════════════════════════════════════════════════════════
# API 路由
# ══════════════════════════════════════════════════════════════

@app.get("/api/health", response_model=HealthResponse, tags=["系统"])
async def health_check():
    """健康检查"""
    from tools.llm import get_current_model

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC).isoformat(),
        version="2.0.0",
        model=get_current_model(),
        data_sources=get_available_data_sources(),
    )


@app.post("/api/reports", response_model=ReportResponse, tags=["报告"])
async def create_report(
    request: Request,
    body: CreateReportRequest,
    rate_limit_info: dict = Depends(check_rate_limit),
    user_info: dict = Depends(check_user_quota_dependency),
):
    """创建报告任务（异步）

    任务将提交到 Celery 队列异步执行，立即返回任务 ID。
    使用 GET /api/reports/{thread_id} 查询任务状态。

    限流: 每分钟 {RATE_LIMIT_REQUESTS} 次请求
    """
    from tools.llm import set_current_model
    from security import check_input_injection, sanitize_output

    # 输入安全检查
    issues = check_input_injection(body.topic)
    high_severity = [i for i in issues if i.severity in ["CRITICAL", "HIGH"]]
    if high_severity:
        raise HTTPException(
            status_code=400,
            detail=f"输入包含潜在危险内容: {high_severity[0].description}"
        )

    # 设置模型
    if body.model:
        if not set_current_model(body.model):
            raise HTTPException(status_code=400, detail=f"模型 {body.model} 不可用")

    # 获取用户 ID
    user_id = user_info.get("user_id")

    try:
        # 检查是否启用 Celery
        use_celery = os.environ.get("REDIS_URL") is not None

        if use_celery:
            # 提交到 Celery 任务队列
            from tasks import generate_report_task

            task = generate_report_task.delay(
                topic=sanitize_output(body.topic),
                abstract=sanitize_output(body.abstract),
                report_type=body.report_type,
                language=body.language,
                quality_threshold=body.quality_threshold,
                max_retry=body.max_retry,
                max_concurrent=body.max_concurrent,
                user_id=user_id,
            )

            thread_id = task.id[:8]

            logger.info(f"[API] 任务已提交到队列: {thread_id}, 用户: {user_id}")

            return ReportResponse(
                thread_id=thread_id,
                status="pending",
                message="任务已提交，正在处理中",
            )
        else:
            # 降级模式：同步执行
            from graph import create_report_task

            thread_id = create_report_task(
                topic=sanitize_output(body.topic),
                abstract=sanitize_output(body.abstract),
                report_type=body.report_type,
                language=body.language,
                quality_threshold=body.quality_threshold,
                max_retry=body.max_retry,
                max_concurrent=body.max_concurrent,
            )

            return ReportResponse(
                thread_id=thread_id,
                status="created",
                message="报告任务已创建，等待人工审核",
            )

    except Exception as e:
        logger.error("[API] 创建任务失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/{thread_id}", tags=["报告"])
async def get_report_status(
    thread_id: str,
    authorized: bool = Depends(verify_api_key),
):
    """获取报告任务状态

    支持两种模式：
    - Celery 模式：从 Celery 任务结果获取状态
    - 降级模式：从 LangGraph 状态获取
    """
    use_celery = os.environ.get("REDIS_URL") is not None

    if use_celery:
        # 从 Celery 获取任务状态
        from tasks import get_task_status

        task_status = get_task_status(thread_id)

        if task_status.get("state") == "PENDING":
            # 尝试从 LangGraph 获取（可能是任务 ID 不完整）
            from graph import get_task_state

            state = get_task_state(thread_id)
            if state:
                return _format_state_response(thread_id, state)

        return task_status
    else:
        # 降级模式：从 LangGraph 状态获取
        from graph import get_task_state, get_token_usage_summary

        state = get_task_state(thread_id)

        if not state:
            raise HTTPException(status_code=404, detail="任务不存在")

        return _format_state_response(thread_id, state)


def _format_state_response(thread_id: str, state: dict) -> dict:
    """格式化状态响应"""
    from graph import get_token_usage_summary

    quality_checks = state.get("quality_checks", [])
    last_quality = quality_checks[-1] if quality_checks else None

    token_summary = get_token_usage_summary(thread_id)

    return {
        "thread_id": thread_id,
        "current_step": state.get("current_step", "unknown"),
        "status": "waiting_review" if state.get("current_step") == "reviewing" else state.get("current_step", "unknown"),
        "retry_count": state.get("retry_count", 0),
        "draft_length": len(state.get("current_draft", "")),
        "quality_score": last_quality.get("score") if last_quality else None,
        "export_path": state.get("export_path"),
        "token_usage": token_summary,
    }


@app.post("/api/reports/{thread_id}/resume", tags=["报告"])
async def resume_report(
    thread_id: str,
    decision: str = "approve",
    comments: str = "",
    authorized: bool = Depends(verify_api_key),
):
    """恢复报告任务执行

    提交人工审核决策后继续执行。
    """
    from security import sanitize_output

    if decision not in ["approve", "revise"]:
        raise HTTPException(status_code=400, detail="决策必须是 approve 或 revise")

    try:
        use_celery = os.environ.get("REDIS_URL") is not None

        if use_celery:
            # 提交到 Celery 队列
            from tasks import resume_report_task

            task = resume_report_task.delay(thread_id, decision, sanitize_output(comments))

            logger.info(f"[API] 恢复任务已提交: {thread_id}, 决策: {decision}")

            return {
                "thread_id": thread_id,
                "task_id": task.id,
                "status": "resuming",
                "message": f"正在执行决策: {decision}",
            }
        else:
            # 降级模式：同步执行
            from graph import resume_with_decision

            result = resume_with_decision(
                thread_id,
                decision,
                sanitize_output(comments)
            )

            return {
                "thread_id": thread_id,
                "current_step": result.get("current_step"),
                "export_path": result.get("export_path"),
            }

    except Exception as e:
        logger.error("[API] 恢复任务失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models", response_model=list[ModelInfo], tags=["配置"])
async def list_models(authorized: bool = Depends(verify_api_key)):
    """列出可用模型"""
    from tools.llm import MODEL_CONFIGS, get_available_models

    available = get_available_models()

    return [
        ModelInfo(
            id=model_id,
            name=config.name,
            provider=config.provider,
            available=model_id in available,
        )
        for model_id, config in MODEL_CONFIGS.items()
    ]


@app.post("/api/models/{model_id}/select", tags=["配置"])
async def select_model(
    model_id: str,
    authorized: bool = Depends(verify_api_key),
):
    """选择使用的模型"""
    from tools.llm import set_current_model

    if not set_current_model(model_id):
        raise HTTPException(status_code=400, detail=f"模型 {model_id} 不可用")

    return {"message": f"已切换到模型 {model_id}"}


@app.get("/api/data-sources", response_model=list[DataSourceInfo], tags=["配置"])
async def list_data_sources(authorized: bool = Depends(verify_api_key)):
    """列出可用数据源"""
    from tools.llm import DATA_SOURCES, get_available_data_sources

    available = get_available_data_sources()

    return [
        DataSourceInfo(
            id=source_id,
            name=config.name,
            source_type=config.source_type,
            available=source_id in available,
            priority=config.priority,
        )
        for source_id, config in DATA_SOURCES.items()
    ]


@app.get("/api/security/audit", tags=["安全"])
async def run_audit(authorized: bool = Depends(verify_api_key)):
    """运行安全审计"""
    from security import run_security_audit

    report = run_security_audit()

    return report.to_dict()


@app.get("/api/reports/{thread_id}/download", tags=["报告"])
async def download_report(
    thread_id: str,
    format: str = "pdf",
    authorized: bool = Depends(verify_api_key),
):
    """下载报告文件"""
    from graph import get_task_state

    state = get_task_state(thread_id)

    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")

    export_path = state.get("export_path")
    if not export_path:
        raise HTTPException(status_code=404, detail="报告文件不存在")

    import os

    if format == "pdf":
        file_path = export_path.replace(".md", ".pdf")
    else:
        file_path = export_path

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        file_path,
        filename=os.path.basename(file_path),
        media_type="application/pdf" if format == "pdf" else "text/markdown",
    )


# ══════════════════════════════════════════════════════════════
# LangSmith 监控端点
# ══════════════════════════════════════════════════════════════


@app.get("/api/monitoring/status", tags=["监控"])
async def get_monitoring_status():
    """获取监控状态"""
    from langsmith_client import is_enabled, LANGSMITH_PROJECT, get_project_stats

    return {
        "enabled": is_enabled(),
        "project": LANGSMITH_PROJECT if is_enabled() else None,
        "stats": get_project_stats() if is_enabled() else None,
    }


@app.get("/api/monitoring/traces/{run_id}", tags=["监控"])
async def get_trace(run_id: str):
    """获取追踪详情"""
    from langsmith_client import get_trace

    trace = get_trace(run_id)
    if not trace:
        raise HTTPException(status_code=404, detail="追踪不存在")

    return {
        "run_id": trace.run_id,
        "name": trace.name,
        "run_type": trace.run_type,
        "inputs": trace.inputs,
        "outputs": trace.outputs,
        "start_time": trace.start_time,
        "end_time": trace.end_time,
        "latency_ms": trace.latency_ms,
        "total_tokens": trace.total_tokens,
        "error": trace.error,
    }


@app.post("/api/monitoring/feedback", tags=["监控"])
async def create_feedback(
    run_id: str,
    key: str,
    score: float,
    comment: str = "",
):
    """记录反馈"""
    from langsmith_client import record_feedback

    success = record_feedback(run_id, key, score, comment)
    if not success:
        raise HTTPException(status_code=400, detail="记录反馈失败")

    return {"status": "success", "run_id": run_id, "key": key, "score": score}


@app.get("/api/monitoring/export", tags=["监控"])
async def export_traces(format: str = "json"):
    """导出追踪数据"""
    from langsmith_client import export_traces

    data = export_traces(format)

    from fastapi.responses import Response

    media_type = "application/json" if format == "json" else "text/csv"
    filename = f"traces.{format}"

    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ══════════════════════════════════════════════════════════════
# Wiki 知识库端点
# ══════════════════════════════════════════════════════════════


class WikiSearchRequest(BaseModel):
    """Wiki 搜索请求"""
    query: str = Field(..., min_length=1, max_length=500, description="搜索查询")
    category: Optional[str] = Field(None, description="分类过滤")
    limit: int = Field(10, ge=1, le=100, description="返回数量")


class WikiEntryResponse(BaseModel):
    """Wiki 条目响应"""
    id: str
    title: str
    content: str
    category: str
    keywords: list[str]
    relevance_score: float
    source_report_id: Optional[str]
    created_at: Optional[str]


@app.get("/api/wiki/stats", tags=["Wiki"])
async def get_wiki_stats():
    """获取 Wiki 知识库统计信息"""
    from wiki import get_wiki_stats

    stats = get_wiki_stats()
    return stats


@app.post("/api/wiki/search", response_model=list[WikiEntryResponse], tags=["Wiki"])
async def search_wiki(
    request: WikiSearchRequest,
    authorized: bool = Depends(verify_api_key),
):
    """搜索 Wiki 知识库"""
    from wiki import search_knowledge

    results = search_knowledge(
        query=request.query,
        category=request.category,
        limit=request.limit,
        use_semantic=True,
    )

    return [
        WikiEntryResponse(
            id=r.get("id", ""),
            title=r.get("title", ""),
            content=r.get("content", "")[:500] + "..." if len(r.get("content", "")) > 500 else r.get("content", ""),
            category=r.get("category", "general"),
            keywords=r.get("keywords", []),
            relevance_score=r.get("relevance_score", 0.0),
            source_report_id=r.get("source_report_id"),
            created_at=r.get("created_at"),
        )
        for r in results
    ]


@app.get("/api/wiki/entries/{entry_id}", tags=["Wiki"])
async def get_wiki_entry(entry_id: str):
    """获取单个 Wiki 条目"""
    # 从存储中获取
    from wiki import _knowledge_store

    if entry_id in _knowledge_store:
        return _knowledge_store[entry_id]

    # 尝试从数据库获取
    if os.environ.get("DATABASE_URL"):
        try:
            from database import get_db_session
            from models import WikiKnowledge

            with get_db_session() as session:
                entry = session.query(WikiKnowledge).filter_by(id=entry_id).first()
                if entry:
                    return entry.to_dict()
        except Exception as e:
            logger.error("[API] 获取 Wiki 条目失败: %s", e)

    raise HTTPException(status_code=404, detail="知识点不存在")


@app.post("/api/wiki/ingest/{report_id}", tags=["Wiki"])
async def ingest_report_to_wiki(
    report_id: str,
    authorized: bool = Depends(verify_api_key),
):
    """将指定报告入库到 Wiki 知识库"""
    from graph import get_task_state
    from wiki import auto_ingest_report

    # 获取报告内容
    state = get_task_state(report_id)

    if not state:
        raise HTTPException(status_code=404, detail="报告不存在")

    final_report = state.get("final_report") or state.get("current_draft")

    if not final_report:
        raise HTTPException(status_code=400, detail="报告内容为空")

    # 入库
    count = auto_ingest_report(
        report_content=final_report,
        report_id=report_id,
        report_title=state.get("topic", ""),
        report_type=state.get("report_type", "research"),
    )

    return {
        "status": "success",
        "report_id": report_id,
        "entries_created": count,
    }


@app.get("/api/wiki/categories", tags=["Wiki"])
async def get_wiki_categories():
    """获取 Wiki 知识库分类列表"""
    categories = [
        {"id": "general", "name": "通用", "description": "通用知识点"},
        {"id": "技术", "name": "技术", "description": "技术方案和架构"},
        {"id": "市场", "name": "市场", "description": "市场分析和趋势"},
        {"id": "数据", "name": "数据", "description": "数据统计和分析"},
        {"id": "风险", "name": "风险", "description": "风险和挑战分析"},
        {"id": "建议", "name": "建议", "description": "建议和对策"},
    ]

    return categories


@app.get("/api/wiki/recommend", tags=["Wiki"])
async def recommend_knowledge(
    topic: str,
    report_type: str = "research",
    limit: int = 5,
):
    """根据主题推荐相关知识"""
    from wiki import get_relevant_knowledge_for_topic

    results = get_relevant_knowledge_for_topic(
        topic=topic,
        report_type=report_type,
        max_entries=limit,
    )

    return {
        "topic": topic,
        "report_type": report_type,
        "recommendations": results,
    }


# ══════════════════════════════════════════════════════════════
# 异常处理
# ══════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理

    在生产环境中隐藏详细错误信息，防止敏感信息泄露。
    在 DEBUG 模式下提供更多信息以便调试。
    """
    # 生成唯一的请求追踪 ID
    import uuid
    trace_id = str(uuid.uuid4())[:8]

    # 记录详细错误日志（仅服务端可见）
    logger.error(
        "[API] 未处理的异常 [trace_id=%s]: %s",
        trace_id,
        str(exc),
        exc_info=True
    )

    # 构建响应内容
    if os.environ.get("DEBUG") == "true":
        # DEBUG 模式：返回详细错误（仅开发环境）
        error_detail = str(exc)
    else:
        # 生产模式：返回通用错误信息，隐藏实现细节
        error_detail = "服务器内部错误，请稍后重试"

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": error_detail,
            "trace_id": trace_id,  # 用于追踪问题
        },
    )


# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=os.environ.get("DEBUG", "false").lower() == "true",
    )
