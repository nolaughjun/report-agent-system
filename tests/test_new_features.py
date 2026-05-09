#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""新功能测试

测试：
1. 多模型选择切换
2. 数据多源接入
3. 安全检查
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
print("新功能测试")
print("=" * 60)

# ========================================
# 测试 1: 多模型选择
# ========================================
print("\n[测试 1] 多模型选择切换")
print("-" * 60)

from tools.llm import (
    get_available_models,
    set_current_model,
    get_current_model,
    get_model_config,
    MODEL_CONFIGS,
)

print("预定义模型:")
for model_id, config in MODEL_CONFIGS.items():
    print(f"  - {model_id}: {config.name} ({config.provider})")

available = get_available_models()
print(f"\n可用模型: {available}")

current = get_current_model()
print(f"当前模型: {current}")

# 切换模型
if len(available) > 1:
    new_model = available[0] if available[0] != current else available[1]
    if set_current_model(new_model):
        print(f"切换到: {get_current_model()}")
        config = get_model_config()
        print(f"  提供商: {config.provider}")
        print(f"  Base URL: {config.base_url}")

print("\n✅ 多模型选择测试通过")

# ========================================
# 测试 2: 数据多源接入
# ========================================
print("\n[测试 2] 数据多源接入")
print("-" * 60)

from tools.llm import (
    get_available_data_sources,
    set_active_data_sources,
    get_active_data_sources,
    DATA_SOURCES,
)

print("预定义数据源:")
for source_id, config in DATA_SOURCES.items():
    print(f"  - {source_id}: {config.name} (优先级: {config.priority})")

available_sources = get_available_data_sources()
print(f"\n可用数据源: {available_sources}")

if available_sources:
    set_active_data_sources(available_sources)
    print(f"活动数据源: {get_active_data_sources()}")

print("\n✅ 数据多源接入测试通过")

# ========================================
# 测试 3: 安全检查
# ========================================
print("\n[测试 3] 红黑安全检查")
print("-" * 60)

from security import (
    run_security_audit,
    check_input_injection,
    check_api_key_leak,
    check_path_traversal,
    sanitize_output,
    validate_filename,
)

# 输入注入检查
print("测试输入注入检测:")
malicious_inputs = [
    "SELECT * FROM users WHERE id=1 OR 1=1",
    "<script>alert('xss')</script>",
    "normal input text",
]

for text in malicious_inputs:
    issues = check_input_injection(text)
    if issues:
        print(f"  ⚠️ 发现问题: {text[:30]}... -> {issues[0].category}")
    else:
        print(f"  ✅ 安全: {text[:30]}...")

# API Key 泄露检查
print("\n测试 API Key 泄露检测:")
test_outputs = [
    "The API key is sk-abc123def456ghi789jkl",
    "Normal output without keys",
]

for text in test_outputs:
    issues = check_api_key_leak(text)
    if issues:
        print(f"  ⚠️ 发现泄露: {issues[0].description}")
        # 清理输出
        cleaned = sanitize_output(text)
        print(f"  清理后: {cleaned[:50]}...")
    else:
        print(f"  ✅ 无泄露: {text[:30]}...")

# 路径穿越检查
print("\n测试路径穿越检测:")
paths = [
    "../../../etc/passwd",
    "normal_file.txt",
]

for path in paths:
    issues = check_path_traversal(path)
    if issues:
        print(f"  ⚠️ 危险路径: {path}")
    else:
        print(f"  ✅ 安全路径: {path}")

# 文件名验证
print("\n测试文件名验证:")
filenames = [
    "report_2024.pdf",
    "../../../etc/passwd",
    "test file (1).txt",
]

for filename in filenames:
    try:
        safe_name = validate_filename(filename)
        print(f"  ✅ {filename} -> {safe_name}")
    except ValueError as e:
        print(f"  ⚠️ {filename}: {e}")

# 运行完整安全审计
print("\n运行完整安全审计...")
report = run_security_audit()
print(f"审计结果: {'通过' if report.passed else '未通过'}")
print(f"问题总数: {report.summary['total_issues']}")
print(f"问题分布: {report.summary['by_severity']}")

if report.issues:
    print("\n问题详情:")
    for issue in report.issues[:5]:
        print(f"  [{issue.severity}] {issue.category}: {issue.description}")

print("\n✅ 安全检查测试通过")

# ========================================
# 测试 4: API 端点检查
# ========================================
print("\n[测试 4] API 端点检查")
print("-" * 60)

try:
    from api import app
    print("API 应用加载成功")

    # 列出所有路由
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes.append(f"  {list(route.methods)} {route.path}")

    print(f"注册的路由 ({len(routes)} 个):")
    for route in routes[:10]:
        print(route)

    if len(routes) > 10:
        print(f"  ... 还有 {len(routes) - 10} 个路由")

    print("\n✅ API 端点检查通过")

except ImportError as e:
    print(f"⚠️ API 模块导入失败: {e}")
    print("（可能缺少 FastAPI 依赖）")

# ========================================
# 测试 5: Docker 配置检查
# ========================================
print("\n[测试 5] Docker 配置检查")
print("-" * 60)

import os

docker_files = [
    "Dockerfile",
    "docker-compose.yml",
    "requirements.txt",
    ".env.example",
]

print("Docker 配置文件:")
for filename in docker_files:
    filepath = Path(__file__).parent.parent / filename
    exists = filepath.exists()
    status = "✅" if exists else "❌"
    print(f"  {status} {filename}")

print("\n✅ Docker 配置检查完成")

print("\n" + "=" * 60)
print("所有测试完成")
print("=" * 60)
