#!/usr/bin/env python
# main.py — 并发版本报告智能体系统主入口
"""并发版本报告智能体系统主入口

特性：
1. 并发数据收集
2. 时间施行（定时执行）
3. 性能指标追踪
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("report_agent_v2.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from graph import (
    create_report_task,
    get_checkpoint_history,
    get_task_state,
    get_token_usage_summary,
    resume_with_decision,
)
from state import create_schedule_config


def print_separator(char: str = "=", length: int = 60):
    print(char * length)


def print_metrics(metrics: dict):
    """打印性能指标"""
    print("\n📊 性能指标:")
    print("-" * 40)
    print(f"  总耗时: {metrics.get('total_time_ms', 0)} ms")
    print(f"  规划耗时: {metrics.get('planning_time_ms', 0)} ms")
    print(f"  收集耗时: {metrics.get('collection_time_ms', 0)} ms")
    print(f"  撰写耗时: {metrics.get('drafting_time_ms', 0)} ms")
    print(f"  审核耗时: {metrics.get('review_time_ms', 0)} ms")
    print(f"  并发任务数: {metrics.get('concurrent_tasks', 0)}")
    print(f"  成功率: {metrics.get('success_rate', 0):.0%}")
    print("-" * 40)


def print_token_usage(token_summary: dict):
    """打印 Token 使用量统计"""
    print("\n📈 Token 使用量统计:")
    print("-" * 40)
    print(f"  总输入 tokens: {token_summary.get('total_prompt_tokens', 0):,}")
    print(f"  总输出 tokens: {token_summary.get('total_completion_tokens', 0):,}")
    print(f"  总 tokens: {token_summary.get('total_tokens', 0):,}")
    print(f"  调用次数: {token_summary.get('call_count', 0)}")

    if token_summary.get("by_node"):
        print("\n  按节点统计:")
        for node, stats in token_summary["by_node"].items():
            print(f"    {node}:")
            print(
                f"      输入: {stats['prompt_tokens']:,} | 输出: {stats['completion_tokens']:,} | 调用: {stats['call_count']}"
            )
    print("-" * 40)


def print_checkpoint_history(history: list):
    """打印 Checkpoint 历史"""
    print("\n⏱️ 执行历史 (时间旅行):")
    print("-" * 40)
    if not history:
        print("  无历史记录")
        return

    for i, h in enumerate(history[:10]):  # 显示最近 10 条
        step = h.get("step", "unknown")
        version = h.get("version", 0)
        checkpoint_id = h.get("checkpoint_id", "")[:8] if h.get("checkpoint_id") else "N/A"
        print(f"  [{i}] step={step}, v={version}, cp={checkpoint_id}")

    if len(history) > 10:
        print(f"  ... 共 {len(history)} 条记录")
    print("-" * 40)


def interactive_mode():
    """交互模式"""
    print_separator()
    print("🤖 并发版本报告智能体系统 v2.0")
    print("  特性: 并发收集 | 时间施行 | 性能追踪")
    print_separator()

    # 获取用户输入
    print("\n📝 请输入报告信息：")
    print("-" * 40)

    topic = input("报告主题（必填）: ").strip()
    if not topic:
        print("❌ 报告主题不能为空")
        return

    abstract = input("报告概要（选填）: ").strip()

    print("\n报告类型：")
    print("  1 - 研究报告 (research)")
    print("  2 - 分析报告 (analysis)")
    print("  3 - 总结报告 (summary)")
    print("  4 - 提案报告 (proposal)")

    type_choice = input("请选择 [1-4，默认1]: ").strip() or "1"
    report_types = {"1": "research", "2": "analysis", "3": "summary", "4": "proposal"}
    report_type = report_types.get(type_choice, "research")

    language = input("语言 [中文/英文，默认中文]: ").strip() or "中文"

    threshold_str = input("质量阈值 [0.0-1.0，默认0.55]: ").strip()
    try:
        quality_threshold = float(threshold_str) if threshold_str else 0.55
        quality_threshold = max(0.0, min(1.0, quality_threshold))
    except ValueError:
        quality_threshold = 0.55

    # 并发设置
    concurrent_input = input("最大并发数 [1-10，默认5]: ").strip()
    try:
        max_concurrent = min(10, max(1, int(concurrent_input))) if concurrent_input else 5
    except ValueError:
        max_concurrent = 5

    # 定时执行设置
    print("\n⏰ 时间施行设置：")
    schedule_now = input("立即执行？[Y/n]: ").strip().lower() != "n"

    schedule = None
    if not schedule_now:
        scheduled_time = input("计划执行时间 (YYYY-MM-DD HH:MM 或 HH:MM): ").strip()
        if scheduled_time:
            recurrence = input("重复模式 [once/daily/weekly/monthly，默认once]: ").strip() or "once"
            schedule = create_schedule_config(
                scheduled_time=scheduled_time,
                recurrence=recurrence,  # type: ignore
            )

    # 创建任务
    print_separator()
    print("🚀 开始生成报告...")
    print(f"   主题: {topic}")
    print(f"   类型: {report_type}")
    print(f"   语言: {language}")
    print(f"   质量阈值: {quality_threshold}")
    print(f"   最大并发: {max_concurrent}")
    print(f"   定时执行: {'否' if schedule_now else schedule.get('scheduled_time', 'N/A')}")
    print_separator()

    try:
        thread_id = create_report_task(
            topic=topic,
            abstract=abstract,
            report_type=report_type,  # type: ignore
            language=language,
            quality_threshold=quality_threshold,
            max_concurrent=max_concurrent,
            schedule=schedule,
        )

        print(f"\n✅ 任务创建成功，ID: {thread_id}")

        # 获取状态
        state = get_task_state(thread_id)
        current_step = state.get("current_step", "unknown")

        print(f"   当前步骤: {current_step}")

        if state.get("current_draft"):
            draft = state["current_draft"]
            print("\n📄 报告预览 (前500字):")
            print("-" * 40)
            print(draft[:500])
            print("...")
            print("-" * 40)
            print(f"   总字数: {len(draft)}")

            # 显示质量评分
            quality_checks = state.get("quality_checks", [])
            if quality_checks:
                last_quality = quality_checks[-1]
                score = last_quality.get("score", 0)
                print(f"\n📊 质量评分: {score:.2f}")
                if last_quality.get("issue"):
                    print(f"   问题: {last_quality['issue']}")

            # 人工审核确认
            print("\n" + "=" * 40)
            print("📋 人工审核")
            print("=" * 40)
            print("选项:")
            print("  1 - 通过 (approve)")
            print("  2 - 需要修改 (revise) - 输入修改意见")
            print("  3 - 退出")

            choice = input("\n请选择 [1/2/3]: ").strip()

            if choice == "3":
                print("已取消")
                return

            decision = "approve" if choice != "2" else "revise"
            comments = ""

            if decision == "revise":
                comments = input("请输入修改意见: ").strip()

            print(f"\n📝 决策: {decision}")
            if comments:
                print(f"   修改意见: {comments}")

            # 恢复执行
            print("\n🚀 恢复执行...")
            result = resume_with_decision(thread_id, decision, comments)

            # 处理修订后再次审核的情况
            while result.get("current_step") == "human_review":
                print("\n" + "=" * 40)
                print("📋 修订后再次审核")
                print("=" * 40)

                new_draft = result.get("current_draft", "")
                if new_draft:
                    print("\n修订后的报告预览 (前300字):")
                    print("-" * 40)
                    print(new_draft[:300])
                    print("...")
                    print("-" * 40)

                retry_count = result.get("retry_count", 0)
                print(f"   修订次数: {retry_count}")

                print("\n选项:")
                print("  1 - 通过 (approve)")
                print("  2 - 继续修改 (revise)")

                choice2 = input("\n请选择 [1/2]: ").strip()
                decision2 = "revise" if choice2 == "2" else "approve"
                comments2 = ""

                if decision2 == "revise":
                    comments2 = input("请输入修改意见: ").strip()

                print(f"\n📝 决策: {decision2}")
                result = resume_with_decision(thread_id, decision2, comments2)

            print_separator()
            if result.get("current_step") == "finished":
                print("✅ 报告生成完成！")
                export_path = result.get("export_path", "N/A")
                print(f"   导出路径: {export_path}")

                # 检查 PDF
                if export_path.endswith(".md"):
                    pdf_path = export_path.replace(".md", ".pdf")
                    import os

                    if os.path.exists(pdf_path):
                        file_size = os.path.getsize(pdf_path)
                        print(f"   PDF 文件: {pdf_path} ({file_size / 1024:.1f} KB)")
                    else:
                        print("   PDF 文件: 未生成 (请安装 MiKTeX 和 pandoc)")

                # 打印性能指标
                metrics = result.get("metrics")
                if metrics:
                    print_metrics(metrics)

                # 打印 Token 使用量统计
                token_summary = get_token_usage_summary(thread_id)
                if token_summary.get("total_tokens", 0) > 0:
                    print_token_usage(token_summary)

                # 打印执行历史
                print("\n是否查看执行历史？")
                show_history = input("查看历史 [y/N]: ").strip().lower() == "y"
                if show_history:
                    history = get_checkpoint_history(thread_id)
                    print_checkpoint_history(history)

                    # 时间旅行选项
                    print("\n是否回滚到某个历史版本？")
                    rollback = input("回滚 [y/N]: ").strip().lower() == "y"
                    if rollback:
                        version_input = input(f"输入版本号 (0-{len(history) - 1}): ").strip()
                        try:
                            version_idx = int(version_input)
                            if 0 <= version_idx < len(history):
                                checkpoint_id = history[version_idx].get("checkpoint_id", "")
                                if checkpoint_id:
                                    from graph import rollback_to_checkpoint, run_from_checkpoint

                                    restored = rollback_to_checkpoint(thread_id, checkpoint_id)
                                    print(f"\n已回滚到版本 {version_idx}")
                                    print(f"步骤: {restored.get('current_step', 'unknown')}")

                                    # 询问是否继续执行
                                    continue_exec = input("\n是否继续执行？[Y/n]: ").strip().lower() != "n"

                                    if continue_exec:
                                        restored_step = restored.get("current_step", "unknown")

                                        if restored_step in ["human_review", "reviewing"]:
                                            # 需要人工审核决策
                                            print("\n📋 人工审核（回滚后）")
                                            print("选项:")
                                            print("  1 - 通过 (approve)")
                                            print("  2 - 需要修改 (revise)")

                                            choice = input("\n请选择 [1/2]: ").strip()
                                            decision = "revise" if choice == "2" else "approve"
                                            comments = ""

                                            if decision == "revise":
                                                comments = input("请输入修改意见: ").strip()

                                            result = resume_with_decision(thread_id, decision, comments)
                                        else:
                                            # 其他步骤，自动继续
                                            result = run_from_checkpoint(thread_id, auto_approve=False)

                                        print(f"\n执行完成，最终步骤: {result.get('current_step', 'unknown')}")
                                        if result.get("export_path"):
                                            print(f"导出路径: {result['export_path']}")
                                    else:
                                        print("提示: 可以使用 resume_with_decision 或 run_from_checkpoint 继续执行")
                        except ValueError:
                            print("无效的版本号")

            else:
                print(f"⚠️ 状态: {result.get('current_step')}")
                if result.get("error_msg"):
                    print(f"   错误: {result['error_msg']}")

        print_separator()

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()


def batch_mode(topic: str, max_concurrent: int = 5):
    """批量模式"""
    print(f"🤖 批量模式：{topic}")
    print(f"   最大并发: {max_concurrent}")

    thread_id = create_report_task(
        topic=topic,
        max_concurrent=max_concurrent,
    )

    result = resume_with_decision(thread_id, "approve", "")

    if result.get("export_path"):
        print(f"✅ 完成: {result['export_path']}")
        metrics = result.get("metrics")
        if metrics:
            print(f"   总耗时: {metrics.get('total_time_ms', 0)}ms")
            print(f"   成功率: {metrics.get('success_rate', 0):.0%}")
    else:
        print(f"❌ 失败: {result.get('error_msg', '未知错误')}")


def main():
    parser = argparse.ArgumentParser(description="并发版本报告智能体系统 v2.0")
    parser.add_argument("--topic", "-t", help="报告主题")
    parser.add_argument("--concurrent", "-c", type=int, default=5, help="最大并发数")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--schedule", "-s", help="计划执行时间")
    parser.add_argument("--recurrence", "-r", default="once", help="重复模式")

    args = parser.parse_args()

    import os

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("⚠️ 警告: 未设置 DEEPSEEK_API_KEY")

    if args.interactive or not args.topic:
        interactive_mode()
    else:
        batch_mode(args.topic, args.concurrent)


if __name__ == "__main__":
    main()
