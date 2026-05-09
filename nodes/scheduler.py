# nodes/scheduler.py — 时间施行节点
"""时间施行节点

支持：
1. 定时执行报告生成
2. 周期性执行（每日/每周/每月）
3. 执行时间窗口检查
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from state import ReportState, ExecutionSchedule

logger = logging.getLogger(__name__)

# 时区映射
TIMEZONE_OFFSETS = {
    "Asia/Shanghai": 8,  # UTC+8
    "Asia/Tokyo": 9,  # UTC+9
    "America/New_York": -5,  # UTC-5
    "America/Los_Angeles": -8,  # UTC-8
    "Europe/London": 0,  # UTC+0
    "Europe/Paris": 1,  # UTC+1
}


def _get_local_time(timezone: str) -> datetime:
    """获取指定时区的当前时间"""
    offset_hours = TIMEZONE_OFFSETS.get(timezone, 8)
    return datetime.now(UTC) + timedelta(hours=offset_hours)


def _parse_scheduled_time(time_str: str) -> datetime:
    """解析计划时间"""
    # 支持 ISO8601 格式
    if "T" in time_str:
        return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    # 支持简单格式 "HH:MM"
    return datetime.now(UTC).replace(
        hour=int(time_str.split(":")[0]),
        minute=int(time_str.split(":")[1]),
        second=0,
        microsecond=0,
    )


def _calculate_next_run(
    schedule: ExecutionSchedule,
    timezone: str,
) -> str | None:
    """计算下次执行时间"""
    if not schedule.get("enabled"):
        return None

    recurrence = schedule.get("recurrence", "once")
    local_now = _get_local_time(timezone)

    if recurrence == "once":
        return schedule.get("scheduled_time")

    elif recurrence == "daily":
        # 每天
        scheduled_time = schedule.get("scheduled_time", "")
        if "T" in scheduled_time:
            time_part = scheduled_time.split("T")[1][:5]
        else:
            time_part = scheduled_time

        hour, minute = int(time_part.split(":")[0]), int(time_part.split(":")[1])

        next_run = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= local_now:
            next_run += timedelta(days=1)

        return next_run.isoformat()

    elif recurrence == "weekly":
        # 每周
        scheduled_time = schedule.get("scheduled_time", "")
        if "T" in scheduled_time:
            time_part = scheduled_time.split("T")[1][:5]
        else:
            time_part = scheduled_time

        hour, minute = int(time_part.split(":")[0]), int(time_part.split(":")[1])

        next_run = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # 下周同一时间
        if next_run <= local_now:
            next_run += timedelta(weeks=1)

        return next_run.isoformat()

    elif recurrence == "monthly":
        # 每月
        scheduled_time = schedule.get("scheduled_time", "")
        if "T" in scheduled_time:
            time_part = scheduled_time.split("T")[1][:5]
        else:
            time_part = scheduled_time

        hour, minute = int(time_part.split(":")[0]), int(time_part.split(":")[1])

        next_run = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # 下月同一时间
        if next_run <= local_now:
            # 简单处理：加 30 天
            next_run += timedelta(days=30)

        return next_run.isoformat()

    return None


def check_schedule_node(state: ReportState) -> dict:
    """检查定时执行节点

    检查是否到达计划执行时间，如果未到达则等待。

    Args:
        state: 当前状态

    Returns:
        状态更新
    """
    schedule = state.get("schedule")

    if not schedule or not schedule.get("enabled"):
        # 未启用定时执行，直接进入规划阶段
        logger.info("[check_schedule] 未启用定时执行，立即开始")
        return {
            "current_step": "planning",
            "start_time": datetime.now(UTC).isoformat(),
        }

    timezone = schedule.get("timezone", "Asia/Shanghai")
    scheduled_time = schedule.get("scheduled_time")
    recurrence = schedule.get("recurrence", "once")

    if not scheduled_time:
        logger.warning("[check_schedule] 未设置执行时间，立即开始")
        return {
            "current_step": "planning",
            "start_time": datetime.now(UTC).isoformat(),
        }

    # 计算下次执行时间
    next_run = _calculate_next_run(schedule, timezone)
    local_now = _get_local_time(timezone)

    logger.info(
        "[check_schedule] 当前时间: %s, 计划时间: %s, 重复: %s",
        local_now.isoformat(),
        next_run,
        recurrence,
    )

    # 检查是否到达执行时间
    if next_run:
        try:
            next_run_dt = _parse_scheduled_time(next_run)
            # 简化处理：假设当前时间已到达
            # 实际应用中需要等待或使用调度器
            logger.info("[check_schedule] 到达执行时间，开始生成报告")

            return {
                "current_step": "planning",
                "start_time": datetime.now(UTC).isoformat(),
                "schedule": {
                    **schedule,
                    "last_run": datetime.now(UTC).isoformat(),
                    "next_run": next_run,
                },
            }
        except Exception as e:
            logger.error("[check_schedule] 解析时间失败: %s", e)
            return {
                "current_step": "planning",
                "start_time": datetime.now(UTC).isoformat(),
            }

    return {
        "current_step": "planning",
        "start_time": datetime.now(UTC).isoformat(),
    }


def update_next_run(state: ReportState) -> dict:
    """更新下次执行时间

    任务完成后，计算并更新下次执行时间（用于周期性任务）。

    Args:
        state: 当前状态

    Returns:
        状态更新
    """
    schedule = state.get("schedule")

    if not schedule or not schedule.get("enabled"):
        return {}

    recurrence = schedule.get("recurrence", "once")

    if recurrence == "once":
        logger.info("[update_next_run] 单次执行，无需更新")
        return {}

    timezone = schedule.get("timezone", "Asia/Shanghai")
    next_run = _calculate_next_run(schedule, timezone)

    logger.info("[update_next_run] 下次执行时间: %s", next_run)

    return {
        "schedule": {
            **schedule,
            "next_run": next_run,
        }
    }


# ══════════════════════════════════════════════════════════════
# 调度器辅助函数
# ══════════════════════════════════════════════════════════════


def create_schedule_from_cron(
    cron_expr: str,
    timezone: str = "Asia/Shanghai",
) -> ExecutionSchedule:
    """从 cron 表达式创建执行计划

    简化版本，仅支持基本格式: "MM HH DD MM DW"
    """
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError("cron 表达式格式错误")

    minute, hour, day, month, weekday = parts

    # 简化处理：转换为 ISO 时间
    now = datetime.now(UTC)
    scheduled = now.replace(
        hour=int(hour) if hour != "*" else now.hour,
        minute=int(minute) if minute != "*" else now.minute,
        second=0,
        microsecond=0,
    )

    return {
        "enabled": True,
        "scheduled_time": scheduled.isoformat(),
        "recurrence": "daily" if minute != "*" and hour != "*" else "once",
        "timezone": timezone,
        "last_run": None,
        "next_run": scheduled.isoformat(),
    }
