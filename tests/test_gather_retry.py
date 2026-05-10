# tests/test_gather_retry.py — 数据收集质量重试测试
"""数据收集质量重试功能测试

测试内容：
1. 数据质量不足时是否返回 planning 阶段重新规划
2. 收集重试次数是否正确累加
3. 达到最大重试次数后是否继续到撰写阶段
4. 规划节点是否正确处理重试请求
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import END


class TestGatherDataQualityRetry:
    """数据收集质量重试测试"""

    def test_quality_pass_returns_drafting(self):
        """测试质量通过时进入撰写阶段"""
        from nodes.gather_data import gather_data_concurrent

        state = {
            "topic": "AI发展趋势",
            "search_queries": ["人工智能", "大语言模型"],
            "outline": ["概述", "技术", "应用"],
            "max_concurrent": 5,
            "quality_threshold": 0.55,
            "gather_retry_count": 0,
            "max_gather_retry": 3,
        }

        # Mock 异步收集和 LLM 调用
        with patch("nodes.gather_data.asyncio.run") as mock_run:
            with patch("nodes.gather_data.chat") as mock_chat:
                # 模拟收集结果
                mock_run.return_value = (
                    [{"query": "人工智能", "content": "内容"}],  # sources
                    [{"query": "人工智能", "relevance_score": 0.8}],  # extracted_list
                    1000,  # collection_time_ms
                )

                # 模拟质量评分 - 通过
                mock_chat.return_value = '{"overall_quality_score": 0.8, "quality_passed": true, "suggestions": []}'

                result = gather_data_concurrent(state)

                # 应该进入撰写阶段
                assert result["current_step"] == "drafting", "质量通过应进入 drafting"
                assert result["gather_retry_count"] == 0, "成功后应重置重试计数"

    def test_quality_fail_returns_planning_for_retry(self):
        """测试质量不足时返回规划阶段重新规划"""
        from nodes.gather_data import gather_data_concurrent

        state = {
            "topic": "AI发展趋势",
            "search_queries": ["人工智能", "大语言模型"],
            "outline": ["概述", "技术", "应用"],
            "max_concurrent": 5,
            "quality_threshold": 0.55,
            "gather_retry_count": 0,
            "max_gather_retry": 3,
        }

        with patch("nodes.gather_data.asyncio.run") as mock_run:
            with patch("nodes.gather_data.chat") as mock_chat:
                mock_run.return_value = (
                    [{"query": "人工智能", "content": "内容"}],
                    [{"query": "人工智能", "relevance_score": 0.3}],
                    1000,
                )

                # 模拟质量评分 - 不通过
                mock_chat.return_value = '{"overall_quality_score": 0.4, "quality_passed": false, "suggestions": ["增加更多检索词"]}'

                result = gather_data_concurrent(state)

                # 应该返回规划阶段
                assert result["current_step"] == "planning", "质量不足应返回 planning"
                assert result["gather_retry_count"] == 1, "重试计数应增加到 1"

    def test_max_retry_reached_continues_to_drafting(self):
        """测试达到最大重试次数后继续到撰写阶段"""
        from nodes.gather_data import gather_data_concurrent

        state = {
            "topic": "AI发展趋势",
            "search_queries": ["人工智能", "大语言模型"],
            "outline": ["概述", "技术", "应用"],
            "max_concurrent": 5,
            "quality_threshold": 0.55,
            "gather_retry_count": 3,  # 已经达到最大重试次数
            "max_gather_retry": 3,
        }

        with patch("nodes.gather_data.asyncio.run") as mock_run:
            with patch("nodes.gather_data.chat") as mock_chat:
                mock_run.return_value = (
                    [{"query": "人工智能", "content": "内容"}],
                    [{"query": "人工智能", "relevance_score": 0.3}],
                    1000,
                )

                # 模拟质量评分 - 仍然不通过
                mock_chat.return_value = '{"overall_quality_score": 0.4, "quality_passed": false, "suggestions": []}'

                result = gather_data_concurrent(state)

                # 达到最大重试次数，应该继续到撰写阶段
                assert result["current_step"] == "drafting", "达到最大重试应继续到 drafting"
                assert result["gather_retry_count"] == 3, "重试计数保持不变"

    def test_retry_accumulation(self):
        """测试重试次数正确累加"""
        from nodes.gather_data import gather_data_concurrent

        # 第一次重试
        state = {
            "topic": "测试主题",
            "search_queries": ["关键词"],
            "outline": ["章节1"],
            "max_concurrent": 5,
            "quality_threshold": 0.7,
            "gather_retry_count": 0,
            "max_gather_retry": 3,
        }

        with patch("nodes.gather_data.asyncio.run") as mock_run:
            with patch("nodes.gather_data.chat") as mock_chat:
                mock_run.return_value = ([{"content": "test"}], [{}], 500)
                mock_chat.return_value = '{"overall_quality_score": 0.5, "quality_passed": false, "suggestions": []}'

                result1 = gather_data_concurrent(state)
                assert result1["gather_retry_count"] == 1

                # 第二次重试
                state["gather_retry_count"] = result1["gather_retry_count"]
                result2 = gather_data_concurrent(state)
                assert result2["gather_retry_count"] == 2


class TestPlanNodeRetry:
    """规划节点重试测试"""

    def test_plan_retry_generates_new_queries(self):
        """测试重试时生成新的检索词"""
        from nodes.plan import plan_tasks

        state = {
            "topic": "AI发展趋势",
            "abstract": "",
            "report_type": "research",
            "language": "中文",
            "gather_retry_count": 1,  # 表示是重试
            "search_queries": ["人工智能", "机器学习"],  # 之前的检索词
            "revision_instructions": ["数据不够全面", "缺乏最新信息"],  # 改进建议
        }

        with patch("nodes.plan._get_wiki_context", return_value=""):
            with patch("nodes.plan.chat_with_usage") as mock_chat:
                # 模拟返回新的检索词
                mock_chat.return_value = (
                    '{"outline": ["概述", "技术", "应用", "展望"], "search_queries": ["人工智能2024发展趋势", "大语言模型最新进展", "AI技术全面分析"]}',
                    {"prompt_tokens": 100, "completion_tokens": 50},
                )

                result = plan_tasks(state)

                # 验证返回了新的检索词
                assert result["current_step"] == "researching"
                assert len(result["search_queries"]) == 3
                # 新检索词应该不同于原来的
                assert "人工智能2024发展趋势" in result["search_queries"]

    def test_plan_first_time_uses_standard_prompt(self):
        """测试首次规划使用标准提示词"""
        from nodes.plan import plan_tasks

        state = {
            "topic": "AI发展趋势",
            "abstract": "",
            "report_type": "research",
            "language": "中文",
            "gather_retry_count": 0,  # 首次规划
        }

        with patch("nodes.plan._get_wiki_context", return_value=""):
            with patch("nodes.plan.chat_with_usage") as mock_chat:
                mock_chat.return_value = (
                    '{"outline": ["概述", "技术", "应用"], "search_queries": ["人工智能", "机器学习"]}',
                    {"prompt_tokens": 100, "completion_tokens": 50},
                )

                result = plan_tasks(state)

                assert result["current_step"] == "researching"
                assert len(result["outline"]) == 3


class TestRouteAfterGather:
    """收集后路由测试"""

    def test_route_to_planning_on_retry(self):
        """测试重试时路由到规划节点"""
        from graph import route_after_gather

        state = {
            "current_step": "planning",  # gather_data 返回 planning
            "error_msg": None,
        }

        result = route_after_gather(state)
        assert result == "planning", "应该路由到 planning 节点"

    def test_route_to_generate_draft_on_success(self):
        """测试成功时路由到撰写节点"""
        from graph import route_after_gather

        state = {
            "current_step": "drafting",
            "error_msg": None,
        }

        result = route_after_gather(state)
        assert result == "generate_draft", "应该路由到 generate_draft 节点"

    def test_route_to_end_on_error(self):
        """测试错误时路由到结束"""
        from graph import route_after_gather

        state = {
            "current_step": "drafting",
            "error_msg": "收集失败",
        }

        result = route_after_gather(state)
        assert result == END, "错误时应该结束"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
