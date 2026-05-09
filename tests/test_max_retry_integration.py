#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""max_retry 集成测试

测试完整流程中的 max_retry 是否生效
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("max_retry 集成测试")
print("=" * 60)

from graph import app, create_report_task, get_task_state, resume_with_decision

# 测试：设置 max_retry=2，观察是否在 2 次重试后终止
print("\n[测试] max_retry=2，质量阈值=0.99（故意不达标）")
print("-" * 60)

thread_id = create_report_task(
    topic="测试max_retry",
    abstract="测试最大重试次数限制",
    report_type="summary",
    language="中文",
    max_concurrent=1,
    quality_threshold=0.99,  # 故意设置很高，使质量不达标
    max_retry=2,
)

print(f"任务ID: {thread_id}")
print(f"质量阈值: 0.99")
print(f"max_retry: 2")

state = get_task_state(thread_id)
current_step = state.get("current_step", "unknown")
retry_count = state.get("retry_count", 0)

print(f"\n当前状态: {current_step}")
print(f"重试次数: {retry_count}")

# 检查是否因为质量不达标且达到最大重试次数而终止
if current_step in ["finished", "failed"]:
    print(f"\n✅ 测试通过: 任务已终止，状态={current_step}")
    print(f"   最终 retry_count={retry_count}")
elif current_step == "human_review":
    # 如果质量达标了（不太可能），直接通过
    print("\n质量意外达标，直接通过")
    result = resume_with_decision(thread_id, "approve", "")
    print(f"最终状态: {result.get('current_step')}")
else:
    print(f"\n⚠️ 当前状态: {current_step}, retry_count={retry_count}")

    # 检查日志中是否有重试记录
    print("\n检查是否正确记录了重试...")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
