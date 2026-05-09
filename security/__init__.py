# security/__init__.py — 安全模块
"""安全模块

红黑安全检查：
- 输入验证
- 输出过滤
- 环境检查
- 审计日志
"""
from security.security_audit import (
    # 安全检查
    run_security_audit,
    check_input_injection,
    check_api_key_leak,
    check_path_traversal,
    check_environment_security,
    check_file_permissions,
    check_dependencies_security,
    # 安全工具
    sanitize_output,
    validate_filename,
    # 装饰器
    secure_input,
    secure_output,
    # 数据结构
    SecurityIssue,
    SecurityReport,
    # 审计日志
    AuditLogger,
)

__all__ = [
    "run_security_audit",
    "check_input_injection",
    "check_api_key_leak",
    "check_path_traversal",
    "check_environment_security",
    "check_file_permissions",
    "check_dependencies_security",
    "sanitize_output",
    "validate_filename",
    "secure_input",
    "secure_output",
    "SecurityIssue",
    "SecurityReport",
    "AuditLogger",
]
