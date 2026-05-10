# 更新日志

本项目的所有重要更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中
- 向量数据库集成（Pinecone/Milvus）
- 报告模板系统
- 多语言前端界面

## [2.1.0] - 2026-05-10

### 新增
- **Wiki 知识库系统**: 报告自动入库，知识复用加速生成
  - 自动章节分割和知识点提取
  - 关键词索引和语义搜索
  - 新报告生成时自动获取相关知识
  - 分类管理：技术、市场、数据、风险、建议
- **LangSmith 监控集成**: LLM 调用追踪和性能分析
  - 自动追踪所有 LLM 调用
  - Token 使用量统计
  - 延迟监控
  - 反馈评分记录
- **React 前端界面**: 现代化的 Web UI
  - 专业商务风格设计
  - 工作台仪表板
  - 报告创建和管理
  - 系统设置页面
- **Wiki API 端点**:
  - `POST /api/wiki/search` - 搜索知识库
  - `GET /api/wiki/stats` - 获取统计
  - `GET /api/wiki/recommend` - 推荐知识
  - `POST /api/wiki/ingest/{id}` - 手动入库
- **监控 API 端点**:
  - `GET /api/monitoring/status` - 监控状态
  - `GET /api/monitoring/traces/{id}` - 追踪详情
  - `POST /api/monitoring/feedback` - 记录反馈

### 改进
- 规划节点集成 Wiki 知识上下文
- 报告完成时自动入库到 Wiki
- 完善的测试覆盖（24 个 Wiki 测试用例）

## [2.0.0] - 2026-05-09

### 新增
- **并发数据收集**: 使用 asyncio 实现并发搜索，显著提升效率
- **时间施行功能**: 支持定时和周期性执行报告生成
- **多模型选择**: 支持 DeepSeek、OpenAI、Claude、本地模型切换
- **多源数据接入**: 支持 Tavily、Serper、Brave、自定义搜索源
- **版本回滚**: 基于快照的时间旅行功能
- **Token 统计**: 完整的 Token 使用量追踪
- **安全审计**: 红黑对抗安全检查模块
- **Docker 部署**: 生产级容器化配置
- **REST API**: FastAPI 接口服务

### 修复
- 人工审核流程中断点恢复问题
- PDF 导出 xelatex 路径问题
- max_retry 无限循环问题
- PDF 内容截断和段落缩进问题

### 改进
- 性能指标追踪系统
- 详细的日志记录
- 完善的错误处理

## [1.0.0] - 2026-05-08

### 新增
- 基础报告生成流程
- LangGraph 状态机框架
- DeepSeek LLM 集成
- Tavily 搜索集成
- PDF/Markdown 导出
- 质量自动检测
- 人工审核干预

---

## 版本命名规则

- **主版本号**: 重大架构变更或不兼容更新
- **次版本号**: 新功能添加
- **修订号**: Bug 修复和小改进

## 版本对比

| 特性 | v1.0 | v2.0 |
|-----|------|------|
| 数据收集 | 顺序执行 | 并发执行 |
| 执行模式 | 立即执行 | 支持定时执行 |
| 模型支持 | DeepSeek | 多模型 |
| 数据源 | Tavily | 多源 |
| 安全审计 | 无 | 红黑对抗 |
| 部署方式 | 本地 | Docker |
| API | 无 | REST API |
