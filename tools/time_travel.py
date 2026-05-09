# tools/time_travel.py — 状态快照与时间旅行
"""状态快照与时间旅行功能

特性：
1. 在关键节点自动保存状态快照
2. 支持回滚到任意历史版本
3. 查看状态变更历史
"""
from __future__ import annotations

import copy
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from state import ReportState, StateSnapshot

if TYPE_CHECKING:
    from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


# 需要保存快照的关键步骤
SNAPSHOT_STEPS = [
    "init",
    "planning",
    "researching",
    "drafting",
    "reviewing",
    "revising",
    "human_review",
    "finished",
]


def create_snapshot(
    state: ReportState,
    description: str = "",
) -> StateSnapshot:
    """创建状态快照

    Args:
        state: 当前状态
        description: 快照描述

    Returns:
        状态快照
    """
    version = state.get("current_version", 0) + 1

    # 深拷贝状态数据，避免引用问题
    state_data = copy.deepcopy(dict(state))

    snapshot: StateSnapshot = {
        "version": version,
        "timestamp": datetime.now(UTC).isoformat(),
        "step": state.get("current_step", "unknown"),
        "state_data": state_data,
        "description": description or f"Step: {state.get('current_step', 'unknown')}",
    }

    logger.info("[time_travel] 创建快照 v%d, step=%s", version, snapshot["step"])
    return snapshot


def save_snapshot_to_state(
    state: ReportState,
    description: str = "",
) -> dict:
    """保存快照到状态并返回更新

    Args:
        state: 当前状态
        description: 快照描述

    Returns:
        状态更新字典
    """
    snapshot = create_snapshot(state, description)
    current_version = snapshot["version"]

    return {
        "snapshots": [snapshot],
        "current_version": current_version,
    }


def get_snapshot_by_version(
    state: ReportState,
    version: int,
) -> StateSnapshot | None:
    """根据版本号获取快照

    Args:
        state: 当前状态
        version: 版本号

    Returns:
        快照或 None
    """
    snapshots = state.get("snapshots", [])
    for snapshot in snapshots:
        if snapshot["version"] == version:
            return snapshot
    return None


def list_snapshots(
    state: ReportState,
) -> list[dict[str, Any]]:
    """列出所有快照摘要

    Args:
        state: 当前状态

    Returns:
        快照摘要列表
    """
    snapshots = state.get("snapshots", [])
    return [
        {
            "version": s["version"],
            "timestamp": s["timestamp"],
            "step": s["step"],
            "description": s["description"],
        }
        for s in snapshots
    ]


def rollback_to_version(
    state: ReportState,
    version: int,
) -> dict:
    """回滚到指定版本

    Args:
        state: 当前状态
        version: 目标版本号

    Returns:
        回滚后的状态更新字典
    """
    snapshot = get_snapshot_by_version(state, version)

    if not snapshot:
        logger.warning("[time_travel] 未找到版本 %d", version)
        return {
            "error_msg": f"未找到版本 {version}",
        }

    # 恢复状态数据
    restored_state = copy.deepcopy(snapshot["state_data"])
    restored_state["current_version"] = state.get("current_version", 0)  # 保持当前版本号
    restored_state["error_msg"] = None

    logger.info(
        "[time_travel] 回滚到版本 %d, step=%s",
        version,
        snapshot["step"]
    )

    return restored_state


def get_diff_between_versions(
    state: ReportState,
    version1: int,
    version2: int,
) -> dict[str, Any]:
    """比较两个版本的差异

    Args:
        state: 当前状态
        version1: 版本1
        version2: 版本2

    Returns:
        差异字典
    """
    snap1 = get_snapshot_by_version(state, version1)
    snap2 = get_snapshot_by_version(state, version2)

    if not snap1 or not snap2:
        return {"error": "版本不存在"}

    data1 = snap1["state_data"]
    data2 = snap2["state_data"]

    diff = {
        "version1": version1,
        "version2": version2,
        "step1": snap1["step"],
        "step2": snap2["step"],
        "timestamp1": snap1["timestamp"],
        "timestamp2": snap2["timestamp"],
        "changes": [],
    }

    # 比较关键字段
    key_fields = [
        "current_step",
        "retry_count",
        "current_draft",
        "outline",
        "quality_checks",
        "human_decision",
    ]

    for field in key_fields:
        val1 = data1.get(field)
        val2 = data2.get(field)

        if val1 != val2:
            diff["changes"].append({
                "field": field,
                "old": _truncate_value(val1),
                "new": _truncate_value(val2),
            })

    return diff


def _truncate_value(value: Any, max_length: int = 200) -> str:
    """截断值用于显示"""
    if value is None:
        return "None"
    if isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length] + "..."
        return value
    if isinstance(value, list):
        return f"[{len(value)} items]"
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    return str(value)


# ══════════════════════════════════════════════════════════════
# Checkpoint-based 时间旅行（使用 LangGraph 内置功能）
# ══════════════════════════════════════════════════════════════


def get_checkpoint_history(
    checkpointer: "MemorySaver",
    thread_id: str,
) -> list[dict[str, Any]]:
    """获取 checkpoint 历史

    Args:
        checkpointer: LangGraph checkpointer
        thread_id: 线程 ID

    Returns:
        checkpoint 列表
    """
    config = {"configurable": {"thread_id": thread_id}}
    history = []

    try:
        # 获取所有 checkpoint
        checkpoints = checkpointer.list(config)

        for cp in checkpoints:
            history.append({
                "checkpoint_id": cp.get("config", {}).get("configurable", {}).get("checkpoint_id"),
                "timestamp": cp.get("metadata", {}).get("timestamp", ""),
                "step": cp.get("metadata", {}).get("step", ""),
            })
    except Exception as e:
        logger.warning("[time_travel] 获取 checkpoint 历史失败: %s", e)

    return history


def restore_from_checkpoint(
    checkpointer: "MemorySaver",
    thread_id: str,
    checkpoint_id: str,
) -> dict | None:
    """从 checkpoint 恢复状态

    Args:
        checkpointer: LangGraph checkpointer
        thread_id: 线程 ID
        checkpoint_id: checkpoint ID

    Returns:
        恢复的状态或 None
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
        }
    }

    try:
        state = checkpointer.get(config)
        if state:
            logger.info(
                "[time_travel] 从 checkpoint 恢复: thread=%s, checkpoint=%s",
                thread_id,
                checkpoint_id
            )
            return state.values
    except Exception as e:
        logger.error("[time_travel] 恢复 checkpoint 失败: %s", e)

    return None
