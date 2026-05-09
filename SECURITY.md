# 安全政策

## 支持的版本

| 版本 | 支持状态 |
|-----|---------|
| v2.0 | ✅ 当前支持 |
| v1.0 | ⚠️ 仅维护 |

## 报告安全漏洞

如果您发现安全漏洞，请**不要**在公开的 GitHub Issue 中报告。

请通过以下方式私下报告：

1. 发送邮件至：nolaughjun@gmail.com
2. 包含以下信息：
   - 漏洞描述
   - 复现步骤
   - 影响范围
   - 可能的修复方案（如有）

我们承诺：

- 在 48 小时内确认收到报告
- 在 7 天内提供初步评估
- 在修复后公开致谢

## 安全最佳实践

### API Key 管理

- **永远不要**将 API Key 硬编码在代码中
- 使用 `.env` 文件存储敏感信息
- 确保 `.env` 已添加到 `.gitignore`

```python
# ❌ 错误示例
api_key = "sk-xxxx"

# ✅ 正确示例
import os
api_key = os.getenv("DEEPSEEK_API_KEY")
```

### 输入验证

系统会自动检测以下攻击：

- SQL 注入
- XSS 攻击
- 命令注入
- 路径穿越

```python
from security import check_input_injection

issues = check_input_injection(user_input)
if issues:
    raise ValueError(f"检测到安全问题: {issues[0].category}")
```

### 输出清理

防止敏感信息泄露：

```python
from security import sanitize_output

safe_output = sanitize_output(output_text)
```

## 安全审计

系统内置红黑安全审计功能：

```python
from security import run_security_audit

report = run_security_audit()
print(f"审计通过: {report.passed}")
print(f"问题总数: {report.summary['total_issues']}")
```

建议在生产环境部署前运行完整安全审计。

## 依赖安全

定期更新依赖并检查漏洞：

```bash
# 使用 pip-audit
pip-audit

# 使用 safety
safety check
```
