#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""报告智能体系统完整测试运行脚本

运行方式：
    python tests/run_tests.py

测试结果保存到 tests/test_results.md
"""
from __future__ import annotations

import sys
import os
import time
import json
import asyncio
from datetime import datetime
from pathlib import Path

# 设置路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# 测试结果收集
test_results = []
test_start_time = None


def log_test(name: str, status: str, message: str = "", duration_ms: int = 0):
    """记录测试结果"""
    test_results.append({
        "name": name,
        "status": status,
        "message": message,
        "duration_ms": duration_ms,
    })
    status_icon = "[PASS]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[INFO]"
    print(f"  {status_icon} {name} ({duration_ms}ms)")
    if message:
        print(f"        {message}")


def run_unit_tests():
    """运行单元测试"""
    print("\n" + "=" * 60)
    print("单元测试")
    print("=" * 60)

    # 测试 1: 状态创建
    print("\n[1] 状态创建测试...")
    try:
        from state import create_initial_state, create_schedule_config

        start = time.perf_counter()
        state = create_initial_state(
            topic="测试主题",
            max_concurrent=5,
        )
        elapsed = int((time.perf_counter() - start) * 1000)

        if state["topic"] == "测试主题" and state["max_concurrent"] == 5:
            log_test("状态创建", "PASS", "基本字段正确", elapsed)
        else:
            log_test("状态创建", "FAIL", "字段值不匹配", elapsed)
    except Exception as e:
        log_test("状态创建", "FAIL", str(e))

    # 测试 2: 时间施行配置
    print("\n[2] 时间施行配置测试...")
    try:
        from state import create_schedule_config

        start = time.perf_counter()
        schedule = create_schedule_config(
            scheduled_time="2026-05-09T09:00:00",
            recurrence="daily",
        )
        elapsed = int((time.perf_counter() - start) * 1000)

        if schedule["enabled"] and schedule["recurrence"] == "daily":
            log_test("时间施行配置", "PASS", f"模式: {schedule['recurrence']}", elapsed)
        else:
            log_test("时间施行配置", "FAIL", "配置不正确", elapsed)
    except Exception as e:
        log_test("时间施行配置", "FAIL", str(e))

    # 测试 3: append_item reducer
    print("\n[3] append_item reducer 测试...")
    try:
        from state import append_item

        start = time.perf_counter()
        result1 = append_item(None, [1, 2, 3])
        result2 = append_item([1, 2], [3, 4])
        result3 = append_item([1], 2)
        elapsed = int((time.perf_counter() - start) * 1000)

        if result1 == [1, 2, 3] and result2 == [1, 2, 3, 4] and result3 == [1, 2]:
            log_test("append_item reducer", "PASS", "所有场景通过", elapsed)
        else:
            log_test("append_item reducer", "FAIL", "结果不匹配", elapsed)
    except Exception as e:
        log_test("append_item reducer", "FAIL", str(e))

    # 测试 4: Timer
    print("\n[4] Timer 测试...")
    try:
        from tools.llm import Timer

        start = time.perf_counter()
        with Timer("test") as t:
            time.sleep(0.05)
        elapsed = int((time.perf_counter() - start) * 1000)

        if t.elapsed_ms >= 50:
            log_test("Timer", "PASS", f"测量: {t.elapsed_ms}ms", elapsed)
        else:
            log_test("Timer", "FAIL", "计时不准确", elapsed)
    except Exception as e:
        log_test("Timer", "FAIL", str(e))

    # 测试 5: 安全文件名
    print("\n[5] 安全文件名测试...")
    try:
        from tools.export import _safe_filename

        start = time.perf_counter()
        r1 = _safe_filename("test_report")
        r2 = _safe_filename("test<script>")
        r3 = _safe_filename("测试报告")
        elapsed = int((time.perf_counter() - start) * 1000)

        if r1 == "test_report" and "<script>" not in r2 and r3 == "测试报告":
            log_test("安全文件名", "PASS", "XSS防护有效", elapsed)
        else:
            log_test("安全文件名", "FAIL", "过滤不完整", elapsed)
    except Exception as e:
        log_test("安全文件名", "FAIL", str(e))


def run_async_tests():
    """运行异步测试"""
    print("\n" + "=" * 60)
    print("异步功能测试")
    print("=" * 60)

    # 测试 6: 异步搜索
    print("\n[6] 异步搜索测试...")
    try:
        from tools.llm import tavily_search_async

        async def test_search():
            start = time.perf_counter()
            result = await tavily_search_async("AI发展趋势", max_results=3)
            elapsed = int((time.perf_counter() - start) * 1000)
            return result, elapsed

        result, elapsed = asyncio.run(test_search())

        if "answer" in result and "results" in result:
            log_test("异步搜索", "PASS", f"返回 {len(result['results'])} 条结果", elapsed)
        else:
            log_test("异步搜索", "FAIL", "返回格式错误", elapsed)
    except Exception as e:
        log_test("异步搜索", "FAIL", str(e))

    # 测试 7: 并发收集
    print("\n[7] 并发收集测试...")
    try:
        from nodes.gather_data import _gather_concurrent

        async def test_concurrent():
            start = time.perf_counter()
            sources, extracted, elapsed = await _gather_concurrent(
                topic="AI发展趋势",
                queries=["AI Agent", "LLM", "多模态"],
                max_concurrent=3,
            )
            total_elapsed = int((time.perf_counter() - start) * 1000)
            return sources, total_elapsed

        sources, elapsed = asyncio.run(test_concurrent())

        if len(sources) >= 3:
            log_test("并发收集", "PASS", f"收集 {len(sources)} 条数据", elapsed)
        else:
            log_test("并发收集", "FAIL", "收集数量不足", elapsed)
    except Exception as e:
        log_test("并发收集", "FAIL", str(e))


def run_node_tests():
    """运行节点测试"""
    print("\n" + "=" * 60)
    print("节点功能测试")
    print("=" * 60)

    from unittest.mock import patch, MagicMock
    import json

    # 测试 8: 规划节点
    print("\n[8] 规划节点测试...")
    try:
        from nodes.plan import plan_tasks
        from state import create_initial_state

        with patch("nodes.plan.chat") as mock_chat:
            mock_chat.return_value = json.dumps({
                "outline": ["背景", "现状", "分析", "结论"],
                "search_queries": ["AI", "LLM", "Agent"]
            })

            start = time.perf_counter()
            state = create_initial_state(topic="AI发展趋势")
            result = plan_tasks(state)
            elapsed = int((time.perf_counter() - start) * 1000)

            if result["current_step"] == "researching" and len(result["outline"]) == 4:
                log_test("规划节点", "PASS", f"生成 {len(result['outline'])} 章节", elapsed)
            else:
                log_test("规划节点", "FAIL", "输出不正确", elapsed)
    except Exception as e:
        log_test("规划节点", "FAIL", str(e))

    # 测试 9: 草案撰写节点
    print("\n[9] 草案撰写节点测试...")
    try:
        from nodes.draft import generate_draft
        from state import create_initial_state

        with patch("nodes.draft.chat") as mock_chat:
            mock_chat.return_value = "# 测试报告\n\n这是测试内容。"

            start = time.perf_counter()
            state = create_initial_state(topic="测试")
            state["outline"] = ["背景", "结论"]
            state["research_sources"] = []
            result = generate_draft(state)
            elapsed = int((time.perf_counter() - start) * 1000)

            if result["current_step"] == "reviewing" and result["current_draft"]:
                log_test("草案撰写节点", "PASS", f"字数: {len(result['current_draft'])}", elapsed)
            else:
                log_test("草案撰写节点", "FAIL", "输出不正确", elapsed)
    except Exception as e:
        log_test("草案撰写节点", "FAIL", str(e))

    # 测试 10: 质量审核节点
    print("\n[10] 质量审核节点测试...")
    try:
        from nodes.review import quality_review
        from state import create_initial_state

        with patch("nodes.review.chat") as mock_chat:
            mock_chat.return_value = json.dumps({
                "ispass": True,
                "score": 0.85,
                "issue": "",
                "suggestions": []
            })

            start = time.perf_counter()
            state = create_initial_state(topic="测试")
            state["current_draft"] = "# 测试\n\n内容"
            state["outline"] = ["背景"]
            result = quality_review(state)
            elapsed = int((time.perf_counter() - start) * 1000)

            if result["quality_checks"][0]["ispass"]:
                log_test("质量审核节点", "PASS", f"分数: {result['quality_checks'][0]['score']}", elapsed)
            else:
                log_test("质量审核节点", "FAIL", "审核未通过", elapsed)
    except Exception as e:
        log_test("质量审核节点", "FAIL", str(e))


def run_full_flow_test():
    """运行完整流程测试"""
    print("\n" + "=" * 60)
    print("完整流程测试")
    print("=" * 60)

    print("\n[11] 自动模式完整流程测试...")
    try:
        from graph import run_automatic

        start = time.perf_counter()
        result = run_automatic(
            topic="AI Agent技术发展趋势",
            max_concurrent=3,
        )
        elapsed = int((time.perf_counter() - start) * 1000)

        if result.get("current_step") == "finished" and result.get("final_report"):
            metrics = result.get("metrics", {})
            log_test(
                "完整流程",
                "PASS",
                f"耗时: {metrics.get('total_time_ms', elapsed)}ms, 成功率: {metrics.get('success_rate', 0):.0%}",
                elapsed
            )
        else:
            step = result.get("current_step", "unknown")
            error = result.get("error_msg", "无错误信息")
            log_test("完整流程", "FAIL", f"状态: {step}, 错误: {error}", elapsed)
    except Exception as e:
        log_test("完整流程", "FAIL", str(e))


def save_results():
    """保存测试结果"""
    output_dir = Path(__file__).parent
    output_file = output_dir / "test_results.md"

    total_time = int((time.perf_counter() - test_start_time) * 1000) if test_start_time else 0

    pass_count = sum(1 for r in test_results if r["status"] == "PASS")
    fail_count = sum(1 for r in test_results if r["status"] == "FAIL")
    total_count = len(test_results)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 报告智能体系统测试结果\n\n")
        f.write(f"**测试时间**: {datetime.now().isoformat()}\n\n")
        f.write(f"**总耗时**: {total_time}ms\n\n")
        f.write(f"**测试统计**: {pass_count}/{total_count} 通过 ({pass_count/total_count*100:.0f}%)\n\n")

        f.write("## 测试详情\n\n")
        f.write("| 序号 | 测试项 | 状态 | 耗时 | 说明 |\n")
        f.write("|------|--------|------|------|------|\n")

        for i, r in enumerate(test_results, 1):
            status = "✅ PASS" if r["status"] == "PASS" else "❌ FAIL"
            f.write(f"| {i} | {r['name']} | {status} | {r['duration_ms']}ms | {r['message']} |\n")

        if fail_count > 0:
            f.write("\n## 失败测试详情\n\n")
            for r in test_results:
                if r["status"] == "FAIL":
                    f.write(f"### {r['name']}\n")
                    f.write(f"- 错误: {r['message']}\n\n")

    print(f"\n测试结果已保存到: {output_file}")


def main():
    """主函数"""
    global test_start_time
    test_start_time = time.perf_counter()

    print("=" * 60)
    print("报告智能体系统测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().isoformat()}")

    # 设置环境变量
    os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "sk-test")

    try:
        run_unit_tests()
        run_async_tests()
        run_node_tests()
        run_full_flow_test()
    except KeyboardInterrupt:
        print("\n测试被中断")
    finally:
        save_results()

    # 打印总结
    print("\n" + "=" * 60)
    pass_count = sum(1 for r in test_results if r["status"] == "PASS")
    fail_count = sum(1 for r in test_results if r["status"] == "FAIL")
    print(f"测试完成: {pass_count}/{len(test_results)} 通过")
    if fail_count > 0:
        print(f"失败: {fail_count} 个")
    print("=" * 60)


if __name__ == "__main__":
    main()
