# nodes/gather_data.py — 并发数据收集节点
"""并发数据收集节点

特性：
1. 使用 asyncio 实现并发搜索
2. 实时追踪收集进度
3. 收集任务状态管理
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from state import CollectionTask, ReportState, ResearchSource
from tools.llm import Timer, chat, now_iso, tavily_search_async

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# Prompt 模板
# ══════════════════════════════════════════════════════════════

EXTRACT_SYSTEM = """你是一位严谨的数据分析师，擅长从搜索结果中提取结构化信息。
请严格按照用户要求的 JSON 格式输出，不要包含任何其他内容。"""

EXTRACT_USER = """请从以下搜索结果中提取与报告主题相关的关键信息：

报告主题：{topic}
检索词：{query}

搜索结果：
{search_content}

请输出如下 JSON（不要输出其他内容）：
{{
  "key_findings": ["核心发现1", "核心发现2", "核心发现3"],
  "data_points": ["具体数据/事实1", "具体数据/事实2"],
  "summary": "本次搜索的综合摘要（500字以内）",
  "relevance_score": 0.85,
  "completeness_score": 0.75,
  "credibility_score": 0.80,
  "issues": "存在的问题描述（无问题则为空字符串）"
}}
"""

AGGREGATE_SYSTEM = """你是一位专业的研究报告数据整合专家。
请将多条搜索结果整合为结构化的研究资料，严格按 JSON 格式输出。"""

AGGREGATE_USER = """请将以下多条数据收集结果整合：

报告主题：{topic}
报告大纲：{outline}

各检索词的收集结果：
{all_results}

请输出如下 JSON：
{{
  "integrated_summary": "整合后的综合摘要（500字以内）",
  "key_facts": ["关键事实1", "关键事实2", "关键事实3"],
  "data_gaps": ["缺失信息1", "缺失信息2"],
  "overall_quality_score": 0.80,
  "quality_passed": true,
  "quality_issues": "质量问题描述（无则为空字符串）",
  "suggestions": ["改进建议1", "改进建议2"]
}}
"""


# ══════════════════════════════════════════════════════════════
# 单任务收集（异步）
# ══════════════════════════════════════════════════════════════


async def _collect_single_async(
    topic: str,
    query: str,
    task_index: int,
) -> tuple[ResearchSource, dict, int]:
    """异步收集单个检索词

    Args:
        topic: 报告主题
        query: 检索词
        task_index: 任务索引

    Returns:
        (ResearchSource, 提取结果, 耗时毫秒)
    """
    start_time = time.perf_counter()
    logger.info("  [gather:%d] 开始搜索: %s", task_index, query)

    try:
        # 1. 异步搜索
        search_result = await tavily_search_async(query, max_results=5)
        answer = search_result.get("answer", "")
        results = search_result.get("results", [])

        # 拼接搜索内容
        content_parts = []
        if answer:
            content_parts.append(f"AI 综合答案：{answer}")
        for r in results:
            content_parts.append(f"【{r['title']}】\n{r['content']}\n来源：{r['url']}")
        search_content = "\n\n".join(content_parts) or "无搜索结果"

        # 收集第一个有效 URL
        first_url = next((r["url"] for r in results if r.get("url")), "")

        # 2. LLM 结构化提取
        try:
            raw = chat(
                messages=[
                    {"role": "system", "content": EXTRACT_SYSTEM},
                    {
                        "role": "user",
                        "content": EXTRACT_USER.format(
                            topic=topic,
                            query=query,
                            search_content=search_content[:4000],
                        ),
                    },
                ],
                json_mode=True,
            )
            extracted = json.loads(raw)
        except Exception as e:
            logger.warning("  [gather:%d] 提取失败: %s", task_index, e)
            extracted = {
                "key_findings": [],
                "data_points": [],
                "summary": search_content[:500],
                "relevance_score": 0.5,
                "completeness_score": 0.5,
                "credibility_score": 0.5,
                "issues": str(e),
            }

        # 3. 构造 ResearchSource
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        source: ResearchSource = {
            "source_type": "web",
            "query": query,
            "content": json.dumps(extracted, ensure_ascii=False),
            "url": first_url,
            "retrieved_at": now_iso(),
            "collection_time_ms": elapsed_ms,
        }

        logger.info("  [gather:%d] 完成: %s (%d ms)", task_index, query, elapsed_ms)

        return source, extracted, elapsed_ms

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error("  [gather:%d] 失败: %s (%d ms)", task_index, e, elapsed_ms)

        # 返回失败结果
        source: ResearchSource = {
            "source_type": "web",
            "query": query,
            "content": f"收集失败：{e}",
            "url": "",
            "retrieved_at": now_iso(),
            "collection_time_ms": elapsed_ms,
        }

        return source, {"error": str(e)}, elapsed_ms


# ══════════════════════════════════════════════════════════════
# 并发收集管理
# ══════════════════════════════════════════════════════════════


async def _gather_concurrent(
    topic: str,
    queries: list[str],
    max_concurrent: int,
) -> tuple[list[ResearchSource], list[dict], int]:
    """并发收集多个检索词

    Args:
        topic: 报告主题
        queries: 检索词列表
        max_concurrent: 最大并发数

    Returns:
        (数据源列表, 提取结果列表, 总耗时毫秒)
    """
    start_time = time.perf_counter()

    logger.info(
        "[gather_concurrent] 开始并发收集: %d 个检索词, 最大并发 %d",
        len(queries),
        max_concurrent,
    )

    # 创建信号量控制并发数
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _limited_collect(query: str, index: int):
        """带并发限制的收集"""
        async with semaphore:
            return await _collect_single_async(topic, query, index)

    # 创建所有任务
    tasks = [_limited_collect(query, i) for i, query in enumerate(queries)]

    # 并发执行
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 整理结果
    sources: list[ResearchSource] = []
    extracted_list: list[dict] = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("[gather] 任务 %d 异常: %s", i, result)
            # 添加失败记录
            sources.append(
                {
                    "source_type": "web",
                    "query": queries[i],
                    "content": f"任务异常: {result}",
                    "url": "",
                    "retrieved_at": now_iso(),
                    "collection_time_ms": 0,
                }
            )
        else:
            source, extracted, _ = result
            sources.append(source)
            extracted_list.append({"query": queries[i], **extracted})

    total_time_ms = int((time.perf_counter() - start_time) * 1000)
    logger.info(
        "[gather_concurrent] 完成收集: %d 成功, 耗时 %d ms",
        len(extracted_list),
        total_time_ms,
    )

    return sources, extracted_list, total_time_ms


# ══════════════════════════════════════════════════════════════
# 主节点函数
# ══════════════════════════════════════════════════════════════


def gather_data_concurrent(state: ReportState) -> dict:
    """并发数据收集节点

    使用 asyncio 实现并发搜索，显著提升收集效率。

    Args:
        state: 当前状态

    Returns:
        状态更新
    """
    logger.info("[gather_data_concurrent] 开始并发数据收集")

    search_queries = state.get("search_queries", [])
    topic = state["topic"]
    outline = state.get("outline", [])
    max_concurrent = state.get("max_concurrent", 5)

    if not search_queries:
        logger.warning("[gather_data_concurrent] 无检索词")
        return {
            "current_step": "failed",
            "error_msg": "search_queries 为空",
        }

    # 创建收集任务列表
    collection_tasks: list[CollectionTask] = [
        {
            "query": q,
            "status": "pending",
            "start_time": None,
            "end_time": None,
            "result": None,
            "error": None,
        }
        for q in search_queries
    ]

    # 执行并发收集
    try:
        # 运行异步收集
        sources, extracted_list, collection_time_ms = asyncio.run(
            _gather_concurrent(topic, search_queries, max_concurrent)
        )

        # 更新任务状态
        for i, task in enumerate(collection_tasks):
            task["status"] = "completed"
            task["end_time"] = now_iso()
            if i < len(sources):
                task["result"] = sources[i]

    except Exception as e:
        logger.error("[gather_data_concurrent] 并发收集失败: %s", e)
        return {
            "current_step": "failed",
            "error_msg": f"并发收集失败: {e}",
        }

    # 聚合质量评分
    logger.info("[gather_data_concurrent] 开始聚合质量评分")
    all_results_text = json.dumps(extracted_list, ensure_ascii=False, indent=2)

    try:
        with Timer("质量评分") as t:
            agg_raw = chat(
                messages=[
                    {"role": "system", "content": AGGREGATE_SYSTEM},
                    {
                        "role": "user",
                        "content": AGGREGATE_USER.format(
                            topic=topic,
                            outline="\n".join(f"- {s}" for s in outline),
                            all_results=all_results_text[:6000],
                        ),
                    },
                ],
                json_mode=True,
            )
            agg = json.loads(agg_raw)
            review_time_ms = t.elapsed_ms
    except Exception as e:
        logger.error("[gather_data_concurrent] 聚合失败: %s", e)
        agg = {
            "integrated_summary": "聚合失败",
            "key_facts": [],
            "data_gaps": [],
            "overall_quality_score": 0.4,
            "quality_passed": False,
            "quality_issues": str(e),
            "suggestions": [],
        }
        review_time_ms = 0

    # 构造质量检测结果
    overall_score = float(agg.get("overall_quality_score", 0.5))
    threshold = state.get("quality_threshold", 0.55)
    quality_passed = overall_score >= threshold

    quality_check = {
        "ispass": quality_passed,
        "score": overall_score,
        "issue": agg.get("quality_issues", ""),
        "suggestions": agg.get("suggestions", []),
        "check_time_ms": review_time_ms,
    }

    # 添加聚合摘要
    integrated_source: ResearchSource = {
        "source_type": "document",
        "query": f"[聚合摘要] {topic}",
        "content": json.dumps(
            {
                "integrated_summary": agg.get("integrated_summary", ""),
                "key_facts": agg.get("key_facts", []),
                "data_gaps": agg.get("data_gaps", []),
            },
            ensure_ascii=False,
        ),
        "url": "",
        "retrieved_at": now_iso(),
        "collection_time_ms": review_time_ms,
    }
    sources.append(integrated_source)

    # 决定下一步
    # 注意：gather_data 阶段的重试不影响 retry_count
    # retry_count 只用于报告修订阶段的重试计数

    if quality_passed:
        next_step = "drafting"
        logger.info("[gather_data_concurrent] 质量通过 (%.2f)", overall_score)
    else:
        # 数据质量不足，继续到 drafting 阶段
        # 让后续的质量审核节点决定是否需要修订
        next_step = "drafting"
        logger.warning("[gather_data_concurrent] 质量不足 (%.2f)，继续到撰写阶段", overall_score)

    # 计算成功率
    success_count = sum(1 for s in sources if "失败" not in s.get("content", ""))
    success_rate = success_count / len(sources) if sources else 0

    return {
        "research_sources": sources,
        "quality_checks": [quality_check],
        "collection_tasks": collection_tasks,
        "collection_progress": 1.0,
        "current_step": next_step,
        # 不修改 retry_count，让修订阶段单独控制
        "error_msg": None,
        "messages": [
            {
                "role": "assistant",
                "content": (
                    f"[gather_data_concurrent] 并发收集完成: {len(sources) - 1} 条, "
                    f"耗时 {collection_time_ms}ms, 成功率 {success_rate:.0%}, "
                    f"质量 {overall_score:.2f}"
                ),
            }
        ],
    }
