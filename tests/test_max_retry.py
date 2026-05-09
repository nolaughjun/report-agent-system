#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""max_retry 测试

测试 max_retry 是否正确生效：
1. 当质量不达标时，超过次数后应退出
2. 当人工审核选择 revise 时，超过次数后应退出
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 设置控制台编码
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("max_retry 测试")
print("=" * 60)

from graph import app, create_report_task, get_task_state, resume_with_decision

# 测试 1: 质量不达标时的 max_retry
print("\n[测试 1] 质量不达标时的 max_retry 限制")
print("-" * 60)

# 创建一个简单任务，设置较高的质量阈值，使得质量不达标
thread_id = create_report_task(
    topic="测试主题",
    abstract="测试 max_retry 功能",
    report_type="summary",
    language="中文",
    max_concurrent=1,
    quality_threshold=0.99,  # 设置一个非常高的阈值，确保质量不达标
    max_retry=2,  # 设置最大重试次数为 2
)

print(f"任务ID: {thread_id}")
print(f"质量阈值: 0.99 (故意设置很高)")
print(f"max_retry: 2")

state = get_task_state(thread_id)
current_step = state.get("current_step", "unknown")
retry_count = state.get("retry_count", 0)

print(f"当前步骤: {current_step}")
print(f"重试次数: {retry_count}")

# 检查是否因为质量不达标且达到最大重试次数而终止
if current_step == "finished" or current_step == "failed" or retry_count >= 2:
    print("✅ 测试通过: 达到最大重试次数后正确终止")
else:
    print(f"⚠️ 当前状态: {current_step}, 重试次数: {retry_count}")

    # 尝试人工审核
    print("\n尝试人工审核选择 revise...")
    result = resume_with_decision(thread_id, "revise", "测试修改")
    print(f"修订后状态: {result.get('current_step')}")
    print(f"修订后重试次数: {result.get('retry_count')}")

    # 再次修订
    if result.get("current_step") == "human_review":
        result2 = resume_with_decision(thread_id, "revise", "测试修改2")
        print(f"再次修订后状态: {result2.get('current_step')}")
        print(f"再次修订后重试次数: {result2.get('retry_count')}")

        # 检查是否终止
        if result2.get("current_step") in ["finished", "failed"] or result2.get("current_step") is None:
            print("✅ 测试通过: 达到最大重试次数后正确终止")
        else:
            print("❌ 测试失败: 未在达到最大重试次数后终止")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
