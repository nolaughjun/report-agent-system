# nodes/finalize.py — 最终输出节点
"""最终输出节点"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from state import ReportState, PerformanceMetrics
from tools.export import export_report
from tools.llm import now_iso

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs")


def finalize_node(state: ReportState) -> dict:
    """最终输出节点"""
    logger.info("[finalize] 开始生成最终报告")
    start_time = time.perf_counter()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    topic = state["topic"]
    current_draft = state.get("current_draft", "")
    task_start = state.get("start_time")

    if not current_draft:
        return {
            "current_step": "failed",
            "error_msg": "无草案内容",
        }

    # 生成文件名
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c if c.isalnum() or c in "_-" else "_" for c in topic)[:50]
    filename = f"{safe_topic}_{timestamp}"

    try:
        # 导出报告
        export_result = export_report(
            content=current_draft,
            topic=topic,
            output_dir=OUTPUT_DIR,
            filename=filename,
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # 计算性能指标
        metrics: PerformanceMetrics = {
            "total_time_ms": _calculate_total_time(state, elapsed_ms),
            "planning_time_ms": _extract_time(state, "plan"),
            "collection_time_ms": _extract_collection_time(state),
            "drafting_time_ms": _extract_time(state, "draft"),
            "review_time_ms": _extract_time(state, "review"),
            "concurrent_tasks": state.get("max_concurrent", 5),
            "success_rate": _calculate_success_rate(state),
        }

        logger.info("[finalize] 完成，耗时 %dms", elapsed_ms)

        return {
            "final_report": current_draft,
            "export_path": export_result.get("pdf") or export_result.get("markdown"),
            "metrics": metrics,
            "current_step": "finished",
            "error_msg": None,
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        f"[finalize] 报告生成完成\n"
                        f"Markdown: {export_result.get('markdown')}\n"
                        f"PDF: {export_result.get('pdf')}\n"
                        f"总耗时: {metrics['total_time_ms']}ms"
                    ),
                }
            ],
        }

    except Exception as e:
        logger.error("[finalize] 失败: %s", e)
        return {
            "current_step": "failed",
            "error_msg": f"导出失败: {e}",
        }


def _calculate_total_time(state: ReportState, finalize_ms: int) -> int:
    """计算总耗时"""
    metrics = state.get("metrics")
    if metrics:
        return metrics.get("total_time_ms", 0) + finalize_ms

    # 从开始时间计算
    start = state.get("start_time")
    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            now = datetime.now(UTC)
            return int((now - start_dt).total_seconds() * 1000)
        except Exception:
            pass

    return 0


def _extract_time(state: ReportState, node_name: str) -> int:
    """从消息中提取节点耗时"""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
        if f"[{node_name}" in content or f"_{node_name}]" in content:
            # 尝试提取耗时
            import re
            match = re.search(r"(\d+)\s*ms", content)
            if match:
                return int(match.group(1))
    return 0


def _extract_collection_time(state: ReportState) -> int:
    """提取收集耗时"""
    sources = state.get("research_sources", [])
    total = sum(s.get("collection_time_ms", 0) for s in sources)
    return total


def _calculate_success_rate(state: ReportState) -> float:
    """计算成功率"""
    sources = state.get("research_sources", [])
    if not sources:
        return 0.0

    success = sum(1 for s in sources if "失败" not in s.get("content", ""))
    return success / len(sources)
