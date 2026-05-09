# tasks.py — Celery 后台任务定义
"""Celery 后台任务定义

任务：
1. generate_report_task - 生成报告任务
2. resume_report_task - 恢复报告执行任务

支持：
- Redis 状态存储
- PostgreSQL 数据库持久化
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# 检查是否启用数据库
USE_DATABASE = os.environ.get("DATABASE_URL") is not None


# ══════════════════════════════════════════════════════════════
# 任务去重工具
# ══════════════════════════════════════════════════════════════

def _generate_task_hash(topic: str, **kwargs) -> str:
    """生成任务哈希用于去重

    Args:
        topic: 报告主题
        **kwargs: 其他参数

    Returns:
        任务哈希字符串
    """
    import hashlib
    content = f"{topic}:{kwargs.get('abstract', '')}:{kwargs.get('report_type', 'research')}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def _check_duplicate_task(task_hash: str, ttl: int = 300) -> tuple[bool, str | None]:
    """检查是否有重复任务

    Args:
        task_hash: 任务哈希
        ttl: 缓存时间（秒）

    Returns:
        (是否有重复, 已存在的 thread_id)
    """
    import os
    if not os.environ.get("REDIS_URL"):
        return False, None

    try:
        from redis_client import get_redis
        client = get_redis()
        key = f"task_dedup:{task_hash}"

        existing = client.get(key)
        if existing:
            return True, existing.decode('utf-8')

        return False, None
    except Exception as e:
        logger.warning(f"[Dedup] 检查重复任务失败: {e}")
        return False, None


def _mark_task_running(task_hash: str, thread_id: str, ttl: int = 300):
    """标记任务正在运行

    Args:
        task_hash: 任务哈希
        thread_id: 任务 ID
        ttl: 缓存时间（秒）
    """
    import os
    if not os.environ.get("REDIS_URL"):
        return

    try:
        from redis_client import get_redis
        client = get_redis()
        key = f"task_dedup:{task_hash}"
        client.setex(key, ttl, thread_id)
    except Exception as e:
        logger.warning(f"[Dedup] 标记任务失败: {e}")


# ══════════════════════════════════════════════════════════════
# 报告生成任务
# ══════════════════════════════════════════════════════════════

@shared_task(
    bind=True,
    name="generate_report",
    max_retries=3,
    default_retry_delay=60,
)
def generate_report_task(self, topic: str, **kwargs) -> dict[str, Any]:
    """后台生成报告任务

    Args:
        self: Celery task 实例
        topic: 报告主题
        **kwargs: 其他参数
            - abstract: 报告概要
            - report_type: 报告类型
            - language: 语言
            - quality_threshold: 质量阈值
            - max_retry: 最大重试次数
            - max_concurrent: 最大并发数
            - thread_id: 自定义任务 ID
            - user_id: 用户 ID

    Returns:
        dict: 包含 thread_id 和状态的结果
    """
    from state import create_initial_state
    from graph import build_graph

    thread_id = kwargs.pop("thread_id", self.request.id[:8] if self.request.id else "unknown")
    user_id = kwargs.pop("user_id", None)

    logger.info(f"[Task {thread_id}] 开始生成报告: {topic}")

    # 任务去重检查
    task_hash = _generate_task_hash(topic, **kwargs)
    is_duplicate, existing_thread_id = _check_duplicate_task(task_hash)

    if is_duplicate and existing_thread_id:
        logger.info(f"[Task {thread_id}] 检测到重复任务，已存在: {existing_thread_id}")
        return {
            "thread_id": existing_thread_id,
            "status": "duplicate",
            "message": "相同任务正在处理中",
        }

    # 标记任务开始
    _mark_task_running(task_hash, thread_id)

    # 创建数据库记录
    if USE_DATABASE:
        try:
            from models import create_task_record, check_user_quota, increment_user_usage

            # 检查用户配额
            if user_id and not check_user_quota(user_id):
                logger.warning(f"[Task {thread_id}] 用户 {user_id} 配额已用尽")
                return {
                    "thread_id": thread_id,
                    "status": "failed",
                    "error": "用户配额已用尽",
                }

            # 创建任务记录
            create_task_record(
                thread_id=thread_id,
                topic=topic,
                user_id=user_id,
                celery_task_id=self.request.id,
                abstract=kwargs.get("abstract", ""),
                report_type=kwargs.get("report_type", "research"),
                language=kwargs.get("language", "中文"),
                quality_threshold=kwargs.get("quality_threshold", 0.55),
                max_retry=kwargs.get("max_retry", 3),
                max_concurrent=kwargs.get("max_concurrent", 5),
                status="processing",
                started_at=datetime.now(UTC),
            )
            logger.info(f"[Task {thread_id}] 数据库记录已创建")
        except Exception as e:
            logger.error(f"[Task {thread_id}] 数据库记录创建失败: {e}")
            # 数据库失败不应阻止任务执行，但记录错误
            # 如果需要严格的事务保证，应在此处抛出异常

    # 更新任务状态 - 初始化
    self.update_state(
        state="PROCESSING",
        meta={"step": "init", "progress": 0.0, "topic": topic}
    )

    try:
        # 创建初始状态
        initial_state = create_initial_state(
            topic=topic,
            **kwargs
        )

        config = {"configurable": {"thread_id": thread_id}}

        # 构建图（使用 Redis checkpointer）
        graph = build_graph()

        # 更新状态 - 规划阶段
        self.update_state(
            state="PROCESSING",
            meta={"step": "planning", "progress": 0.1}
        )

        # 更新数据库记录
        if USE_DATABASE:
            from models import update_task_record
            update_task_record(thread_id, current_step="planning", progress=0.1)

        # 执行到人工审核暂停点
        graph.invoke(initial_state, config=config)

        # 获取当前状态
        state = graph.get_state(config)
        values = state.values if state else {}

        current_step = values.get("current_step", "unknown")
        draft = values.get("current_draft", "")
        quality_checks = values.get("quality_checks", [])
        last_quality = quality_checks[-1] if quality_checks else {}

        logger.info(f"[Task {thread_id}] 执行暂停，当前步骤: {current_step}")

        # 更新数据库记录
        if USE_DATABASE:
            try:
                from models import update_task_record

                update_task_record(
                    thread_id,
                    status="waiting_review",
                    current_step="human_review",
                    progress=0.7,
                    draft_content=draft,
                    quality_score=last_quality.get("score"),
                )
            except Exception as e:
                logger.warning(f"[Task {thread_id}] 数据库更新失败: {e}")

        # 更新状态 - 等待审核
        self.update_state(
            state="WAITING_REVIEW",
            meta={
                "step": "human_review",
                "progress": 0.7,
                "draft_preview": draft[:500] + "..." if len(draft) > 500 else draft,
                "quality_score": last_quality.get("score", 0),
            }
        )

        logger.info(f"[Task {thread_id}] 报告已生成，等待人工审核")

        return {
            "thread_id": thread_id,
            "status": "waiting_review",
            "message": "报告已生成，等待人工审核",
            "draft_length": len(draft),
            "quality_score": last_quality.get("score", 0),
        }

    except Exception as e:
        logger.error(f"[Task {thread_id}] 任务失败: {e}", exc_info=True)

        # 更新数据库记录
        if USE_DATABASE:
            try:
                from models import update_task_record
                update_task_record(
                    thread_id,
                    status="failed",
                    error_message=str(e),
                    completed_at=datetime.now(UTC),
                )
            except Exception as db_e:
                logger.warning(f"[Task {thread_id}] 数据库更新失败: {db_e}")

        # 更新失败状态
        self.update_state(
            state="FAILURE",
            meta={"error": str(e), "topic": topic}
        )

        # 重试（如果是临时错误）
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    name="resume_report",
    max_retries=2,
)
def resume_report_task(self, thread_id: str, decision: str, comments: str = "") -> dict[str, Any]:
    """恢复报告任务执行

    Args:
        self: Celery task 实例
        thread_id: 任务 ID
        decision: 决策 (approve/revise)
        comments: 评论

    Returns:
        dict: 最终结果
    """
    from graph import build_graph

    logger.info(f"[Task {thread_id}] 恢复执行，决策: {decision}")

    if decision not in ["approve", "revise"]:
        return {
            "thread_id": thread_id,
            "status": "failed",
            "error": f"无效的决策: {decision}",
        }

    try:
        config = {"configurable": {"thread_id": thread_id}}

        graph = build_graph()

        # 更新状态
        self.update_state(
            state="PROCESSING",
            meta={"step": "resuming", "decision": decision}
        )

        # 更新数据库记录
        if USE_DATABASE:
            from models import update_task_record
            update_task_record(thread_id, status="resuming", current_step="finalize")

        # 更新人工审核决策
        graph.update_state(
            config,
            {"human_decision": decision, "human_comments": comments},
            as_node="human_review",
        )

        # 继续执行
        result = graph.invoke(None, config=config)

        export_path = result.get("export_path", "") if result else ""
        final_report = result.get("final_report", "") if result else ""
        total_tokens = result.get("total_prompt_tokens", 0) + result.get("total_completion_tokens", 0) if result else 0

        logger.info(f"[Task {thread_id}] 执行完成，导出路径: {export_path}")

        # 更新数据库记录
        if USE_DATABASE:
            from models import update_task_record, increment_user_usage

            # 获取用户 ID
            from models import get_task_record
            task_record = get_task_record(thread_id)

            update_task_record(
                thread_id,
                status="completed",
                current_step="finished",
                progress=1.0,
                final_report=final_report,
                export_path=export_path,
                total_tokens=total_tokens,
                completed_at=datetime.now(UTC),
            )

            # 更新用户使用量
            if task_record and task_record.user_id:
                increment_user_usage(task_record.user_id, total_tokens)

        return {
            "thread_id": thread_id,
            "status": "completed",
            "decision": decision,
            "export_path": export_path,
        }

    except Exception as e:
        logger.error(f"[Task {thread_id}] 恢复执行失败: {e}", exc_info=True)

        # 更新数据库记录
        if USE_DATABASE:
            from models import update_task_record
            update_task_record(
                thread_id,
                status="failed",
                error_message=str(e),
                completed_at=datetime.now(UTC),
            )

        self.update_state(
            state="FAILURE",
            meta={"error": str(e), "thread_id": thread_id}
        )

        raise self.retry(exc=e)


# ══════════════════════════════════════════════════════════════
# 辅助任务
# ══════════════════════════════════════════════════════════════

@shared_task(name="cleanup_old_tasks")
def cleanup_old_tasks() -> dict:
    """清理旧任务（定时任务）

    Returns:
        dict: 清理结果
    """
    from redis_client import get_redis

    logger.info("[Cleanup] 开始清理旧任务...")

    client = get_redis()

    # 清理过期的任务结果
    # Celery 会自动处理，这里可以添加额外的清理逻辑

    # 清理超过 24 小时的锁
    keys = client.keys("lock:*")
    cleaned = 0
    for key in keys:
        ttl = client.ttl(key)
        if ttl == -1:  # 没有过期时间的锁
            client.delete(key)
            cleaned += 1

    logger.info(f"[Cleanup] 清理完成，删除 {cleaned} 个过期锁")

    return {"cleaned_locks": cleaned}


@shared_task(name="health_check")
def health_check_task() -> dict:
    """健康检查任务

    Returns:
        dict: 健康状态
    """
    from redis_client import check_redis_connection

    redis_ok = check_redis_connection()

    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis": redis_ok,
    }


# ══════════════════════════════════════════════════════════════
# 任务状态查询
# ══════════════════════════════════════════════════════════════

def get_task_status(task_id: str) -> dict[str, Any]:
    """获取任务状态

    Args:
        task_id: 任务 ID

    Returns:
        dict: 任务状态信息
    """
    from celery.result import AsyncResult

    result = AsyncResult(task_id)

    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.state == "PENDING":
        response["status"] = "pending"
        response["message"] = "任务排队中"

    elif result.state == "PROCESSING":
        response["status"] = "processing"
        response["step"] = result.info.get("step", "unknown") if result.info else "unknown"
        response["progress"] = result.info.get("progress", 0) if result.info else 0

    elif result.state == "WAITING_REVIEW":
        response["status"] = "waiting_review"
        response["message"] = "等待人工审核"
        if result.info:
            response["draft_preview"] = result.info.get("draft_preview", "")
            response["quality_score"] = result.info.get("quality_score", 0)

    elif result.state == "SUCCESS":
        response["status"] = "completed"
        if result.result:
            response.update(result.result)

    elif result.state == "FAILURE":
        response["status"] = "failed"
        response["error"] = str(result.info) if result.info else "Unknown error"

    return response
