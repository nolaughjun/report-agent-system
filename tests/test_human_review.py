#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""人工审核流程测试

测试完整的人工审核流程：
1. 创建任务并执行到人工审核暂停点
2. 显示报告草案供人工审阅
3. 等待人工输入决策
4. 根据决策继续执行或修改
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("人工审核流程测试")
print("=" * 60)

from graph import app, create_report_task, get_task_state, resume_with_decision

# 测试主题
topic = "2026年人工智能产业发展趋势"

print(f"\n主题: {topic}")
print("类型: research")
print("最大并发: 3")
print("-" * 60)

# ========================================
# 阶段 1: 创建任务，执行到人工审核暂停点
# ========================================
print("\n[阶段 1] 创建任务并生成草案...")

thread_id = create_report_task(
    topic=topic,
    abstract="分析人工智能产业的发展趋势和未来展望",
    report_type="research",
    language="中文",
    max_concurrent=3,
)

print(f"    任务ID: {thread_id}")
print("    状态: 已暂停在人工审核节点")

# ========================================
# 阶段 2: 获取当前状态，显示草案
# ========================================
print("\n[阶段 2] 报告草案预览")
print("-" * 60)

state = get_task_state(thread_id)

# 显示质量评分
quality_checks = state.get("quality_checks", [])
if quality_checks:
    last_quality = quality_checks[-1]
    score = last_quality.get("score", 0)
    print(f"质量评分: {score:.2f}")
    if last_quality.get("issue"):
        print(f"问题: {last_quality['issue']}")

# 显示草案
draft = state.get("current_draft", "")
if draft:
    print(f"\n报告预览 (前500字):")
    print("-" * 40)
    print(draft[:500])
    print("...")
    print("-" * 40)
    print(f"报告总字数: {len(draft)}")
else:
    print("警告: 未找到草案内容")

# ========================================
# 阶段 3: 模拟人工审核决策
# ========================================
print("\n[阶段 3] 人工审核")
print("-" * 60)
print("选项:")
print("  1 - 通过 (approve)")
print("  2 - 需要修改 (revise) - 输入修改意见")
print("  3 - 退出")

choice = input("\n请选择 [1/2/3]: ").strip()

if choice == "3":
    print("已取消")
    sys.exit(0)

decision = "approve" if choice != "2" else "revise"
comments = ""

if decision == "revise":
    comments = input("请输入修改意见: ").strip()

print(f"\n决策: {decision}")
if comments:
    print(f"修改意见: {comments}")

# ========================================
# 阶段 4: 恢复执行
# ========================================
print("\n[阶段 4] 恢复执行...")
print("-" * 60)

result = resume_with_decision(thread_id, decision, comments)

# ========================================
# 阶段 5: 输出结果
# ========================================
print("\n[阶段 5] 执行结果")
print("-" * 60)

if result.get("current_step") == "finished":
    print("状态: 完成")
    export_path = result.get("export_path", "N/A")
    print(f"导出路径: {export_path}")

    # 性能指标
    metrics = result.get("metrics")
    if metrics:
        print("\n性能指标:")
        print(f"  总耗时: {metrics.get('total_time_ms', 0)} ms")
        print(f"  收集耗时: {metrics.get('collection_time_ms', 0)} ms")
        print(f"  并发任务: {metrics.get('concurrent_tasks', 0)}")
        print(f"  成功率: {metrics.get('success_rate', 0):.0%}")

    # 检查文件
    final_report = result.get("final_report", "")
    if final_report:
        print(f"\n最终报告字数: {len(final_report)}")

elif result.get("current_step") == "human_review":
    # 需要再次审核（修改后）
    print("状态: 等待再次审核")
    print("\n修改后的草案预览:")
    new_draft = result.get("current_draft", "")
    if new_draft:
        print(new_draft[:300])
        print("...")

    # 再次决策
    print("\n请再次审核:")
    choice2 = input("通过? [Y/n]: ").strip().lower()
    decision2 = "revise" if choice2 == "n" else "approve"

    result2 = resume_with_decision(thread_id, decision2, "")
    if result2.get("current_step") == "finished":
        print(f"\n完成! 导出路径: {result2.get('export_path')}")
    else:
        print(f"\n状态: {result2.get('current_step')}")

else:
    step = result.get("current_step", "unknown")
    print(f"状态: {step}")
    error = result.get("error_msg")
    if error:
        print(f"错误: {error}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
