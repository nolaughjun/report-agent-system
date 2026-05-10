# state.py — 并发版本报告系统状态定义
"""并发版本报告智能体系统状态定义

特性：
1. 支持并发数据收集
2. 支持版本时间施行（定时执行）
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

if TYPE_CHECKING:
    pass


def append_item(existing: list[Any] | None, new: list[Any] | Any | None) -> list[Any]:
    """列表追加 reducer，用于 Annotated 类型"""
    if existing is None:
        existing = []
    if new is None:
        return existing
    return existing + (new if isinstance(new, list) else [new])


# ══════════════════════════════════════════════════════════════
# 数据结构定义
# ══════════════════════════════════════════════════════════════


class ResearchSource(TypedDict):
    """单条数据来源"""

    source_type: Literal["web", "database", "document", "api"]
    query: str
    content: str
    url: str
    retrieved_at: str
    collection_time_ms: int  # 收集耗时（毫秒）


class ReportDraft(TypedDict):
    """报告草案版本"""

    version: str
    content: str
    sections: list[str]
    created_at: str
    change_note: str
    generation_time_ms: int  # 生成耗时（毫秒）


class QualityCheckResult(TypedDict):
    """质量检测结果"""

    ispass: bool
    score: float
    issue: str
    suggestions: list[str]
    check_time_ms: int  # 检测耗时（毫秒）


class CollectionTask(TypedDict):
    """并发收集任务"""

    query: str
    status: Literal["pending", "running", "completed", "failed"]
    start_time: str | None
    end_time: str | None
    result: ResearchSource | None
    error: str | None


class ExecutionSchedule(TypedDict):
    """时间施行配置"""

    enabled: bool  # 是否启用定时执行
    scheduled_time: str | None  # 计划执行时间 ISO8601
    recurrence: Literal["once", "daily", "weekly", "monthly"] | None  # 重复模式
    timezone: str  # 时区
    last_run: str | None  # 上次执行时间
    next_run: str | None  # 下次执行时间


class PerformanceMetrics(TypedDict):
    """性能指标"""

    total_time_ms: int  # 总耗时
    planning_time_ms: int  # 规划耗时
    collection_time_ms: int  # 收集耗时
    drafting_time_ms: int  # 撰写耗时
    review_time_ms: int  # 审核耗时
    concurrent_tasks: int  # 并发任务数
    success_rate: float  # 成功率


class TokenUsage(TypedDict):
    """Token 使用量统计"""

    prompt_tokens: int  # 输入 token 数
    completion_tokens: int  # 输出 token 数
    total_tokens: int  # 总 token 数
    model: str  # 使用的模型
    timestamp: str  # 记录时间
    node: str  # 来源节点


class StateSnapshot(TypedDict):
    """状态快照，用于版本回滚"""

    version: int  # 版本号
    timestamp: str  # 快照时间
    step: str  # 当前步骤
    state_data: dict  # 状态数据快照
    description: str  # 快照描述


# ══════════════════════════════════════════════════════════════
# 主状态定义
# ══════════════════════════════════════════════════════════════


class ReportState(TypedDict):
    """并发版本报告生成状态

    新增特性：
    1. 并发收集任务管理
    2. 时间施行配置
    3. 性能指标追踪
    """

    # ── 1. 任务输入 ───────────────────────────────────────────
    topic: str
    abstract: str
    report_type: Literal["research", "analysis", "summary", "proposal"]
    language: str
    create_at: str
    quality_threshold: float

    # ── 2. 流程控制 ───────────────────────────────────────────
    current_step: Literal[
        "init",
        "scheduled",  # 新增：等待定时执行
        "planning",
        "researching",
        "drafting",
        "reviewing",
        "revising",
        "finished",
        "failed",
    ]
    retry_count: int
    max_retry: int
    error_msg: str | None

    # ── 3. 并发收集控制（新增）───────────────────────────────
    max_concurrent: int  # 最大并发数
    collection_tasks: list[CollectionTask]  # 收集任务列表
    collection_progress: float  # 收集进度 0.0-1.0

    # ── 4. 时间施行（新增）───────────────────────────────────
    schedule: ExecutionSchedule | None  # 定时执行配置

    # ── 5. 性能指标（新增）───────────────────────────────────
    metrics: PerformanceMetrics | None
    start_time: str | None  # 任务开始时间

    # ── 6. 规划产物 ───────────────────────────────────────────
    outline: list[str]
    search_queries: list[str]

    # ── 7. 数据收集 ───────────────────────────────────────────
    research_sources: Annotated[list[ResearchSource], append_item]

    # ── 8. 对话历史 ───────────────────────────────────────────
    messages: Annotated[list, add_messages]

    # ── 9. 报告版本 ───────────────────────────────────────────
    draft_versions: Annotated[list[ReportDraft], append_item]
    current_draft: str | None

    # ── 10. 质量控制 ──────────────────────────────────────────
    quality_checks: Annotated[list[QualityCheckResult], append_item]
    revision_instructions: list[str]

    # ── 11. 人工审核 ──────────────────────────────────────────
    human_decision: Literal["approve", "revise"] | None
    human_comments: str | None
    revision_history: list[dict]  # 修改历史记录

    # ── 12. 最终输出 ──────────────────────────────────────────
    final_report: str | None
    export_path: str | None

    # ── 13. Token 使用量统计（新增）───────────────────────────
    token_usage: Annotated[list[TokenUsage], append_item]
    total_prompt_tokens: int
    total_completion_tokens: int

    # ── 14. 状态快照（新增，用于时间旅行）─────────────────────
    snapshots: Annotated[list[StateSnapshot], append_item]
    current_version: int


# ══════════════════════════════════════════════════════════════
# 状态初始化函数
# ══════════════════════════════════════════════════════════════


def create_initial_state(
    topic: str,
    abstract: str = "",
    report_type: Literal["research", "analysis", "summary", "proposal"] = "research",
    language: str = "中文",
    quality_threshold: float = 0.55,
    max_retry: int = 3,
    max_concurrent: int = 5,  # 默认最大并发数
    schedule: ExecutionSchedule | None = None,
) -> ReportState:
    """创建初始状态

    Args:
        topic: 报告主题
        abstract: 报告概要
        report_type: 报告类型
        language: 语言
        quality_threshold: 质量阈值 (0.0-1.0)
        max_retry: 最大重试次数 (0-10)
        max_concurrent: 最大并发收集数 (1-20)
        schedule: 定时执行配置

    Returns:
        初始化后的状态

    Raises:
        ValueError: 参数验证失败
    """
    # 参数验证
    if not topic or not topic.strip():
        raise ValueError("报告主题不能为空")

    if len(topic) > 500:
        raise ValueError(f"报告主题过长: {len(topic)} 字符，最大 500 字符")

    if not 0.0 <= quality_threshold <= 1.0:
        raise ValueError(f"质量阈值必须在 [0, 1] 范围内，当前: {quality_threshold}")

    if not 0 <= max_retry <= 10:
        raise ValueError(f"最大重试次数必须在 [0, 10] 范围内，当前: {max_retry}")

    if not 1 <= max_concurrent <= 20:
        raise ValueError(f"最大并发数必须在 [1, 20] 范围内，当前: {max_concurrent}")

    # 验证报告类型
    valid_report_types = ["research", "analysis", "summary", "proposal"]
    if report_type not in valid_report_types:
        raise ValueError(f"无效的报告类型: {report_type}，有效值: {valid_report_types}")

    return {
        # 任务输入
        "topic": topic.strip(),
        "abstract": abstract.strip() if abstract else "",
        "report_type": report_type,
        "language": language,
        "create_at": datetime.now(UTC).isoformat(),
        "quality_threshold": quality_threshold,
        # 流程控制
        "current_step": "init",
        "retry_count": 0,
        "max_retry": max_retry,
        "error_msg": None,
        # 并发控制
        "max_concurrent": max_concurrent,
        "collection_tasks": [],
        "collection_progress": 0.0,
        # 时间施行
        "schedule": schedule,
        # 性能指标
        "metrics": None,
        "start_time": None,
        # 规划产物
        "outline": [],
        "search_queries": [],
        # 数据收集
        "research_sources": [],
        # 对话历史
        "messages": [],
        # 报告版本
        "draft_versions": [],
        "current_draft": None,
        # 质量控制
        "quality_checks": [],
        "revision_instructions": [],
        # 人工审核
        "human_decision": None,
        "human_comments": None,
        "revision_history": [],
        # 最终输出
        "final_report": None,
        "export_path": None,
        # Token 使用量统计
        "token_usage": [],
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        # 状态快照
        "snapshots": [],
        "current_version": 0,
    }


def create_schedule_config(
    scheduled_time: str,
    recurrence: Literal["once", "daily", "weekly", "monthly"] = "once",
    timezone: str = "Asia/Shanghai",
) -> ExecutionSchedule:
    """创建定时执行配置

    Args:
        scheduled_time: 计划执行时间 ISO8601
        recurrence: 重复模式
        timezone: 时区

    Returns:
        ExecutionSchedule 配置
    """
    return {
        "enabled": True,
        "scheduled_time": scheduled_time,
        "recurrence": recurrence,
        "timezone": timezone,
        "last_run": None,
        "next_run": scheduled_time,
    }
