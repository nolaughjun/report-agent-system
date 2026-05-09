# tests/test_unit.py — 单元测试
"""报告智能体系统单元测试"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestStateCreation:
    """测试状态创建"""

    def test_create_initial_state(self):
        """测试初始状态创建"""
        from state import create_initial_state

        state = create_initial_state(topic="测试主题")

        assert state["topic"] == "测试主题"
        assert state["current_step"] == "init"
        assert state["max_concurrent"] == 5
        assert state["collection_tasks"] == []
        assert state["collection_progress"] == 0.0

    def test_create_state_with_concurrent(self):
        """测试带并发数的状态创建"""
        from state import create_initial_state

        state = create_initial_state(
            topic="测试",
            max_concurrent=10,
        )

        assert state["max_concurrent"] == 10

    def test_create_state_with_schedule(self):
        """测试带定时执行的状态创建"""
        from state import create_initial_state, create_schedule_config

        schedule = create_schedule_config(
            scheduled_time="2026-05-09T09:00:00",
            recurrence="daily",
        )

        state = create_initial_state(
            topic="测试",
            schedule=schedule,
        )

        assert state["schedule"] is not None
        assert state["schedule"]["recurrence"] == "daily"


class TestScheduleConfig:
    """测试时间施行配置"""

    def test_create_once_schedule(self):
        """测试单次执行配置"""
        from state import create_schedule_config

        schedule = create_schedule_config(
            scheduled_time="2026-05-09T09:00:00",
            recurrence="once",
        )

        assert schedule["enabled"] is True
        assert schedule["recurrence"] == "once"
        assert schedule["timezone"] == "Asia/Shanghai"

    def test_create_daily_schedule(self):
        """测试每日执行配置"""
        from state import create_schedule_config

        schedule = create_schedule_config(
            scheduled_time="09:00",
            recurrence="daily",
        )

        assert schedule["recurrence"] == "daily"


class TestAppendItem:
    """测试 append_item reducer"""

    def test_append_to_empty(self):
        """测试追加到空列表"""
        from state import append_item

        result = append_item(None, [1, 2, 3])
        assert result == [1, 2, 3]

    def test_append_to_existing(self):
        """测试追加到已有列表"""
        from state import append_item

        result = append_item([1, 2], [3, 4])
        assert result == [1, 2, 3, 4]

    def test_append_single(self):
        """测试追加单个元素"""
        from state import append_item

        result = append_item([1], 2)
        assert result == [1, 2]


class TestTimer:
    """测试计时器"""

    def test_timer_context(self):
        """测试计时器上下文"""
        from tools.llm import Timer
        import time

        with Timer("test") as t:
            time.sleep(0.1)

        assert t.elapsed_ms >= 100

    def test_timer_now_ms(self):
        """测试获取当前毫秒"""
        from tools.llm import Timer

        ms = Timer.now_ms()
        assert ms > 0


class TestExportTools:
    """测试导出工具"""

    def test_safe_filename(self):
        """测试安全文件名"""
        from tools.export import _safe_filename

        assert _safe_filename("test_report") == "test_report"
        assert _safe_filename("test<script>") == "test_"
        assert _safe_filename("测试报告") == "测试报告"

    def test_export_markdown(self, tmp_path):
        """测试 Markdown 导出"""
        from tools.export import export_markdown

        output_path = export_markdown(
            content="# 测试报告\n\n内容",
            topic="测试",
            output_dir=tmp_path,
            filename="test_report",
        )

        assert Path(output_path).exists()
        content = Path(output_path).read_text(encoding="utf-8")
        assert "测试报告" in content


class TestSchedulerNode:
    """测试时间施行节点"""

    def test_check_schedule_immediate(self):
        """测试立即执行"""
        from nodes.scheduler import check_schedule_node
        from state import create_initial_state

        state = create_initial_state(topic="测试")
        result = check_schedule_node(state)

        assert result["current_step"] == "planning"
        assert result["start_time"] is not None

    def test_check_schedule_with_schedule(self):
        """测试定时执行"""
        from nodes.scheduler import check_schedule_node
        from state import create_initial_state, create_schedule_config

        schedule = create_schedule_config(
            scheduled_time="2099-01-01T09:00:00",
            recurrence="once",
        )

        state = create_initial_state(topic="测试", schedule=schedule)
        result = check_schedule_node(state)

        assert result["current_step"] == "planning"


# pytest 入口
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
