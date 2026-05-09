# tools/__init__.py — 工具模块初始化
"""工具层模块

特性：
1. 多模型支持
2. 数据多源接入
3. Token 统计
4. 时间旅行
"""
from tools.llm import (
    # LLM 调用
    chat,
    chat_with_usage,
    make_token_usage_update,
    now_iso,
    # 多模型管理
    get_available_models,
    set_current_model,
    get_current_model,
    get_model_config,
    ModelConfig,
    # 数据多源
    search_multi_source,
    get_available_data_sources,
    set_active_data_sources,
    get_active_data_sources,
    DataSourceConfig,
    tavily_search,
    tavily_search_async,
    # Token 统计
    get_token_stats,
    reset_token_stats,
    # 工具
    Timer,
    sanitize_for_logging,
)
from tools.export import export_markdown, export_pdf, export_report
from tools.time_travel import (
    create_snapshot,
    save_snapshot_to_state,
    get_snapshot_by_version,
    list_snapshots,
    rollback_to_version,
    get_diff_between_versions,
)

__all__ = [
    # LLM 调用
    "chat",
    "chat_with_usage",
    "make_token_usage_update",
    "now_iso",
    # 多模型管理
    "get_available_models",
    "set_current_model",
    "get_current_model",
    "get_model_config",
    "ModelConfig",
    # 数据多源
    "search_multi_source",
    "get_available_data_sources",
    "set_active_data_sources",
    "get_active_data_sources",
    "DataSourceConfig",
    "tavily_search",
    "tavily_search_async",
    # Token 统计
    "get_token_stats",
    "reset_token_stats",
    # 工具
    "Timer",
    "sanitize_for_logging",
    # 导出
    "export_markdown",
    "export_pdf",
    "export_report",
    # 时间旅行
    "create_snapshot",
    "save_snapshot_to_state",
    "get_snapshot_by_version",
    "list_snapshots",
    "rollback_to_version",
    "get_diff_between_versions",
]
