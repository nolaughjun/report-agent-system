# security/audit.py — 红黑安全检查
"""红黑安全检查模块

红队检查（攻击视角）：
- 输入注入攻击检测
- API Key 泄露检测
- 路径穿越检测
- 命令注入检测

黑队检查（防御视角）：
- 敏感数据过滤
- 访问控制验证
- 日志审计
- 配置安全检查
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 安全检查结果
# ══════════════════════════════════════════════════════════════

@dataclass
class SecurityIssue:
    """安全问题"""
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    category: str  # 问题类别
    description: str  # 问题描述
    location: str  # 问题位置
    recommendation: str  # 修复建议
    details: dict = field(default_factory=dict)


@dataclass
class SecurityReport:
    """安全报告"""
    timestamp: str
    issues: list[SecurityIssue]
    passed: bool
    summary: dict

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "passed": self.passed,
            "summary": self.summary,
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "description": i.description,
                    "location": i.location,
                    "recommendation": i.recommendation,
                }
                for i in self.issues
            ],
        }


# ══════════════════════════════════════════════════════════════
# 红队检查（攻击视角）
# ══════════════════════════════════════════════════════════════

def check_input_injection(text: str, location: str = "input") -> list[SecurityIssue]:
    """检查输入注入攻击

    检测：
    - SQL 注入
    - XSS 攻击
    - 命令注入
    - Prompt 注入
    """
    issues = []

    # SQL 注入检测
    sql_patterns = [
        r"['\"]\s*(OR|AND)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+",
        r"UNION\s+(ALL\s+)?SELECT",
        r";\s*(DROP|DELETE|UPDATE|INSERT)",
        r"--\s*$",
        r"/\*.*\*/",
    ]
    for pattern in sql_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(SecurityIssue(
                severity="HIGH",
                category="SQL_INJECTION",
                description=f"检测到可能的 SQL 注入模式: {pattern}",
                location=location,
                recommendation="使用参数化查询，避免直接拼接 SQL",
                details={"pattern": pattern, "sample": text[:100]},
            ))
            break

    # XSS 检测
    xss_patterns = [
        r"<script[^>]*>.*?</script>",
        r"javascript\s*:",
        r"on(error|load|click|mouseover)\s*=",
        r"<img[^>]+onerror\s*=",
    ]
    for pattern in xss_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(SecurityIssue(
                severity="HIGH",
                category="XSS",
                description=f"检测到可能的 XSS 攻击模式",
                location=location,
                recommendation="对用户输入进行 HTML 编码",
                details={"pattern": pattern},
            ))
            break

    # 命令注入检测
    cmd_patterns = [
        r"[;&|`]\s*(rm|del|format|shutdown|reboot)",
        r"\$\([^)]+\)",  # $(command)
        r"`[^`]+`",  # `command`
        r"\|\s*(bash|sh|cmd|powershell)",
    ]
    for pattern in cmd_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(SecurityIssue(
                severity="CRITICAL",
                category="COMMAND_INJECTION",
                description="检测到可能的命令注入攻击",
                location=location,
                recommendation="禁止执行用户输入的命令，使用白名单验证",
                details={"pattern": pattern},
            ))
            break

    # Prompt 注入检测
    prompt_injection_patterns = [
        r"ignore\s+(previous|all)\s+(instructions|prompts)",
        r"you\s+are\s+now\s+a",
        r"disregard\s+(your|the)\s+(training|instructions)",
        r"repeat\s+(the\s+)?(above|following|words)",
    ]
    for pattern in prompt_injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(SecurityIssue(
                severity="MEDIUM",
                category="PROMPT_INJECTION",
                description="检测到可能的 Prompt 注入尝试",
                location=location,
                recommendation="使用系统提示加固，限制模型行为",
                details={"pattern": pattern},
            ))
            break

    return issues


def check_api_key_leak(content: str, location: str = "output") -> list[SecurityIssue]:
    """检查 API Key 泄露"""
    issues = []

    # API Key 模式
    key_patterns = [
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI/DeepSeek API Key"),
        (r"tvly-[a-zA-Z0-9]{20,}", "Tavily API Key"),
        (r"xox[baprs]-[a-zA-Z0-9-]+", "Slack Token"),
        (r"github_pat_[a-zA-Z0-9_]+", "GitHub PAT"),
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
        (r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*", "JWT Token"),
    ]

    for pattern, key_type in key_patterns:
        matches = re.findall(pattern, content)
        if matches:
            issues.append(SecurityIssue(
                severity="CRITICAL",
                category="API_KEY_LEAK",
                description=f"检测到 {key_type} 泄露",
                location=location,
                recommendation="立即轮换泄露的 API Key，添加到日志过滤列表",
                details={"key_type": key_type, "count": len(matches)},
            ))

    return issues


def check_path_traversal(path: str, location: str = "file_path") -> list[SecurityIssue]:
    """检查路径穿越攻击"""
    issues = []

    traversal_patterns = [
        r"\.\./",
        r"\.\.\\",
        r"%2e%2e[/\\]",
        r"\.\.%2f",
        r"%252e%252e",
    ]

    for pattern in traversal_patterns:
        if re.search(pattern, path, re.IGNORECASE):
            issues.append(SecurityIssue(
                severity="HIGH",
                category="PATH_TRAVERSAL",
                description="检测到路径穿越攻击尝试",
                location=location,
                recommendation="使用安全的文件名处理函数，限制访问目录",
                details={"pattern": pattern, "path": path},
            ))
            break

    return issues


# ══════════════════════════════════════════════════════════════
# 黑队检查（防御视角）
# ══════════════════════════════════════════════════════════════

def check_environment_security() -> list[SecurityIssue]:
    """检查环境配置安全"""
    issues = []

    # 检查敏感环境变量是否设置
    sensitive_keys = [
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "TAVILY_API_KEY",
        "DATABASE_URL",
    ]

    for key in sensitive_keys:
        value = os.environ.get(key, "")
        if not value:
            issues.append(SecurityIssue(
                severity="INFO",
                category="CONFIG",
                description=f"环境变量 {key} 未设置",
                location="environment",
                recommendation="根据需要配置必要的环境变量",
            ))
        elif len(value) < 10:
            issues.append(SecurityIssue(
                severity="MEDIUM",
                category="CONFIG",
                description=f"环境变量 {key} 值可能无效",
                location="environment",
                recommendation="检查 API Key 格式是否正确",
            ))

    # 检查调试模式
    debug_mode = os.environ.get("DEBUG", "").lower()
    if debug_mode in ["true", "1", "yes"]:
        issues.append(SecurityIssue(
            severity="MEDIUM",
            category="CONFIG",
            description="调试模式已启用",
            location="environment",
            recommendation="生产环境应关闭调试模式",
        ))

    return issues


def check_file_permissions() -> list[SecurityIssue]:
    """检查文件权限"""
    issues = []

    # 检查敏感文件
    sensitive_files = [
        ".env",
        "config.json",
        "secrets.json",
        "credentials.json",
    ]

    for filename in sensitive_files:
        if os.path.exists(filename):
            # 检查文件权限（Unix）
            try:
                mode = os.stat(filename).st_mode
                # 检查是否其他用户可读
                if mode & 0o004:
                    issues.append(SecurityIssue(
                        severity="HIGH",
                        category="FILE_PERMISSION",
                        description=f"敏感文件 {filename} 对其他用户可读",
                        location=filename,
                        recommendation="修改文件权限为 600 (仅所有者可读写)",
                    ))
            except Exception:
                pass

    return issues


def check_dependencies_security() -> list[SecurityIssue]:
    """检查依赖安全（基础检查）"""
    issues = []

    # 检查是否有已知不安全的模式
    unsafe_imports = [
        ("pickle", "pickle 加载不可信数据可能导致远程代码执行"),
        ("marshal", "marshal 加载不可信数据可能导致远程代码执行"),
        ("yaml", "yaml.load 不带 Loader 可能导致代码执行"),
        ("subprocess", "subprocess 使用 shell=True 可能导致命令注入"),
    ]

    # 这里只是示例，实际应该扫描源代码
    issues.append(SecurityIssue(
        severity="INFO",
        category="DEPENDENCY",
        description="建议定期运行 pip-audit 或 safety 检查依赖漏洞",
        location="requirements.txt",
        recommendation="使用 pip-audit 检查已知漏洞",
    ))

    return issues


# ══════════════════════════════════════════════════════════════
# 综合安全检查
# ══════════════════════════════════════════════════════════════

def run_security_audit(
    check_input: str = None,
    check_output: str = None,
    check_path: str = None,
) -> SecurityReport:
    """运行完整的安全审计

    Args:
        check_input: 要检查的输入文本
        check_output: 要检查的输出文本
        check_path: 要检查的文件路径

    Returns:
        安全报告
    """
    all_issues: list[SecurityIssue] = []

    # 红队检查
    if check_input:
        all_issues.extend(check_input_injection(check_input, "user_input"))

    if check_output:
        all_issues.extend(check_api_key_leak(check_output, "output"))

    if check_path:
        all_issues.extend(check_path_traversal(check_path, "file_path"))

    # 黑队检查
    all_issues.extend(check_environment_security())
    all_issues.extend(check_file_permissions())
    all_issues.extend(check_dependencies_security())

    # 统计
    severity_counts = {
        "CRITICAL": 0,
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
        "INFO": 0,
    }
    for issue in all_issues:
        severity_counts[issue.severity] += 1

    # 判断是否通过
    passed = severity_counts["CRITICAL"] == 0 and severity_counts["HIGH"] == 0

    return SecurityReport(
        timestamp=datetime.now(UTC).isoformat(),
        issues=all_issues,
        passed=passed,
        summary={
            "total_issues": len(all_issues),
            "by_severity": severity_counts,
        },
    )


def sanitize_output(text: str) -> str:
    """清理输出中的敏感信息

    Args:
        text: 原始文本

    Returns:
        清理后的文本
    """
    # 移除 API Keys
    text = re.sub(r"sk-[a-zA-Z0-9]{20,}", "sk-***REDACTED***", text)
    text = re.sub(r"tvly-[a-zA-Z0-9]{20,}", "tvly-***REDACTED***", text)
    text = re.sub(r"github_pat_[a-zA-Z0-9_]+", "github_pat_***REDACTED***", text)
    text = re.sub(r"AKIA[0-9A-Z]{16}", "AKIA***REDACTED***", text)
    text = re.sub(r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*", "***JWT_REDACTED***", text)

    return text


def validate_filename(filename: str) -> str:
    """验证并清理文件名

    Args:
        filename: 原始文件名

    Returns:
        安全的文件名

    Raises:
        ValueError: 如果文件名包含路径穿越
    """
    # 检查路径穿越
    issues = check_path_traversal(filename)
    if issues:
        raise ValueError(f"文件名包含非法字符: {filename}")

    # 只保留安全字符
    safe_name = re.sub(r'[^\w\-_\.]', '_', filename)

    # 移除连续下划线
    safe_name = re.sub(r'_+', '_', safe_name)

    # 移除首尾下划线和点
    safe_name = safe_name.strip('_.')

    return safe_name[:255] if safe_name else "unnamed"


# ══════════════════════════════════════════════════════════════
# 安全中间件
# ══════════════════════════════════════════════════════════════

def secure_input(func: Callable) -> Callable:
    """输入安全检查装饰器"""
    def wrapper(*args, **kwargs):
        # 检查字符串参数
        for arg in args:
            if isinstance(arg, str):
                issues = check_input_injection(arg)
                if issues:
                    for issue in issues:
                        if issue.severity in ["CRITICAL", "HIGH"]:
                            logger.warning(
                                "[security] 输入检查发现问题: %s - %s",
                                issue.category,
                                issue.description
                            )

        return func(*args, **kwargs)

    return wrapper


def secure_output(func: Callable) -> Callable:
    """输出安全检查装饰器"""
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)

        # 清理输出
        if isinstance(result, str):
            return sanitize_output(result)
        elif isinstance(result, dict):
            return {k: sanitize_output(v) if isinstance(v, str) else v for k, v in result.items()}

        return result

    return wrapper


# ══════════════════════════════════════════════════════════════
# 审计日志
# ══════════════════════════════════════════════════════════════

class AuditLogger:
    """审计日志记录器"""

    def __init__(self, log_file: str = "audit.log"):
        self.log_file = log_file
        self.logger = logging.getLogger("audit")

        # 配置审计日志处理器
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        ))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log_access(self, user: str, action: str, resource: str, result: str):
        """记录访问日志"""
        self.logger.info(
            "ACCESS user=%s action=%s resource=%s result=%s",
            user, action, resource, result
        )

    def log_security_event(self, event_type: str, details: dict):
        """记录安全事件"""
        self.logger.warning(
            "SECURITY event=%s details=%s",
            event_type,
            details
        )

    def log_data_access(self, source: str, query: str, record_count: int):
        """记录数据访问"""
        self.logger.info(
            "DATA_ACCESS source=%s query=%s records=%d",
            source,
            query[:50] if len(query) > 50 else query,
            record_count
        )
