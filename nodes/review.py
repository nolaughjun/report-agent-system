# nodes/review.py — 质量审核节点
"""质量审核节点"""
from __future__ import annotations

import json
import logging
import time

from state import ReportState, QualityCheckResult
from tools.llm import chat_with_usage, make_token_usage_update

logger = logging.getLogger(__name__)

REVIEW_SYSTEM = """你是一位严格的报告质检员。
请对报告草案进行多维度质量检测，输出 JSON 格式结果。"""

REVIEW_USER = """请对以下报告草案进行质量检测：

报告主题：{topic}
报告大纲：{outline}

报告内容：
{draft}

请从以下维度进行检测：
1. 结构完整性：是否覆盖大纲所有章节
2. 内容一致性：是否存在自相矛盾
3. 数据支撑：是否有足够的数据和事实支撑
4. 语言质量：语言是否流畅、专业

请输出如下 JSON：
{{
  "ispass": true,
  "score": 0.85,
  "issue": "存在的问题描述",
  "suggestions": ["改进建议1", "改进建议2"]
}}
"""


def quality_review(state: ReportState) -> dict:
    """质量审核节点"""
    logger.info("[quality_review] 开始质量审核")
    start_time = time.perf_counter()

    topic = state["topic"]
    outline = state.get("outline", [])
    current_draft = state.get("current_draft", "")

    if not current_draft:
        return {
            "current_step": "failed",
            "error_msg": "无草案内容",
        }

    try:
        # 使用 chat_with_usage 获取 Token 使用量
        raw, usage = chat_with_usage(
            messages=[
                {"role": "system", "content": REVIEW_SYSTEM},
                {
                    "role": "user",
                    "content": REVIEW_USER.format(
                        topic=topic,
                        outline="\n".join(f"- {s}" for s in outline),
                        draft=current_draft[:5000],
                    ),
                },
            ],
            json_mode=True,
            node="reviewing",
        )

        result = json.loads(raw)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        quality_check: QualityCheckResult = {
            "ispass": result.get("ispass", False),
            "score": float(result.get("score", 0.5)),
            "issue": result.get("issue", ""),
            "suggestions": result.get("suggestions", []),
            "check_time_ms": elapsed_ms,
        }

        threshold = state.get("quality_threshold", 0.55)
        passed = quality_check["score"] >= threshold

        logger.info("[quality_review] 完成，得分 %.2f, 耗时 %dms", quality_check["score"], elapsed_ms)

        revision_instructions = []
        if not passed:
            if quality_check["issue"]:
                revision_instructions.append(f"问题：{quality_check['issue']}")
            for i, suggestion in enumerate(quality_check.get("suggestions", []), 1):
                revision_instructions.append(f"{i}. {suggestion}")

        # 创建 Token 使用量更新
        token_update = make_token_usage_update(usage)

        # 无论质量是否通过，都进入人工审核等待用户决策
        return {
            "quality_checks": [quality_check],
            "revision_instructions": revision_instructions,
            "current_step": "human_review",
            "error_msg": None,
            "messages": [
                {"role": "assistant", "content": f"[quality_review] 审核 {quality_check['score']:.2f}, 耗时 {elapsed_ms}ms"}
            ],
            # Token 使用量
            **token_update,
        }

    except Exception as e:
        logger.error("[quality_review] 失败: %s", e)
        return {
            "current_step": "human_review",
            "error_msg": f"审核失败: {e}",
        }
