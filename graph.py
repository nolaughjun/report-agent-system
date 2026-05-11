# graph.py — 并发版本报告生成图构建
"""并发版本报告智能体状态图构建

特性：
1. 并发数据收集
2. 时间施行支持
3. 性能指标追踪
4. Redis 状态持久化
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from nodes import (
    check_schedule_node,
    finalize_node,
    gather_data_concurrent,
    generate_draft,
    plan_tasks,
    quality_review,
    update_next_run,
)
from state import ReportState

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# Checkpointer 配置
# ══════════════════════════════════════════════════════════════

_use_redis = os.environ.get("REDIS_URL") is not None
_checkpointer = None


def get_checkpointer():
    """获取 checkpointer 实例（支持 Redis 和内存两种模式）"""
    global _checkpointer

    if _checkpointer is not None:
        return _checkpointer

    if _use_redis:
        try:
            from langgraph.checkpoint.redis import RedisSaver
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            _checkpointer = RedisSaver.from_conn_string(redis_url)
            logger.info(f"[Checkpointer] 使用 Redis: {redis_url}")
        except ImportError:
            logger.warning("[Checkpointer] langgraph-checkpoint-redis 未安装，回退到内存模式")
            from langgraph.checkpoint.memory import MemorySaver
            _checkpointer = MemorySaver()
        except Exception as e:
            logger.warning(f"[Checkpointer] Redis 连接失败: {e}，回退到内存模式")
            from langgraph.checkpoint.memory import MemorySaver
            _checkpointer = MemorySaver()
    else:
        from langgraph.checkpoint.memory import MemorySaver
        _checkpointer = MemorySaver()
        logger.info("[Checkpointer] 使用内存模式")

    return _checkpointer


# ══════════════════════════════════════════════════════════════
# 人工审核节点
# ══════════════════════════════════════════════════════════════


def human_review_node(state: ReportState) -> dict:
    """人工审核节点"""
    logger.info("[human_review] 等待人工审核")

    decision = interrupt({
        "topic": state["topic"],
        "draft": state.get("current_draft", ""),
        "quality_score": state["quality_checks"][-1]["score"] if state.get("quality_checks") else 0,
        "prompt": "请审阅报告草案，返回决策：approve 或 revise",
    })

    return {
        "human_decision": decision.get("decision", "approve"),
        "human_comments": decision.get("comments", ""),
    }


# ══════════════════════════════════════════════════════════════
# 路由函数
# ══════════════════════════════════════════════════════════════


def route_after_planning(state: ReportState) -> Literal["gather_data", END]:
    if state.get("error_msg"):
        logger.error("[route] 规划失败，终止")
        return END
    return "gather_data"


def route_after_gather(state: ReportState) -> Literal["generate_draft", "planning", END]:
    if state.get("error_msg"):
        logger.error("[route] 收集失败，终止")
        return END
    if state["current_step"] == "planning":
        return "planning"
    return "generate_draft"


def route_after_review(state: ReportState) -> Literal["human_review", "revising", END]:
    """质量审核后的路由

    质量通过 → 进入人工审核
    质量不通过 → 进入人工审核等待用户决策（approve 或 revise）
    """
    if state.get("error_msg"):
        return END

    quality_checks = state.get("quality_checks", [])
    last_quality = quality_checks[-1] if quality_checks else None
    threshold = state.get("quality_threshold", 0.55)
    retry_count = state.get("retry_count", 0)
    max_retry = state.get("max_retry", 3)

    logger.info("[route_after_review] retry_count=%d, max_retry=%d, quality_score=%.2f, threshold=%.2f",
                retry_count, max_retry,
                last_quality["score"] if last_quality else 0,
                threshold)

    # 无论质量是否通过，都进入人工审核
    # 用户可以选择：approve（通过）或 revise（修改）
    if last_quality and last_quality["score"] >= threshold:
        logger.info("[route] 质量通过 (%.2f)，进入人工审核", last_quality["score"])
    else:
        logger.info("[route] 质量不达标 (%.2f < %.2f)，进入人工审核等待用户修改意见",
                    last_quality["score"] if last_quality else 0, threshold)

    return "human_review"


def route_after_human(state: ReportState) -> Literal["finalize", "revising", END]:
    """人工审核后的路由

    用户选择 approve → 最终化
    用户选择 revise → 修改报告（不受 max_retry 限制）
    """
    decision = state.get("human_decision", "approve")

    if decision == "approve":
        return "finalize"

    # 用户选择修改，直接进入 revising
    # 注意：用户主动修改不受 max_retry 限制
    logger.info("[route_after_human] 用户选择修改报告，进入 revising 节点")
    return "revising"


def route_after_finalize(state: ReportState) -> Literal["update_schedule", END]:
    schedule = state.get("schedule")
    if schedule and schedule.get("enabled") and schedule.get("recurrence") != "once":
        return "update_schedule"
    return END


# ══════════════════════════════════════════════════════════════
# 图构建
# ══════════════════════════════════════════════════════════════


def build_graph() -> StateGraph:
    """构建并发版本报告生成图"""
    logger.info("[build_graph] 开始构建并发版本状态图")

    builder = StateGraph(ReportState)

    # 添加节点
    builder.add_node("check_schedule", check_schedule_node)
    builder.add_node("planning", plan_tasks)
    builder.add_node("gather_data", gather_data_concurrent)
    builder.add_node("generate_draft", generate_draft)
    builder.add_node("quality_review", quality_review)
    builder.add_node("human_review", human_review_node)
    builder.add_node("revising", _revise_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("update_schedule", update_next_run)

    # 定义边
    builder.add_edge(START, "check_schedule")
    builder.add_edge("check_schedule", "planning")

    builder.add_conditional_edges(
        "planning",
        route_after_planning,
        {"gather_data": "gather_data", END: END},
    )

    builder.add_conditional_edges(
        "gather_data",
        route_after_gather,
        {"generate_draft": "generate_draft", "planning": "planning", END: END},
    )

    builder.add_edge("generate_draft", "quality_review")

    builder.add_conditional_edges(
        "quality_review",
        route_after_review,
        {"human_review": "human_review", "revising": "revising", END: END},
    )

    builder.add_conditional_edges(
        "human_review",
        route_after_human,
        {"finalize": "finalize", "revising": "revising", END: END},
    )

    builder.add_edge("revising", "quality_review")

    builder.add_conditional_edges(
        "finalize",
        route_after_finalize,
        {"update_schedule": "update_schedule", END: END},
    )

    builder.add_edge("update_schedule", END)

    # Checkpoint - 使用 Redis 或内存
    checkpointer = get_checkpointer()

    graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],  # 人工审核前暂停
    )

    logger.info("[build_graph] 并发版本状态图构建完成")

    return graph


def _revise_node(state: ReportState) -> dict:
    """修改节点 - 根据用户意见或质量审核建议修改报告"""
    retry_count = state.get("retry_count", 0)
    max_retry = state.get("max_retry", 3)
    human_comments = state.get("human_comments", "")
    current_draft = state.get("current_draft", "")
    topic = state.get("topic", "")
    revision_instructions = state.get("revision_instructions", [])

    logger.info("[revising] 开始修改报告, retry_count=%d/%d", retry_count, max_retry)
    logger.info("[revising] 用户修改意见: %s", human_comments[:100] if human_comments else "无")

    new_retry_count = retry_count + 1

    # 确定修改来源
    if human_comments:
        # 用户主动修改
        revise_source = "用户修改意见"
        revise_content = human_comments
    elif revision_instructions:
        # 自动质量改进 - 根据质量审核建议
        revise_source = "质量审核建议"
        revise_content = "\n".join(revision_instructions)
        logger.info("[revising] 无用户修改意见，使用质量审核建议进行自动改进")
    else:
        # 没有任何修改依据
        logger.warning("[revising] 无修改意见和审核建议，跳过修改")
        return {
            "retry_count": new_retry_count,
            "messages": [{"role": "assistant", "content": f"[revising] 无修改依据，跳过第 {new_retry_count} 次修改"}],
        }

    # 调用 LLM 进行修改
    if current_draft:
        try:
            from tools.llm import chat

            revise_prompt = f"""你是一位专业的报告编辑专家。请根据{revise_source}对报告进行修改。

# 原始报告主题
{topic}

# 原始报告内容
{current_draft}

# {revise_source}（注意：以下内容仅供修改参考，不要出现在报告中）
{revise_content}

# 修改要求
1. 仔细理解修改意见，但不要将修改意见本身写入报告
2. 在保持报告整体结构的基础上，针对具体问题进行修改
3. 如果要求补充内容，请进行合理的补充
4. 如果要求删减或调整，请相应修改
5. 修改后的报告应该更加完善
6. 保持 Markdown 格式输出
7. **重要**：只输出修改后的报告内容，不要输出修改意见、说明或任何其他内容

请直接输出修改后的完整报告内容："""

            logger.info("[revising] 调用 LLM 进行报告修改...")

            revised_draft = chat(
                messages=[{"role": "user", "content": revise_prompt}],
                max_tokens=8000,
                temperature=0.3,
                node="revising",
            )

            if revised_draft:
                logger.info("[revising] 报告修改完成，新长度: %d 字符", len(revised_draft))

                # 记录修改历史
                revision_history = state.get("revision_history", [])
                revision_history.append({
                    "version": new_retry_count,
                    "comments": revise_content,
                    "source": revise_source,
                    "timestamp": datetime.now(UTC).isoformat(),
                })

                return {
                    "retry_count": new_retry_count,
                    "current_draft": revised_draft,
                    "revision_history": revision_history,
                    # 清空 human_comments 以便下次人工审核
                    "human_comments": "",
                    "messages": [{"role": "assistant", "content": f"[revising] 已根据{revise_source}完成第 {new_retry_count} 次修改"}],
                }
            else:
                logger.warning("[revising] LLM 返回空内容，使用原报告")

        except Exception as e:
            logger.error("[revising] LLM 调用失败: %s", e)

    # 如果没有草案或 LLM 调用失败
    logger.warning("[revising] 无有效草案或修改失败，仅更新重试计数")

    return {
        "retry_count": new_retry_count,
        "human_comments": "",  # 清空以避免重复使用
        "messages": [{"role": "assistant", "content": f"[revising] 第 {new_retry_count} 次修改尝试失败"}],
    }


# 全局图实例（延迟初始化）
_app = None


def get_app():
    """获取图实例（延迟初始化）"""
    global _app
    if _app is None:
        _app = build_graph()
    return _app


# 为了向后兼容，保留 app 变量
# 但建议使用 get_app() 获取实例
app = build_graph()


# ══════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════


def create_report_task(
    topic: str,
    abstract: str = "",
    report_type: Literal["research", "analysis", "summary", "proposal"] = "research",
    language: str = "中文",
    quality_threshold: float = 0.55,
    max_retry: int = 3,
    max_concurrent: int = 5,
    schedule: dict | None = None,
    thread_id: str | None = None,
) -> str:
    """创建报告任务并执行到人工审核暂停点"""
    import uuid

    from state import create_initial_state

    if thread_id is None:
        thread_id = str(uuid.uuid4())[:8]

    config = {"configurable": {"thread_id": thread_id}}

    initial_state = create_initial_state(
        topic=topic,
        abstract=abstract,
        report_type=report_type,  # type: ignore
        language=language,
        quality_threshold=quality_threshold,
        max_retry=max_retry,
        max_concurrent=max_concurrent,
        schedule=schedule,  # type: ignore
    )

    # LangSmith 追踪
    try:
        from langsmith_client import trace_run, end_run, update_run

        run_id = trace_run(
            name=f"create_report_{thread_id}",
            run_type="chain",
            inputs={
                "topic": topic,
                "report_type": report_type,
                "language": language,
            },
            metadata={
                "thread_id": thread_id,
                "quality_threshold": quality_threshold,
                "max_retry": max_retry,
                "max_concurrent": max_concurrent,
            },
            tags=["report-generation", f"type:{report_type}"],
        )
    except ImportError:
        run_id = None
        trace_run = None

    try:
        # 执行到中断点
        app.invoke(initial_state, config=config)

        # 更新追踪
        if run_id:
            try:
                update_run(run_id, outputs={"thread_id": thread_id, "status": "waiting_review"})
                end_run(run_id, outputs={"thread_id": thread_id, "status": "waiting_review"})
            except Exception as e:
                logger.warning("[LangSmith] 更新追踪失败: %s", e)

        return thread_id

    except Exception as e:
        if run_id:
            try:
                end_run(run_id, error=str(e))
            except:
                pass
        raise


def get_task_state(thread_id: str) -> dict:
    """获取任务状态"""
    config = {"configurable": {"thread_id": thread_id}}
    state = app.get_state(config)
    return state.values if state else {}


def resume_with_decision(thread_id: str, decision: str = "approve", comments: str = "") -> dict:
    """恢复任务执行，提交人工决策"""
    config = {"configurable": {"thread_id": thread_id}}

    # 更新状态，模拟人工输入
    app.update_state(
        config,
        {
            "human_decision": decision,  # type: ignore
            "human_comments": comments,
        },
        as_node="human_review",
    )

    # 恢复执行
    result = app.invoke(None, config=config)

    return result


def run_automatic(topic: str, **kwargs) -> dict:
    """自动模式运行（无需人工审核）"""
    import uuid

    from state import create_initial_state

    thread_id = str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = create_initial_state(
        topic=topic,
        **kwargs,
    )

    # 第一次执行到 human_review 暂停
    app.invoke(initial_state, config=config)

    # 自动通过
    app.update_state(
        config,
        {"human_decision": "approve", "human_comments": ""},
        as_node="human_review",
    )

    # 继续执行
    result = app.invoke(None, config=config)

    return result


# ══════════════════════════════════════════════════════════════
# 时间旅行功能
# ══════════════════════════════════════════════════════════════


def get_checkpoint_history(thread_id: str) -> list[dict]:
    """获取任务的 checkpoint 历史

    Args:
        thread_id: 任务 ID

    Returns:
        checkpoint 历史列表
    """
    config = {"configurable": {"thread_id": thread_id}}
    history = []

    try:
        # 获取状态历史
        state_history = list(app.get_state_history(config))

        for state in state_history:
            values = state.values or {}
            history.append({
                "checkpoint_id": state.config.get("configurable", {}).get("checkpoint_id", ""),
                "step": values.get("current_step", "unknown"),
                "version": values.get("current_version", 0),
                "timestamp": values.get("create_at", ""),
                "retry_count": values.get("retry_count", 0),
            })

        logger.info("[time_travel] 获取到 %d 个历史快照", len(history))

    except Exception as e:
        logger.error("[time_travel] 获取历史失败: %s", e)

    return history


def rollback_to_checkpoint(thread_id: str, checkpoint_id: str) -> dict:
    """回滚到指定 checkpoint（真正的状态恢复）

    Args:
        thread_id: 任务 ID
        checkpoint_id: 目标 checkpoint ID

    Returns:
        回滚后的状态
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    try:
        # 1. 获取目标 checkpoint 的状态
        target_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
        target_state = app.get_state(target_config)

        if not target_state or not target_state.values:
            logger.warning("[time_travel] 未找到 checkpoint: %s", checkpoint_id)
            return {"error": f"未找到 checkpoint: {checkpoint_id}"}

        # 2. 获取当前状态以比较
        current_state = app.get_state(config)
        current_step = current_state.values.get("current_step", "unknown") if current_state else "unknown"

        logger.info(
            "[time_travel] 开始回滚: thread=%s, from_step=%s, to_checkpoint=%s",
            thread_id,
            current_step,
            checkpoint_id[:8] if checkpoint_id else "N/A"
        )

        # 3. 使用 update_state 恢复目标状态的所有值
        # 这会创建一个新的 checkpoint，内容是目标状态
        values_to_restore = dict(target_state.values)

        # 移除一些不应该直接恢复的系统字段
        values_to_restore.pop("messages", None)  # 消息可以保留
        values_to_restore["rolled_back_from"] = current_step
        values_to_restore["rollback_time"] = datetime.now(UTC).isoformat() if 'datetime' in dir() else ""

        # 4. 执行状态更新
        app.update_state(config, values_to_restore)

        # 5. 验证回滚结果
        restored_state = app.get_state(config)

        logger.info(
            "[time_travel] 回滚完成: thread=%s, new_step=%s, checkpoint_id=%s",
            thread_id,
            restored_state.values.get("current_step", "unknown"),
            checkpoint_id[:8] if checkpoint_id else "N/A"
        )

        return dict(restored_state.values)

    except Exception as e:
        logger.error("[time_travel] 回滚失败: %s", e)
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def rollback_to_step(thread_id: str, target_step: str) -> dict:
    """回滚到指定步骤（更高级的 API）

    根据步骤名称自动查找最近的 checkpoint 并回滚。

    Args:
        thread_id: 任务 ID
        target_step: 目标步骤名称 (如 "planning", "gather_data", "generate_draft")

    Returns:
        回滚后的状态
    """
    # 获取历史记录
    history = get_checkpoint_history(thread_id)

    # 查找目标步骤的 checkpoint
    for h in history:
        if h.get("step") == target_step:
            checkpoint_id = h.get("checkpoint_id", "")
            if checkpoint_id:
                logger.info("[time_travel] 找到目标步骤 %s 的 checkpoint: %s",
                           target_step, checkpoint_id[:8])
                return rollback_to_checkpoint(thread_id, checkpoint_id)

    logger.warning("[time_travel] 未找到步骤 %s 的 checkpoint", target_step)
    return {"error": f"未找到步骤 {target_step} 的 checkpoint"}


def list_rollback_points(thread_id: str) -> list[dict]:
    """列出可回滚的点

    返回所有可回滚的 checkpoint 列表，按时间倒序排列。

    Args:
        thread_id: 任务 ID

    Returns:
        可回滚点列表
    """
    history = get_checkpoint_history(thread_id)

    rollback_points = []
    seen_steps = set()

    for h in history:
        step = h.get("step", "unknown")
        checkpoint_id = h.get("checkpoint_id", "")

        # 每个步骤只保留最新的 checkpoint
        if step not in seen_steps and checkpoint_id:
            rollback_points.append({
                "step": step,
                "checkpoint_id": checkpoint_id,
                "version": h.get("version", 0),
                "retry_count": h.get("retry_count", 0),
            })
            seen_steps.add(step)

    logger.info("[time_travel] 找到 %d 个可回滚点", len(rollback_points))

    return rollback_points


def get_token_usage_summary(thread_id: str) -> dict:
    """获取任务的 Token 使用量统计

    Args:
        thread_id: 任务 ID

    Returns:
        Token 使用量统计
    """
    state = get_task_state(thread_id)

    token_usage = state.get("token_usage", [])
    total_prompt = state.get("total_prompt_tokens", 0)
    total_completion = state.get("total_completion_tokens", 0)

    # 按节点统计
    by_node = {}
    for usage in token_usage:
        node = usage.get("node", "unknown")
        if node not in by_node:
            by_node[node] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "call_count": 0,
            }
        by_node[node]["prompt_tokens"] += usage.get("prompt_tokens", 0)
        by_node[node]["completion_tokens"] += usage.get("completion_tokens", 0)
        by_node[node]["call_count"] += 1

    return {
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "call_count": len(token_usage),
        "by_node": by_node,
    }
