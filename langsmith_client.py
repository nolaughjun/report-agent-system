# langsmith_client.py - LangSmith 监控集成
"""LangSmith 监控集成模块

提供：
1. LLM 调用追踪
2. 链式调用追踪
3. 性能指标收集
4. 错误追踪
5. 反馈记录

使用方式：
1. 设置环境变量：
   LANGCHAIN_API_KEY=your-api-key
   LANGCHAIN_PROJECT=report-agent
   LANGCHAIN_TRACING_V2=true

2. 或在代码中初始化：
   from langsmith_client import init_langsmith
   init_langsmith()
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════════

LANGSMITH_ENABLED = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGSMITH_API_KEY = os.environ.get("LANGCHAIN_API_KEY", "")
LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "report-agent")
LANGSMITH_ENDPOINT = os.environ.get("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

# 客户端实例
_client = None


def is_enabled() -> bool:
    """检查 LangSmith 是否启用"""
    return LANGSMITH_ENABLED and bool(LANGSMITH_API_KEY)


def init_langsmith(
    api_key: str = None,
    project: str = None,
    enabled: bool = True,
) -> bool:
    """初始化 LangSmith

    Args:
        api_key: LangSmith API Key
        project: 项目名称
        enabled: 是否启用

    Returns:
        是否初始化成功
    """
    global LANGSMITH_ENABLED, LANGSMITH_API_KEY, LANGSMITH_PROJECT, _client

    if api_key:
        LANGSMITH_API_KEY = api_key
        os.environ["LANGCHAIN_API_KEY"] = api_key

    if project:
        LANGSMITH_PROJECT = project
        os.environ["LANGCHAIN_PROJECT"] = project

    LANGSMITH_ENABLED = enabled and bool(LANGSMITH_API_KEY)
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if LANGSMITH_ENABLED else "false"

    if not LANGSMITH_ENABLED:
        logger.info("[LangSmith] 监控未启用")
        return False

    try:
        from langsmith import Client

        _client = Client(
            api_url=LANGSMITH_ENDPOINT,
            api_key=LANGSMITH_API_KEY,
        )

        logger.info("[LangSmith] 初始化成功, project=%s", LANGSMITH_PROJECT)
        return True

    except ImportError:
        logger.warning("[LangSmith] langsmith 包未安装, 运行: pip install langsmith")
        return False
    except Exception as e:
        logger.error("[LangSmith] 初始化失败: %s", e)
        return False


def get_client():
    """获取 LangSmith 客户端"""
    global _client

    if _client is None and is_enabled():
        init_langsmith()

    return _client


# ══════════════════════════════════════════════════════════════
# 追踪数据结构
# ══════════════════════════════════════════════════════════════

@dataclass
class RunTrace:
    """运行追踪记录"""
    run_id: str
    name: str
    run_type: str  # "llm", "chain", "tool", "retriever"
    inputs: dict
    outputs: dict = field(default_factory=dict)
    start_time: str = ""
    end_time: str = ""
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    parent_run_id: Optional[str] = None

    # 性能指标
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


# 本地追踪存储（用于 LangSmith 不可用时）
_local_traces: dict[str, RunTrace] = {}
_active_runs: dict[str, float] = {}  # run_id -> start_timestamp


# ══════════════════════════════════════════════════════════════
# 追踪函数
# ══════════════════════════════════════════════════════════════

def create_run(
    name: str,
    run_type: str = "chain",
    inputs: dict = None,
    metadata: dict = None,
    tags: list = None,
    parent_run_id: str = None,
) -> str:
    """创建一个新的运行追踪

    Args:
        name: 运行名称
        run_type: 运行类型 (llm, chain, tool, retriever)
        inputs: 输入数据
        metadata: 元数据
        tags: 标签
        parent_run_id: 父运行 ID

    Returns:
        运行 ID
    """
    run_id = str(uuid.uuid4())

    trace = RunTrace(
        run_id=run_id,
        name=name,
        run_type=run_type,
        inputs=inputs or {},
        metadata=metadata or {},
        tags=tags or [],
        parent_run_id=parent_run_id,
        start_time=datetime.now(UTC).isoformat(),
    )

    _local_traces[run_id] = trace
    _active_runs[run_id] = time.perf_counter()

    # 如果 LangSmith 可用，创建远程追踪
    client = get_client()
    if client:
        try:
            client.create_run(
                name=name,
                run_type=run_type,
                inputs=inputs or {},
                id=run_id,
                project_name=LANGSMITH_PROJECT,
                tags=tags or [],
                extra=metadata or {},
                parent_run_id=parent_run_id,
            )
        except Exception as e:
            logger.warning("[LangSmith] 创建运行失败: %s", e)

    logger.debug("[Trace] 创建运行: %s (%s)", name, run_id[:8])
    return run_id


def end_run(
    run_id: str,
    outputs: dict = None,
    error: str = None,
) -> None:
    """结束运行追踪

    Args:
        run_id: 运行 ID
        outputs: 输出数据
        error: 错误信息（如果有）
    """
    if run_id not in _local_traces:
        logger.warning("[Trace] 未找到运行: %s", run_id)
        return

    trace = _local_traces[run_id]
    trace.outputs = outputs or {}
    trace.error = error
    trace.end_time = datetime.now(UTC).isoformat()

    # 计算延迟
    if run_id in _active_runs:
        trace.latency_ms = int((time.perf_counter() - _active_runs[run_id]) * 1000)
        del _active_runs[run_id]

    # 如果 LangSmith 可用，更新远程追踪
    client = get_client()
    if client:
        try:
            client.update_run(
                run_id=run_id,
                outputs=outputs or {},
                error=error,
                end_time=datetime.now(UTC),
            )
        except Exception as e:
            logger.warning("[LangSmith] 更新运行失败: %s", e)

    logger.debug(
        "[Trace] 结束运行: %s (%s), latency=%dms",
        trace.name, run_id[:8], trace.latency_ms
    )


def update_run(
    run_id: str,
    outputs: dict = None,
    metadata: dict = None,
    tokens: dict = None,
) -> None:
    """更新运行追踪

    Args:
        run_id: 运行 ID
        outputs: 输出数据（增量更新）
        metadata: 元数据（增量更新）
        tokens: Token 使用量 {prompt, completion, total}
    """
    if run_id not in _local_traces:
        return

    trace = _local_traces[run_id]

    if outputs:
        trace.outputs.update(outputs)

    if metadata:
        trace.metadata.update(metadata)

    if tokens:
        trace.prompt_tokens = tokens.get("prompt", 0)
        trace.completion_tokens = tokens.get("completion", 0)
        trace.total_tokens = tokens.get("total", 0)


# ══════════════════════════════════════════════════════════════
# 上下文管理器
# ══════════════════════════════════════════════════════════════

@contextmanager
def trace_run(
    name: str,
    run_type: str = "chain",
    inputs: dict = None,
    metadata: dict = None,
    tags: list = None,
    parent_run_id: str = None,
):
    """追踪运行的上下文管理器

    使用示例:
        with trace_run("generate_report", inputs={"topic": "AI"}) as run_id:
            # 执行操作
            result = do_something()
            update_run(run_id, outputs={"result": result})
    """
    run_id = create_run(
        name=name,
        run_type=run_type,
        inputs=inputs,
        metadata=metadata,
        tags=tags,
        parent_run_id=parent_run_id,
    )

    error = None
    try:
        yield run_id
    except Exception as e:
        error = str(e)
        raise
    finally:
        end_run(run_id, error=error)


# ══════════════════════════════════════════════════════════════
# 装饰器
# ══════════════════════════════════════════════════════════════

def traced(
    name: str = None,
    run_type: str = "chain",
):
    """追踪装饰器

    使用示例:
        @traced("my_function")
        def my_function(arg1, arg2):
            return result

        @traced(run_type="llm")
        async def call_llm(prompt):
            return response
    """
    def decorator(func: Callable) -> Callable:
        import functools

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            trace_name = name or func.__name__

            with trace_run(
                name=trace_name,
                run_type=run_type,
                inputs={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
            ) as run_id:
                result = func(*args, **kwargs)
                update_run(run_id, outputs={"result": str(result)[:500]})
                return result

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            trace_name = name or func.__name__

            with trace_run(
                name=trace_name,
                run_type=run_type,
                inputs={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
            ) as run_id:
                result = await func(*args, **kwargs)
                update_run(run_id, outputs={"result": str(result)[:500]})
                return result

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ══════════════════════════════════════════════════════════════
# LLM 追踪辅助
# ══════════════════════════════════════════════════════════════

def trace_llm_call(
    model: str,
    messages: list,
    response: str,
    usage: dict = None,
    latency_ms: int = 0,
    parent_run_id: str = None,
) -> str:
    """追踪 LLM 调用

    Args:
        model: 模型名称
        messages: 输入消息
        response: 输出响应
        usage: Token 使用量
        latency_ms: 延迟毫秒
        parent_run_id: 父运行 ID

    Returns:
        运行 ID
    """
    run_id = create_run(
        name=f"llm_call_{model}",
        run_type="llm",
        inputs={
            "model": model,
            "messages": messages,
        },
        metadata={
            "model": model,
            "latency_ms": latency_ms,
        },
        tags=[f"model:{model}"],
        parent_run_id=parent_run_id,
    )

    update_run(
        run_id,
        outputs={"response": response},
        tokens=usage,
    )

    end_run(run_id)

    return run_id


# ══════════════════════════════════════════════════════════════
# 反馈记录
# ══════════════════════════════════════════════════════════════

def record_feedback(
    run_id: str,
    key: str,
    score: float,
    comment: str = None,
) -> bool:
    """记录反馈

    Args:
        run_id: 运行 ID
        key: 反馈键 (如 "quality", "relevance")
        score: 分数 (0.0 - 1.0)
        comment: 评论

    Returns:
        是否成功
    """
    client = get_client()
    if not client:
        logger.debug("[LangSmith] 客户端不可用，跳过反馈记录")
        return False

    try:
        client.create_feedback(
            run_id=run_id,
            key=key,
            score=score,
            comment=comment,
        )
        logger.info("[LangSmith] 记录反馈: run=%s, key=%s, score=%.2f", run_id[:8], key, score)
        return True
    except Exception as e:
        logger.warning("[LangSmith] 记录反馈失败: %s", e)
        return False


# ══════════════════════════════════════════════════════════════
# 查询追踪
# ══════════════════════════════════════════════════════════════

def get_trace(run_id: str) -> Optional[RunTrace]:
    """获取追踪记录"""
    return _local_traces.get(run_id)


def get_project_stats() -> dict:
    """获取项目统计"""
    client = get_client()
    if not client:
        # 返回本地统计
        total_runs = len(_local_traces)
        total_tokens = sum(t.total_tokens for t in _local_traces.values())
        errors = sum(1 for t in _local_traces.values() if t.error)

        return {
            "total_runs": total_runs,
            "total_tokens": total_tokens,
            "errors": errors,
            "source": "local",
        }

    try:
        # 从 LangSmith 获取统计
        runs = list(client.list_runs(project_name=LANGSMITH_PROJECT, limit=100))

        total_tokens = 0
        errors = 0

        for run in runs:
            if run.total_tokens:
                total_tokens += run.total_tokens
            if run.error:
                errors += 1

        return {
            "total_runs": len(runs),
            "total_tokens": total_tokens,
            "errors": errors,
            "source": "langsmith",
        }

    except Exception as e:
        logger.error("[LangSmith] 获取统计失败: %s", e)
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════
# 导出追踪数据
# ══════════════════════════════════════════════════════════════

def export_traces(format: str = "json") -> str:
    """导出追踪数据

    Args:
        format: 导出格式 (json, csv)

    Returns:
        导出的数据字符串
    """
    import json

    traces = []
    for trace in _local_traces.values():
        traces.append({
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
        })

    if format == "json":
        return json.dumps(traces, indent=2, ensure_ascii=False)

    if format == "csv":
        import csv
        import io

        output = io.StringIO()
        if traces:
            writer = csv.DictWriter(output, fieldnames=traces[0].keys())
            writer.writeheader()
            writer.writerows(traces)

        return output.getvalue()

    return json.dumps(traces)


# ══════════════════════════════════════════════════════════════
# 初始化检查
# ══════════════════════════════════════════════════════════════

def _check_init():
    """检查初始化状态"""
    if LANGSMITH_ENABLED and not _client:
        init_langsmith()


# 自动初始化
_check_init()
