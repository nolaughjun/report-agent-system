# tests/test_integration.py — 集成测试
"""报告智能体系统集成测试"""
from __future__ import annotations

import pytest
import sys
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConcurrentCollection:
    """测试并发收集"""

    @pytest.mark.asyncio
    async def test_single_collection(self):
        """测试单条收集"""
        from nodes.gather_data import _collect_single_async

        with patch("nodes.gather_data.tavily_search_async") as mock_search, \
             patch("nodes.gather_data.chat") as mock_chat:

            mock_search.return_value = {
                "answer": "测试答案",
                "results": [{"title": "测试", "url": "http://test.com", "content": "内容"}]
            }
            mock_chat.return_value = json.dumps({
                "key_findings": ["发现1"],
                "summary": "摘要",
                "relevance_score": 0.8,
            })

            source, extracted, elapsed = await _collect_single_async(
                topic="AI", query="AI发展趋势", task_index=0
            )

            assert source["source_type"] == "web"
            assert source["query"] == "AI发展趋势"
            assert elapsed >= 0

    @pytest.mark.asyncio
    async def test_concurrent_collection(self):
        """测试并发收集"""
        from nodes.gather_data import _gather_concurrent

        with patch("nodes.gather_data.tavily_search_async") as mock_search, \
             patch("nodes.gather_data.chat") as mock_chat:

            mock_search.return_value = {
                "answer": "答案",
                "results": [{"title": "T", "url": "http://x.com", "content": "C"}]
            }
            mock_chat.return_value = json.dumps({
                "key_findings": ["F"],
                "summary": "S",
                "relevance_score": 0.7,
            })

            queries = ["AI", "LLM", "Agent"]
            sources, extracted, elapsed = await _gather_concurrent(
                topic="AI",
                queries=queries,
                max_concurrent=2,
            )

            assert len(sources) >= len(queries)


class TestGraphFlow:
    """测试图流程"""

    @patch("tools.llm.deepseek")
    def test_planning_node(self, mock_deepseek):
        """测试规划节点"""
        from nodes.plan import plan_tasks
        from state import create_initial_state

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps({
            "outline": ["背景", "现状", "结论"],
            "search_queries": ["AI", "LLM"]
        })))]
        mock_deepseek.chat.completions.create.return_value = mock_response

        state = create_initial_state(topic="AI发展趋势")
        result = plan_tasks(state)

        assert result["current_step"] == "researching"
        assert len(result["outline"]) == 3
        assert len(result["search_queries"]) == 2

    @patch("tools.llm.deepseek")
    def test_draft_node(self, mock_deepseek):
        """测试草案撰写节点"""
        from nodes.draft import generate_draft
        from state import create_initial_state

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="# 测试报告\n\n内容"))]
        mock_deepseek.chat.completions.create.return_value = mock_response

        state = create_initial_state(topic="测试")
        state["outline"] = ["背景", "结论"]
        state["research_sources"] = []

        result = generate_draft(state)

        assert result["current_step"] == "reviewing"
        assert result["current_draft"] is not None

    @patch("tools.llm.deepseek")
    def test_review_node(self, mock_deepseek):
        """测试审核节点"""
        from nodes.review import quality_review
        from state import create_initial_state

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps({
            "ispass": True,
            "score": 0.85,
            "issue": "",
            "suggestions": []
        })))]
        mock_deepseek.chat.completions.create.return_value = mock_response

        state = create_initial_state(topic="测试")
        state["current_draft"] = "# 测试\n\n内容"
        state["outline"] = ["背景"]

        result = quality_review(state)

        assert "quality_checks" in result
        assert result["quality_checks"][0]["ispass"] is True


class TestFinalize:
    """测试最终输出"""

    def test_finalize_node(self, tmp_path):
        """测试最终输出节点"""
        from nodes.finalize import finalize_node
        from state import create_initial_state

        state = create_initial_state(topic="测试报告")
        state["current_draft"] = "# 测试报告\n\n这是测试内容。"
        state["start_time"] = "2026-05-08T10:00:00Z"

        with patch("nodes.finalize.OUTPUT_DIR", tmp_path):
            result = finalize_node(state)

        assert result["current_step"] == "finished"
        assert result["final_report"] is not None
        assert result["metrics"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
