#!/usr/bin/env python
# tests/test_full_flow.py — 完整流程测试
"""完整流程测试

测试目标：
1. 验证报告生成完整流程
2. 验证人工审核中断和恢复
3. 验证质量不达标时的处理
4. 验证用户修改意见的正确处理
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFullFlow:
    """完整流程测试"""

    def test_flow_quality_pass_user_approve(self):
        """测试：质量通过 → 用户批准 → 完成"""
        from graph import build_graph
        from state import create_initial_state

        # 构建图
        graph = build_graph()
        thread_id = "test_flow_001"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = create_initial_state(
            topic="AI发展趋势",
            quality_threshold=0.55,
        )

        # Mock 所有外部调用
        with patch("nodes.plan.chat_with_usage") as mock_plan_chat:
            with patch("nodes.gather_data.asyncio.run") as mock_gather_run:
                with patch("nodes.gather_data.chat") as mock_gather_chat:
                    with patch("nodes.draft.chat_with_usage") as mock_draft_chat:
                        with patch("nodes.review.chat_with_usage") as mock_review_chat:
                            with patch("tools.export.export_report") as mock_export:
                                    # 规划节点
                                    mock_plan_chat.return_value = (
                                        '{"outline": ["概述", "技术", "应用"], "search_queries": ["AI", "LLM"]}',
                                        {"prompt_tokens": 100, "completion_tokens": 50},
                                    )

                                    # 收集节点
                                    mock_gather_run.return_value = (
                                        [{"query": "AI", "content": "content"}],
                                        [{"query": "AI", "relevance_score": 0.8}],
                                        1000,
                                    )
                                    mock_gather_chat.return_value = '{"overall_quality_score": 0.8, "quality_passed": true, "suggestions": []}'

                                    # 撰写节点
                                    mock_draft_chat.return_value = (
                                        "# AI发展趋势报告\n\n## 概述\n这是测试报告内容...",
                                        {"prompt_tokens": 500, "completion_tokens": 300},
                                    )

                                    # 质量审核 - 通过
                                    mock_review_chat.return_value = (
                                        '{"ispass": true, "score": 0.85, "issue": "", "suggestions": []}',
                                        {"prompt_tokens": 200, "completion_tokens": 100},
                                    )

                                    # 最终化
                                    mock_export.return_value = "/tmp/report.md"

                                    # 执行到中断点
                                    result = graph.invoke(initial_state, config=config)

                                    # 验证：应该在 human_review 暂停
                                    # 检查状态
                                    state = graph.get_state(config)
                                    print(f"当前步骤: {state.values.get('current_step')}")
                                    print(f"human_decision: {state.values.get('human_decision')}")

                                    # 此时 human_decision 应该为 None
                                    assert state.values.get("human_decision") is None, "应该在等待人工决策"

                                    # 模拟用户批准
                                    graph.update_state(
                                        config,
                                        {"human_decision": "approve", "human_comments": ""},
                                        as_node="human_review",
                                    )

                                    # 继续执行
                                    final_result = graph.invoke(None, config=config)

                                    # 验证最终状态
                                    assert final_result.get("current_step") == "finished" or final_result.get("export_path"), \
                                        f"应该完成，但得到: {final_result.get('current_step')}"

    def test_flow_quality_fail_user_revise(self):
        """测试：质量不达标 → 用户输入修改意见 → 修改报告 → 完成"""
        from graph import build_graph
        from state import create_initial_state

        graph = build_graph()
        thread_id = "test_flow_002"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = create_initial_state(
            topic="测试主题",
            quality_threshold=0.7,  # 设置较高阈值
        )

        with patch("nodes.plan.chat_with_usage") as mock_plan_chat:
            with patch("nodes.gather_data.asyncio.run") as mock_gather_run:
                with patch("nodes.gather_data.chat") as mock_gather_chat:
                    with patch("nodes.draft.chat_with_usage") as mock_draft_chat:
                        with patch("nodes.review.chat_with_usage") as mock_review_chat:
                            with patch("tools.llm.chat") as mock_revise_chat:
                                with patch("tools.export.export_report") as mock_export:
                                        # 规划
                                        mock_plan_chat.return_value = (
                                            '{"outline": ["概述"], "search_queries": ["test"]}',
                                            {"prompt_tokens": 100, "completion_tokens": 50},
                                        )

                                        # 收集
                                        mock_gather_run.return_value = (
                                            [{"query": "test", "content": "content"}],
                                            [{}],
                                            500,
                                        )
                                        mock_gather_chat.return_value = '{"overall_quality_score": 0.8, "quality_passed": true, "suggestions": []}'

                                        # 撰写
                                        mock_draft_chat.return_value = (
                                            "# 测试报告\n\n内容较少",
                                            {"prompt_tokens": 200, "completion_tokens": 100},
                                        )

                                        # 质量审核 - 不通过
                                        mock_review_chat.return_value = (
                                            '{"ispass": false, "score": 0.5, "issue": "内容太短", "suggestions": ["增加更多细节"]}',
                                            {"prompt_tokens": 100, "completion_tokens": 50},
                                        )

                                        # 修订
                                        mock_revise_chat.return_value = "# 测试报告\n\n## 概述\n增加了更多细节的内容..."

                                        # 最终化
                                        mock_export.return_value = "/tmp/report_v2.md"

                                        # 执行到中断点
                                        graph.invoke(initial_state, config=config)

                                        # 获取状态
                                        state = graph.get_state(config)
                                        print(f"质量不达标后步骤: {state.values.get('current_step')}")
                                        print(f"human_decision: {state.values.get('human_decision')}")

                                        # 应该在 human_review 等待
                                        assert state.values.get("human_decision") is None, "应该在等待人工决策"

                                        # 模拟用户输入修改意见
                                        graph.update_state(
                                            config,
                                            {"human_decision": "revise", "human_comments": "请增加更多技术细节"},
                                            as_node="human_review",
                                        )

                                        # 继续执行
                                        result = graph.invoke(None, config=config)

                                        # 验证修订被调用
                                        assert mock_revise_chat.called, "应该调用 LLM 进行修订"

                                        # 验证修改意见被传递
                                        call_args = mock_revise_chat.call_args
                                        messages = call_args[1]["messages"]
                                        assert "请增加更多技术细节" in messages[0]["content"], "修改意见应该被传递给 LLM"

    def test_flow_gather_quality_retry(self):
        """测试：数据收集质量不足 → 重新规划 → 完成"""
        from nodes.gather_data import gather_data_concurrent

        state = {
            "topic": "测试主题",
            "search_queries": ["查询1", "查询2"],
            "outline": ["章节1", "章节2"],
            "max_concurrent": 5,
            "quality_threshold": 0.7,
            "gather_retry_count": 0,
            "max_gather_retry": 3,
        }

        with patch("nodes.gather_data.asyncio.run") as mock_run:
            with patch("nodes.gather_data.chat") as mock_chat:
                mock_run.return_value = (
                    [{"query": "test", "content": "内容"}],
                    [{}],
                    500,
                )
                # 质量不足
                mock_chat.return_value = '{"overall_quality_score": 0.5, "quality_passed": false, "suggestions": ["增加更多检索词"]}'

                result = gather_data_concurrent(state)

                # 应该返回 planning 重新规划
                assert result["current_step"] == "planning", f"质量不足应返回 planning，得到: {result['current_step']}"
                assert result["gather_retry_count"] == 1, "重试计数应增加"


class TestHumanReviewInterrupt:
    """人工审核中断测试"""

    def test_interrupt_before_human_review(self):
        """测试：在 human_review 前正确中断"""
        from graph import build_graph
        from state import create_initial_state

        graph = build_graph()
        thread_id = "test_interrupt_001"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = create_initial_state(topic="测试中断")

        with patch("nodes.plan.chat_with_usage") as mock_plan:
            with patch("nodes.gather_data.asyncio.run") as mock_gather:
                with patch("nodes.gather_data.chat") as mock_gather_chat:
                    with patch("nodes.draft.chat_with_usage") as mock_draft:
                        with patch("nodes.review.chat_with_usage") as mock_review:
                            mock_plan.return_value = ('{"outline": ["a"], "search_queries": ["b"]}', {"prompt_tokens": 10, "completion_tokens": 5})
                            mock_gather.return_value = ([{}], [{}], 100)
                            mock_gather_chat.return_value = '{"overall_quality_score": 0.8, "quality_passed": true, "suggestions": []}'
                            mock_draft.return_value = ("# 报告内容", {"prompt_tokens": 100, "completion_tokens": 50})
                            mock_review.return_value = ('{"ispass": true, "score": 0.8, "issue": "", "suggestions": []}', {"prompt_tokens": 50, "completion_tokens": 20})

                            # 执行
                            result = graph.invoke(initial_state, config=config)

                            # 检查状态 - 应该在 human_review 暂停
                            state = graph.get_state(config)

                            # human_decision 应该是 None（等待用户输入）
                            assert state.values.get("human_decision") is None, \
                                f"human_decision 应该为 None，实际为: {state.values.get('human_decision')}"

                            # 应该有 draft 内容
                            assert state.values.get("current_draft") is not None, "应该有报告草案"


class TestRevisionPrompt:
    """修订提示词测试"""

    def test_user_comments_not_in_output(self):
        """测试：用户修改意见不应该出现在输出中"""
        from graph import _revise_node

        state = {
            "topic": "AI发展",
            "current_draft": "# 原报告\n\n内容",
            "human_comments": "请删除这段话并增加AI安全相关内容",
            "retry_count": 0,
            "max_retry": 3,
        }

        with patch("tools.llm.chat") as mock_chat:
            # 模拟 LLM 返回
            mock_chat.return_value = "# AI发展报告\n\n## 概述\n这是关于AI发展的报告...\n\n## AI安全\nAI安全是重要话题..."

            result = _revise_node(state)

            # 验证调用
            assert mock_chat.called

            # 验证 prompt 中包含警告
            call_args = mock_chat.call_args
            prompt = call_args[1]["messages"][0]["content"]

            assert "不要出现在报告中" in prompt or "仅供参考" in prompt, \
                "prompt 应该包含警告：修改意见不要出现在报告中"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
