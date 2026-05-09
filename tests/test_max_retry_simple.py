#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""max_retry 简单测试

直接测试路由函数逻辑
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("max_retry 路由函数测试")
print("=" * 60)

# 直接测试路由函数
from graph import route_after_review, route_after_human
from langgraph.graph import END

# 模拟状态
class MockState(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__dict__.update(kwargs)

# 测试 1: 质量达标 → human_review
print("\n[测试 1] 质量达标 → human_review")
state1 = MockState(
    error_msg=None,
    quality_checks=[{"score": 0.8}],
    quality_threshold=0.55,
    retry_count=0,
    max_retry=3,
)
result1 = route_after_review(state1)
print(f"  结果: {result1}")
assert result1 == "human_review", f"期望 human_review, 得到 {result1}"
print("  ✅ 通过")

# 测试 2: 质量不达标，retry_count < max_retry → revising
print("\n[测试 2] 质量不达标，retry_count < max_retry → revising")
state2 = MockState(
    error_msg=None,
    quality_checks=[{"score": 0.3}],
    quality_threshold=0.55,
    retry_count=1,
    max_retry=3,
)
result2 = route_after_review(state2)
print(f"  结果: {result2}")
assert result2 == "revising", f"期望 revising, 得到 {result2}"
print("  ✅ 通过")

# 测试 3: 质量不达标，retry_count >= max_retry → END
print("\n[测试 3] 质量不达标，retry_count >= max_retry → END")
state3 = MockState(
    error_msg=None,
    quality_checks=[{"score": 0.3}],
    quality_threshold=0.55,
    retry_count=3,
    max_retry=3,
)
result3 = route_after_review(state3)
print(f"  结果: {result3}")
assert result3 == END, f"期望 END, 得到 {result3}"
print("  ✅ 通过")

# 测试 4: 人工审核 approve → finalize
print("\n[测试 4] 人工审核 approve → finalize")
state4 = MockState(
    human_decision="approve",
    retry_count=0,
    max_retry=3,
)
result4 = route_after_human(state4)
print(f"  结果: {result4}")
assert result4 == "finalize", f"期望 finalize, 得到 {result4}"
print("  ✅ 通过")

# 测试 5: 人工审核 revise，retry_count < max_retry → revising
print("\n[测试 5] 人工审核 revise，retry_count < max_retry → revising")
state5 = MockState(
    human_decision="revise",
    retry_count=1,
    max_retry=3,
)
result5 = route_after_human(state5)
print(f"  结果: {result5}")
assert result5 == "revising", f"期望 revising, 得到 {result5}"
print("  ✅ 通过")

# 测试 6: 人工审核 revise，retry_count >= max_retry → END
print("\n[测试 6] 人工审核 revise，retry_count >= max_retry → END")
state6 = MockState(
    human_decision="revise",
    retry_count=3,
    max_retry=3,
)
result6 = route_after_human(state6)
print(f"  结果: {result6}")
assert result6 == END, f"期望 END, 得到 {result6}"
print("  ✅ 通过")

print("\n" + "=" * 60)
print("所有路由函数测试通过")
print("=" * 60)
