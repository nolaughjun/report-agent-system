# nodes/plan.py — 规划节点
"""规划节点：生成大纲和检索词"""

from __future__ import annotations

import json
import logging
import time

from state import ReportState
from tools.llm import chat_with_usage, make_token_usage_update

logger = logging.getLogger(__name__)

PLAN_SYSTEM = """你是一位专业的研究报告规划专家。
请根据用户提供的报告主题、概要和类型，输出严格的 JSON 格式。
不要输出任何其他内容，不要使用 markdown 代码块。"""

PLAN_USER = """请为以下报告生成详细的规划方案：

主题：{topic}
概要：{abstract}
报告类型：{report_type}
语言：{language}

请输出如下 JSON 格式（不要输出任何其他内容）：
{{
  "outline": ["章节1", "章节2", "章节3", "章节4", "章节5"],
  "search_queries": ["检索词1", "检索词2", "检索词3", "检索词4", "检索词5"]
}}

要求：
- outline：5~7个章节，覆盖背景、现状、分析、结论,展望，附录等维度
- search_queries：5~8个精准检索词，用于后续网络数据收集
- 语言与报告语言保持一致
- 附录中包含参考文件，数据来源标注等信息
"""


def plan_tasks(state: ReportState) -> dict:
    """规划节点"""
    logger.info("[plan_tasks] 开始规划，主题：%s", state["topic"])
    start_time = time.perf_counter()

    try:
        # 获取 Wiki 相关知识作为上下文
        wiki_context = _get_wiki_context(state["topic"], state.get("report_type", "research"))

        # 构建提示词
        prompt = PLAN_USER.format(
            topic=state["topic"],
            abstract=state.get("abstract", ""),
            report_type=state["report_type"],
            language=state.get("language", "中文"),
        )

        # 如果有 Wiki 上下文，添加到提示词
        if wiki_context:
            prompt = f"{prompt}\n\n{wiki_context}"
            logger.info("[plan_tasks] 已添加 Wiki 知识上下文")

        # 使用 chat_with_usage 获取 Token 使用量
        raw, usage = chat_with_usage(
            messages=[
                {"role": "system", "content": PLAN_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
            node="planning",
        )

        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        result = json.loads(raw)
        outline = result.get("outline", [])
        search_queries = result.get("search_queries", [])

        if not outline:
            raise ValueError("大纲为空")
        if not search_queries:
            raise ValueError("检索词为空")

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "[plan_tasks] 完成: %d 章节, %d 检索词, %d ms",
            len(outline),
            len(search_queries),
            elapsed_ms,
        )

        # 创建 Token 使用量更新
        token_update = make_token_usage_update(usage)

        return {
            "outline": outline,
            "search_queries": search_queries,
            "current_step": "researching",
            "retry_count": 0,
            "error_msg": None,
            "messages": [
                {"role": "assistant", "content": f"[plan_tasks] 规划完成，耗时 {elapsed_ms}ms"}
            ],
            # Token 使用量
            **token_update,
        }

    except json.JSONDecodeError as e:
        logger.error("[plan_tasks] JSON 解析失败: %s", e)
        return {
            "current_step": "failed",
            "error_msg": f"JSON 解析失败: {e}",
            "retry_count": state.get("retry_count", 0) + 1,
        }
    except Exception as e:
        logger.error("[plan_tasks] 规划失败: %s", e)
        return {
            "current_step": "failed",
            "error_msg": str(e),
            "retry_count": state.get("retry_count", 0) + 1,
        }


def _get_wiki_context(topic: str, report_type: str) -> str:
    """获取 Wiki 知识上下文

    Args:
        topic: 报告主题
        report_type: 报告类型

    Returns:
        Wiki 知识上下文字符串
    """
    try:
        from wiki import generate_report_context

        context = generate_report_context(topic, report_type)

        if context:
            logger.info("[plan_tasks] 获取到 Wiki 上下文，长度: %d", len(context))
        return context

    except Exception as e:
        logger.warning("[plan_tasks] 获取 Wiki 上下文失败: %s", e)
        return ""
