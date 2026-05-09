# nodes/draft.py — 草案撰写节点
"""草案撰写节点"""

from __future__ import annotations

import json
import logging
import time

from state import ReportDraft, ReportState
from tools.llm import chat_with_usage, make_token_usage_update, now_iso

logger = logging.getLogger(__name__)

DRAFT_SYSTEM = """你是一位专业的报告撰写专家。
请根据提供的大纲和资料，撰写结构清晰、内容充实的专业报告。
直接输出 Markdown 格式的报告内容，不要包含任何其他说明。"""

DRAFT_USER = """请根据以下信息撰写报告草案：

主题：{topic}
报告类型：{report_type}
语言：{language}

报告大纲：
{outline}

参考资料：
{research_data}

要求：
1. 使用 Markdown 格式
2. 每个章节需要有明确的标题（## 章节名）和内容
3. 内容要有数据支撑，引用资料中的关键发现
4. 语言流畅，逻辑清晰
5. 总字数控制在 8000-10000 字
"""


def generate_draft(state: ReportState) -> dict:
    """草案撰写节点"""
    logger.info("[generate_draft] 开始撰写草案")
    start_time = time.perf_counter()

    topic = state["topic"]
    report_type = state["report_type"]
    language = state.get("language", "中文")
    outline = state.get("outline", [])
    research_sources = state.get("research_sources", [])

    # 整合研究资料
    research_data_parts = []
    for source in research_sources:
        if source.get("source_type") == "document" and "聚合摘要" in source.get("query", ""):
            try:
                agg_data = json.loads(source["content"])
                research_data_parts.insert(
                    0,
                    f"【整合摘要】\n{agg_data.get('integrated_summary', '')}",
                )
            except json.JSONDecodeError:
                research_data_parts.insert(0, source["content"][:500])
        else:
            research_data_parts.append(
                f"- {source.get('query', '')}: {source.get('content', '')[:300]}"
            )

    research_data = "\n\n".join(research_data_parts) or "无参考资料"

    try:
        # 使用 chat_with_usage 获取 Token 使用量
        draft_content, usage = chat_with_usage(
            messages=[
                {"role": "system", "content": DRAFT_SYSTEM},
                {
                    "role": "user",
                    "content": DRAFT_USER.format(
                        topic=topic,
                        report_type=report_type,
                        language=language,
                        outline="\n".join(f"- {s}" for s in outline),
                        research_data=research_data[:8000],
                    ),
                },
            ],
            max_tokens=6000,
            temperature=0.3,
            node="drafting",
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        existing_versions = state.get("draft_versions", [])
        version = f"1.0.{len(existing_versions) + 1}"

        new_draft: ReportDraft = {
            "version": version,
            "content": draft_content,
            "sections": outline,
            "created_at": now_iso(),
            "change_note": "初始草案",
            "generation_time_ms": elapsed_ms,
        }

        logger.info(
            "[generate_draft] 完成，版本 %s, 字数 %d, 耗时 %dms",
            version,
            len(draft_content),
            elapsed_ms,
        )

        # 创建 Token 使用量更新
        token_update = make_token_usage_update(usage)

        return {
            "current_draft": draft_content,
            "draft_versions": [new_draft],
            "current_step": "reviewing",
            "error_msg": None,
            "messages": [
                {"role": "assistant", "content": f"[generate_draft] 草案完成，耗时 {elapsed_ms}ms"}
            ],
            # Token 使用量
            **token_update,
        }

    except Exception as e:
        logger.error("[generate_draft] 失败: %s", e)
        return {
            "current_step": "failed",
            "error_msg": f"草案撰写失败: {e}",
            "retry_count": state.get("retry_count", 0) + 1,
        }
