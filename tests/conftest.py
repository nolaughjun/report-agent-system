# tests/conftest.py — pytest 配置
"""pytest 配置和共享 fixtures"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 添加源码路径
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_llm_response():
    """Mock LLM 响应"""
    def _mock_response(content: str):
        mock = MagicMock()
        mock.choices = [MagicMock(message=MagicMock(content=content))]
        return mock
    return _mock_response


@pytest.fixture
def mock_deepseek(mock_llm_response):
    """Mock DeepSeek 客户端"""
    with patch("tools.llm.deepseek") as mock:
        mock.chat.completions.create.return_value = mock_llm_response('{"result": "success"}')
        yield mock


@pytest.fixture
def temp_output_dir(tmp_path):
    """临时输出目录"""
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def sample_state():
    """示例状态"""
    from state import create_initial_state

    return create_initial_state(
        topic="AI发展趋势报告",
        abstract="分析人工智能发展趋势",
        max_concurrent=3,
    )


# 设置测试环境变量
@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """设置测试环境变量"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key-for-testing")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key-for-testing")


# pytest 配置选项
def pytest_configure(config):
    """pytest 配置"""
    config.addinivalue_line("markers", "slow: 标记慢速测试")
    config.addinivalue_line("markers", "integration: 标记集成测试")
    config.addinivalue_line("markers", "asyncio: 标记异步测试")
