#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""人工审核流程自动化测试

测试完整的人工审核流程（自动模式）：
1. 创建任务并执行到人工审核暂停点
2. 验证任务状态是否暂停在 human_review
3. 获取草案内容
4. 自动提交决策
5. 验证最终输出
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# 设置控制台编码
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("人工审核流程自动化测试")
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

# ========================================
# 阶段 2: 获取当前状态，验证暂停点
# ========================================
print("\n[阶段 2] 验证任务状态...")

state = get_task_state(thread_id)
current_step = state.get("current_step", "unknown")

print(f"    当前步骤: {current_step}")

# 验证是否暂停在人工审核节点
if current_step == "reviewing":
    print("    ✅ 任务已暂停在审核阶段，等待人工决策")
else:
    print(f"    ⚠️ 当前步骤: {current_step}")

# 显示质量评分
quality_checks = state.get("quality_checks", [])
if quality_checks:
    last_quality = quality_checks[-1]
    score = last_quality.get("score", 0)
    print(f"    质量评分: {score:.2f}")
    if last_quality.get("issue"):
        print(f"    问题: {last_quality['issue']}")

# 显示草案
draft = state.get("current_draft", "")
if draft:
    print(f"\n[阶段 2.1] 报告草案预览 (前300字):")
    print("-" * 40)
    print(draft[:300])
    print("...")
    print("-" * 40)
    print(f"    报告总字数: {len(draft)}")
else:
    print("    ⚠️ 未找到草案内容")

# ========================================
# 阶段 3: 模拟人工审核决策 - 通过
# ========================================
print("\n[阶段 3] 模拟人工审核决策...")
print("    决策: approve (通过)")

# ========================================
# 阶段 4: 恢复执行
# ========================================
print("\n[阶段 4] 恢复执行...")
print("-" * 60)

result = resume_with_decision(thread_id, "approve", "")

# ========================================
# 阶段 5: 输出结果
# ========================================
print("\n[阶段 5] 执行结果")
print("-" * 60)

if result.get("current_step") == "finished":
    print("    状态: ✅ 完成")
    export_path = result.get("export_path", "N/A")
    print(f"    导出路径: {export_path}")

    # 性能指标
    metrics = result.get("metrics")
    if metrics:
        print("\n    性能指标:")
        print(f"      总耗时: {metrics.get('total_time_ms', 0)} ms")
        print(f"      收集耗时: {metrics.get('collection_time_ms', 0)} ms")
        print(f"      并发任务: {metrics.get('concurrent_tasks', 0)}")
        print(f"      成功率: {metrics.get('success_rate', 0):.0%}")

    # 检查文件
    final_report = result.get("final_report", "")
    if final_report:
        print(f"\n    最终报告字数: {len(final_report)}")

    # 检查 PDF 导出
    pdf_path = export_path.replace('.md', '.pdf') if export_path.endswith('.md') else None
    if pdf_path and os.path.exists(pdf_path):
        file_size = os.path.getsize(pdf_path)
        print(f"    PDF 文件: {pdf_path} ({file_size/1024:.1f} KB)")
    elif export_path != "N/A":
        print(f"    ⚠️ PDF 文件未生成")

else:
    step = result.get("current_step", "unknown")
    print(f"    状态: {step}")
    error = result.get("error_msg")
    if error:
        print(f"    错误: {error}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)

# ========================================
# 测试修订流程
# ========================================
print("\n\n" + "=" * 60)
print("测试修订流程")
print("=" * 60)

print("\n[阶段 6] 创建新任务测试修订功能...")

thread_id2 = create_report_task(
    topic="Python 编程最佳实践",
    abstract="介绍 Python 编程的最佳实践和技巧",
    report_type="summary",
    language="中文",
    max_concurrent=2,
)

print(f"    任务ID: {thread_id2}")

# 先测试修订
print("\n[阶段 7] 模拟人工审核决策 - 需要修订...")
print("    决策: revise")
print("    修改意见: 请增加更多代码示例")

result_revise = resume_with_decision(thread_id2, "revise", "请增加更多代码示例")

print(f"\n    修订后状态: {result_revise.get('current_step')}")
retry_count = result_revise.get("retry_count", 0)
print(f"    重试次数: {retry_count}")

# 再次审核通过
print("\n[阶段 8] 再次审核 - 通过...")
result_final = resume_with_decision(thread_id2, "approve", "")

if result_final.get("current_step") == "finished":
    print(f"    ✅ 完成: {result_final.get('export_path')}")
else:
    print(f"    状态: {result_final.get('current_step')}")

print("\n" + "=" * 60)
print("所有测试完成")
print("=" * 60)
