# 贡献指南

感谢您有兴趣为报告智能体系统做出贡献！

## 如何贡献

### 报告 Bug

如果您发现了 bug，请创建一个 Issue，包含以下信息：

- 清晰的标题和描述
- 复现步骤
- 预期行为
- 实际行为
- 环境信息（Python 版本、操作系统等）
- 相关日志或截图

### 提出新功能

欢迎提出新功能建议！请创建一个 Issue，描述：

- 功能描述
- 使用场景
- 可能的实现方案

### 提交代码

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 代码规范

- 使用 Python 3.10+ 语法
- 遵循 PEP 8 编码规范
- 添加类型注解
- 编写单元测试
- 更新相关文档

### 提交信息规范

使用约定式提交：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式（不影响功能）
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 构建/工具相关

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/your-username/report-agent-system.git
cd report-agent-system

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 复制环境变量配置
cp .env.example .env
# 编辑 .env 填入您的 API Key

# 运行测试
pytest tests/
```

## 安全问题

如果您发现安全漏洞，请不要在公开 Issue 中报告。

请发送邮件至：nolaughjun@gmail.com

## 许可证

提交代码即表示您同意您的贡献将根据 MIT 许可证进行许可。
