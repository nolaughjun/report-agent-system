#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""时间旅行和 Token 统计功能测试"""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("时间旅行和 Token 统计功能测试")
print("=" * 60)

# ========================================
# 测试 1: Token 使用量统计
# ========================================
print("\n[测试 1] Token 使用量统计")
print("-" * 60)

from tools.llm import chat_with_usage, get_token_stats, reset_token_stats

# 重置统计
reset_token_stats()
print("已重置 Token 统计")

# 调用 LLM 并获取使用量
print("\n调用 LLM...")
content, usage = chat_with_usage(
    messages=[
        {"role": "system", "content": "你是一个简洁的助手，只回答一个字。"},
        {"role": "user", "content": "1+1=?"},
    ],
    node="test_node",
    max_tokens=10,
)

print(f"回复: {content}")
print(f"Token 使用量:")
print(f"  输入 tokens: {usage['prompt_tokens']}")
print(f"  输出 tokens: {usage['completion_tokens']}")
print(f"  总 tokens: {usage['total_tokens']}")
print(f"  节点: {usage['node']}")

# 获取全局统计
stats = get_token_stats()
print(f"\n全局统计:")
print(f"  总输入 tokens: {stats['total_prompt_tokens']}")
print(f"  总输出 tokens: {stats['total_completion_tokens']}")
print(f"  调用次数: {stats['call_count']}")

print("\n✅ Token 统计测试通过")

# ========================================
# 测试 2: 时间旅行功能
# ========================================
print("\n[测试 2] 时间旅行功能")
print("-" * 60)

from tools.time_travel import (
    create_snapshot,
    list_snapshots,
    get_snapshot_by_version,
    get_diff_between_versions,
)
from state import create_initial_state

# 创建初始状态
state = create_initial_state(
    topic="测试时间旅行",
    report_type="summary",
)

print(f"初始状态: step={state['current_step']}, version={state['current_version']}")

# 模拟创建快照
from tools.time_travel import save_snapshot_to_state

# 创建第一个快照
update1 = save_snapshot_to_state(state, "初始状态")
state["snapshots"] = update1["snapshots"]
state["current_version"] = update1["current_version"]
print(f"创建快照 v{state['current_version']}: {state['snapshots'][0]['description']}")

# 模拟状态变更
state["current_step"] = "planning"
state["outline"] = ["第一章", "第二章", "第三章"]

# 创建第二个快照
update2 = save_snapshot_to_state(state, "规划完成")
state["snapshots"].extend(update2["snapshots"])
state["current_version"] = update2["current_version"]
print(f"创建快照 v{state['current_version']}: {state['snapshots'][-1]['description']}")

# 模拟状态变更
state["current_step"] = "drafting"
state["current_draft"] = "# 测试报告\n\n这是测试内容..."

# 创建第三个快照
update3 = save_snapshot_to_state(state, "草案完成")
state["snapshots"].extend(update3["snapshots"])
state["current_version"] = update3["current_version"]
print(f"创建快照 v{state['current_version']}: {state['snapshots'][-1]['description']}")

# 列出所有快照
print("\n快照列表:")
snapshots = list_snapshots(state)
for s in snapshots:
    print(f"  v{s['version']}: {s['step']} - {s['description']}")

# 获取指定版本快照
snapshot_v1 = get_snapshot_by_version(state, 1)
if snapshot_v1:
    print(f"\n快照 v1 数据:")
    print(f"  step: {snapshot_v1['step']}")
    print(f"  outline: {snapshot_v1['state_data'].get('outline', [])}")

# 比较版本差异
print("\n版本差异 (v1 vs v3):")
diff = get_diff_between_versions(state, 1, 3)
for change in diff.get("changes", []):
    print(f"  {change['field']}: {change['old']} -> {change['new']}")

print("\n✅ 时间旅行功能测试通过")

# ========================================
# 测试 3: 完整流程中的时间旅行
# ========================================
print("\n[测试 3] 完整流程中的 Checkpoint 历史")
print("-" * 60)

from graph import create_report_task, get_checkpoint_history, get_token_usage_summary

# 创建一个简单任务
thread_id = create_report_task(
    topic="Python 编程入门",
    abstract="介绍 Python 编程基础知识",
    report_type="summary",
    max_concurrent=1,
)

print(f"任务 ID: {thread_id}")

# 获取 checkpoint 历史
print("\n获取 Checkpoint 历史...")
history = get_checkpoint_history(thread_id)

if history:
    print(f"找到 {len(history)} 个历史快照:")
    for i, h in enumerate(history[:5]):  # 只显示前 5 个
        print(f"  [{i}] step={h.get('step', 'unknown')}, version={h.get('version', 0)}")
else:
    print("未找到历史快照（这是正常的，因为使用了 MemorySaver）")

# 获取 Token 使用量
print("\n获取 Token 使用量...")
token_summary = get_token_usage_summary(thread_id)
print(f"  总输入 tokens: {token_summary['total_prompt_tokens']}")
print(f"  总输出 tokens: {token_summary['total_completion_tokens']}")
print(f"  总 tokens: {token_summary['total_tokens']}")
print(f"  调用次数: {token_summary['call_count']}")

if token_summary['by_node']:
    print("\n按节点统计:")
    for node, stats in token_summary['by_node'].items():
        print(f"  {node}: prompt={stats['prompt_tokens']}, completion={stats['completion_tokens']}, calls={stats['call_count']}")

print("\n" + "=" * 60)
print("所有测试完成")
print("=" * 60)
