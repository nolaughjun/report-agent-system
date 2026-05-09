#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""完整报告系统测试（包含 PDF 导出）"""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("完整报告系统测试")
print("=" * 60)

from graph import create_report_task, get_task_state, resume_with_decision, get_token_usage_summary

# 测试主题
topic = "2026年Python编程最佳实践"

print(f"\n主题: {topic}")
print("类型: summary")
print("最大并发: 1")
print("-" * 60)

# 创建任务
print("\n[阶段 1] 创建任务...")
thread_id = create_report_task(
    topic=topic,
    abstract="介绍 Python 编程的最佳实践和技巧",
    report_type="summary",
    language="中文",
    max_concurrent=1,
)

print(f"    任务ID: {thread_id}")

# 获取状态
state = get_task_state(thread_id)
current_step = state.get("current_step", "unknown")
print(f"    当前步骤: {current_step}")

# 显示草案
draft = state.get("current_draft", "")
if draft:
    print(f"\n[阶段 2] 报告预览 (前300字):")
    print("-" * 40)
    print(draft[:300])
    print("...")
    print(f"    报告总字数: {len(draft)}")

# 自动通过
print("\n[阶段 3] 自动通过审核...")
result = resume_with_decision(thread_id, "approve", "")

print("\n[阶段 4] 执行结果")
print("-" * 60)

if result.get("current_step") == "finished":
    print("    状态: 完成")
    export_path = result.get("export_path", "N/A")
    print(f"    Markdown 路径: {export_path}")

    # 检查 PDF
    if export_path.endswith(".md"):
        pdf_path = export_path.replace(".md", ".pdf")
        if os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            print(f"    PDF 文件: {pdf_path}")
            print(f"    PDF 大小: {file_size/1024:.1f} KB")

            # 读取 Markdown 文件大小对比
            md_size = os.path.getsize(export_path)
            print(f"    Markdown 大小: {md_size/1024:.1f} KB")

            print("\n    ✅ PDF 导出成功！")
        else:
            print("    PDF 文件: 未生成")

    # Token 统计
    token_summary = get_token_usage_summary(thread_id)
    if token_summary.get("total_tokens", 0) > 0:
        print(f"\n    Token 使用量:")
        print(f"      输入: {token_summary['total_prompt_tokens']:,}")
        print(f"      输出: {token_summary['total_completion_tokens']:,}")
        print(f"      总计: {token_summary['total_tokens']:,}")

    # 性能指标
    metrics = result.get("metrics")
    if metrics:
        print(f"\n    性能指标:")
        print(f"      总耗时: {metrics.get('total_time_ms', 0):,} ms")
        print(f"      成功率: {metrics.get('success_rate', 0):.0%}")

else:
    print(f"    状态: {result.get('current_step')}")
    if result.get("error_msg"):
        print(f"    错误: {result['error_msg']}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
