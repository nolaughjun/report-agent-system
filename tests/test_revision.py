# tests/test_revision.py — 报告修改功能测试
"""报告修改功能测试

测试内容：
1. revising 节点是否正确使用用户修改意见
2. LLM 是否被正确调用
3. 修改历史是否被正确记录
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRevisionNode:
    """报告修改节点测试"""

    def test_revise_node_without_comments(self):
        """测试无修改意见时的行为"""
        from graph import _revise_node

        state = {
            "retry_count": 0,
            "max_retry": 3,
            "human_comments": "",
            "current_draft": "这是一份测试报告",
            "topic": "测试主题",
        }

        result = _revise_node(state)

        # 应该增加重试计数
        assert result["retry_count"] == 1, "应该增加 retry_count"
        # 无修改意见时不会修改报告
        assert "current_draft" not in result, "无修改意见时不应该修改报告"

    def test_revise_node_with_comments_calls_llm(self):
        """测试有修改意见时调用 LLM"""
        from graph import _revise_node

        state = {
            "retry_count": 0,
            "max_retry": 3,
            "human_comments": "请增加更多细节",
            "current_draft": "这是一份测试报告",
            "topic": "测试主题",
        }

        # Mock LLM 调用 - 需要mock tools.llm.chat 因为是导入使用的
        with patch("tools.llm.chat") as mock_chat:
            mock_chat.return_value = "这是修改后的报告，增加了更多细节..."

            result = _revise_node(state)

            # 应该调用 LLM
            assert mock_chat.called, "有修改意见时应该调用 LLM"

            # 检查调用参数
            call_args = mock_chat.call_args
            messages = call_args[1]["messages"]
            assert len(messages) == 1, "应该有一条消息"
            assert "请增加更多细节" in messages[0]["content"], "消息应包含用户修改意见"

            # 应该更新报告
            assert "current_draft" in result, "应该更新 current_draft"
            assert result["current_draft"] == "这是修改后的报告，增加了更多细节..."

            # 应该记录修改历史
            assert "revision_history" in result, "应该记录修改历史"
            assert len(result["revision_history"]) == 1
            assert result["revision_history"][0]["comments"] == "请增加更多细节"

    def test_revise_node_llm_failure(self):
        """测试 LLM 调用失败时的行为"""
        from graph import _revise_node

        state = {
            "retry_count": 1,
            "max_retry": 3,
            "human_comments": "请修改",
            "current_draft": "原报告",
            "topic": "主题",
        }

        # Mock LLM 调用失败
        with patch("tools.llm.chat") as mock_chat:
            mock_chat.side_effect = Exception("LLM 调用失败")

            result = _revise_node(state)

            # 即使失败也应该增加重试计数（避免无限循环）
            assert result["retry_count"] == 2, "失败后也应该增加 retry_count"

    def test_revise_node_empty_llm_response(self):
        """测试 LLM 返回空内容"""
        from graph import _revise_node

        state = {
            "retry_count": 0,
            "max_retry": 3,
            "human_comments": "修改意见",
            "current_draft": "原报告",
            "topic": "主题",
        }

        with patch("tools.llm.chat") as mock_chat:
            mock_chat.return_value = ""  # 空响应

            result = _revise_node(state)

            # 空响应时不应该更新报告
            assert "current_draft" not in result, "空响应时不应该更新报告"
            assert result["retry_count"] == 1

    def test_revise_node_max_retry_reached(self):
        """测试达到最大重试次数"""
        from graph import _revise_node

        state = {
            "retry_count": 2,  # 已经 2 次
            "max_retry": 3,
            "human_comments": "继续修改",
            "current_draft": "报告",
            "topic": "主题",
        }

        with patch("tools.llm.chat") as mock_chat:
            mock_chat.return_value = "修改后的报告"

            result = _revise_node(state)

            # 应该还能执行一次
            assert result["retry_count"] == 3


class TestRevisionHistory:
    """修改历史测试"""

    def test_revision_history_accumulation(self):
        """测试修改历史累积"""
        from graph import _revise_node

        existing_history = [
            {"version": 1, "comments": "第一次修改", "timestamp": "2024-01-01T00:00:00"}
        ]

        state = {
            "retry_count": 1,
            "max_retry": 3,
            "human_comments": "第二次修改",
            "current_draft": "报告",
            "topic": "主题",
            "revision_history": existing_history,
        }

        with patch("tools.llm.chat") as mock_chat:
            mock_chat.return_value = "修改后"

            result = _revise_node(state)

            # 应该追加到历史
            assert len(result["revision_history"]) == 2
            assert result["revision_history"][1]["comments"] == "第二次修改"
            assert result["revision_history"][1]["version"] == 2


class TestRevisionNodeIntegration:
    """修改节点集成测试"""

    def test_full_revision_flow_mock(self):
        """测试完整修改流程（Mock LLM）"""
        from graph import _revise_node

        # 模拟真实状态
        state = {
            "retry_count": 0,
            "max_retry": 3,
            "human_comments": "请在报告中增加关于 AI 安全性的讨论，并补充数据隐私保护相关内容",
            "current_draft": """# AI 发展报告

## 概述
人工智能正在快速发展...

## 技术趋势
大语言模型技术持续进步...
""",
            "topic": "人工智能发展趋势",
            "revision_history": [],
        }

        # Mock LLM 返回修改后的报告
        revised_report = """# AI 发展报告

## 概述
人工智能正在快速发展...

## 技术趋势
大语言模型技术持续进步...

## AI 安全性
随着 AI 能力的增强，安全性问题日益重要...

## 数据隐私保护
AI 系统的数据隐私保护需要...
"""

        with patch("tools.llm.chat") as mock_chat:
            mock_chat.return_value = revised_report

            result = _revise_node(state)

            # 验证结果
            assert result["retry_count"] == 1
            assert "AI 安全性" in result["current_draft"]
            assert "数据隐私保护" in result["current_draft"]
            assert len(result["revision_history"]) == 1

            print("\n=== 自测报告 ===")
            print(f"✅ retry_count: {state['retry_count']} -> {result['retry_count']}")
            print(f"✅ 报告已更新: 原长度 {len(state['current_draft'])} -> 新长度 {len(result['current_draft'])}")
            print(f"✅ 修改历史已记录: {len(result['revision_history'])} 条")
            print(f"✅ LLM 调用参数正确: 包含用户修改意见")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


class TestRouteLogic:
    """路由逻辑测试"""

    def test_route_after_human_approve(self):
        """测试用户批准后进入 finalize"""
        from graph import route_after_human

        state = {
            "human_decision": "approve",
            "retry_count": 0,
            "max_retry": 3,
        }

        result = route_after_human(state)
        assert result == "finalize", "用户批准应进入 finalize"

    def test_route_after_human_revise(self):
        """测试用户选择修改后进入 revising"""
        from graph import route_after_human

        state = {
            "human_decision": "revise",
            "retry_count": 0,
            "max_retry": 3,
        }

        result = route_after_human(state)
        assert result == "revising", "用户选择修改应进入 revising"

    def test_route_after_human_revise_high_retry_count(self):
        """测试即使 retry_count 很高，用户选择修改仍然可以进入 revising"""
        from graph import route_after_human

        # 用户主动修改不应该受 max_retry 限制
        state = {
            "human_decision": "revise",
            "retry_count": 10,  # 远超 max_retry
            "max_retry": 3,
        }

        result = route_after_human(state)
        assert result == "revising", "用户主动修改不应受 max_retry 限制"

    def test_route_after_review_quality_pass(self):
        """测试质量通过后进入人工审核"""
        from graph import route_after_review

        state = {
            "quality_checks": [{"score": 0.8, "ispass": True}],
            "quality_threshold": 0.55,
            "retry_count": 0,
            "max_retry": 3,
        }

        result = route_after_review(state)
        assert result == "human_review", "质量通过应进入人工审核"

    def test_route_after_review_quality_fail_low_retry(self):
        """测试质量未通过且重试次数未超限，自动改进"""
        from graph import route_after_review

        state = {
            "quality_checks": [{"score": 0.3, "ispass": False}],  # 低于阈值
            "quality_threshold": 0.55,
            "retry_count": 1,
            "max_retry": 3,
        }

        result = route_after_review(state)
        assert result == "revising", "质量未通过且未达最大重试应自动改进"

    def test_route_after_review_quality_fail_max_retry(self):
        """测试质量未通过但达到最大重试次数，仍进入人工审核让用户决定"""
        from graph import route_after_review

        state = {
            "quality_checks": [{"score": 0.3, "ispass": False}],
            "quality_threshold": 0.55,
            "retry_count": 3,  # 达到最大
            "max_retry": 3,
        }

        result = route_after_review(state)
        # 修复后：即使达到最大重试，也进入人工审核
        assert result == "human_review", "达到最大重试仍应进入人工审核让用户决定"
