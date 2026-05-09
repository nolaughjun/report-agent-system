# 报告智能体系统 - 产品说明文档

## 产品概述

报告智能体系统是一个基于 LangGraph 框架构建的智能报告生成平台，能够自动收集信息、撰写报告并进行质量审核。系统支持 100 人并发使用，具备完整的任务队列、缓存层、限流和用户配额管理功能。

### 核心特性

- **智能报告生成**: 自动规划、收集、撰写、审核
- **多模型支持**: DeepSeek、OpenAI、Anthropic
- **多数据源**: Tavily、Serper 搜索引擎
- **并发处理**: 支持 100 人同时使用
- **任务队列**: Celery 异步任务处理
- **缓存优化**: 搜索结果和 LLM 响应缓存
- **API 限流**: 多层次限流保护
- **用户配额**: 每日/每月使用限制
- **水平扩展**: Docker Compose / Kubernetes 部署

---

## 系统架构

### 架构图

```
                        ┌─────────────────────────────────────┐
                        │       Ingress / Load Balancer       │
                        └──────────────────┬──────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              ↓                            ↓                            ↓
        ┌──────────┐                 ┌──────────┐                 ┌──────────┐
        │  API #1  │                 │  API #2  │                 │  API #N  │
        └────┬─────┘                 └────┬─────┘                 └────┬─────┘
             │                            │                            │
             └────────────────────────────┼────────────────────────────┘
                                         ↓
              ┌──────────────────────────────────────────────────────────────┐
              │                         Redis                                │
              │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
              │  │ 任务队列     │ │ 状态存储     │ │ 缓存层       │        │
              │  │ (Celery)     │ │ (LangGraph)  │ │ (搜索/LLM)   │        │
              │  └──────────────┘ └──────────────┘ └──────────────┘        │
              │  ┌──────────────┐ ┌──────────────┐                         │
              │  │ 限流计数     │ │ 配额追踪     │                         │
              │  └──────────────┘ └──────────────┘                         │
              └──────────────────────────┬───────────────────────────────────┘
                                         │
              ┌──────────────────────────┴───────────────────────────────────┐
              ↓                                                              ↓
    ┌──────────────────┐                                 ┌────────────────────┐
    │  PostgreSQL      │                                 │  Celery Workers    │
    │  ┌────────────┐  │                                 │  ┌──────────────┐  │
    │  │ 任务持久化 │  │                                 │  │ Worker #1    │  │
    │  ├────────────┤  │                                 │  ├──────────────┤  │
    │  │ 用户配额   │  │                                 │  │ Worker #2    │  │
    │  ├────────────┤  │                                 │  ├──────────────┤  │
    │  │ 报告历史   │  │                                 │  │ ...          │  │
    │  └────────────┘  │                                 │  ├──────────────┤  │
    └──────────────────┘                                 │  │ Worker #N    │  │
                                                         │  └──────────────┘  │
                                                         └────────────────────┘
```

### 技术栈

| 层级 | 技术 | 说明 |
|-----|------|------|
| API 层 | FastAPI | 高性能异步 Web 框架 |
| 状态机 | LangGraph | 状态图工作流引擎 |
| 任务队列 | Celery | 分布式任务队列 |
| 缓存 | Redis | 内存数据库 |
| 数据库 | PostgreSQL | 关系型数据库 |
| 容器化 | Docker | 容器部署 |
| 编排 | Kubernetes | 容器编排（生产环境） |

---

## 功能模块

### 1. 报告生成流程

```
START → 检查定时 → 规划任务 → 并发收集数据 → 生成草案 → 质量审核 → 人工审核 → 最终输出 → END
                                    ↑              ↓
                                    └──── 修改 ←───┘
```

#### 1.1 规划阶段

系统根据报告主题自动生成：
- 报告大纲
- 搜索查询列表
- 数据收集计划

#### 1.2 数据收集

- **并发收集**: 同时执行多个搜索任务
- **多数据源**: 支持多个搜索引擎
- **结果缓存**: 相同查询结果缓存 1 小时

#### 1.3 草案生成

- 基于收集的数据生成完整报告
- 支持多种报告类型（研究、分析、摘要、提案）
- 多语言支持

#### 1.4 质量审核

自动检查报告质量：
- 内容完整性
- 逻辑连贯性
- 格式规范性

#### 1.5 人工审核

支持人工干预：
- 审核草案
- 批准或要求修改
- 添加修改意见

---

### 2. 任务队列

#### 2.1 异步处理

报告生成任务通过 Celery 异步执行：

```python
# 提交任务
task = generate_report_task.delay(
    topic="AI 发展趋势",
    report_type="research",
    language="中文"
)

# 查询状态
status = get_task_status(task.id)
```

#### 2.2 任务监控

- **Flower 监控面板**: http://localhost:5555
- 实时查看任务状态
- Worker 健康监控

---

### 3. 缓存层

#### 3.1 搜索结果缓存

```python
from cache import search_with_cache

results = search_with_cache(
    query="AI发展趋势",
    search_func=tavily_search,
    source="tavily",
    ttl=3600  # 1 小时
)
```

#### 3.2 LLM 响应缓存

```python
from cache import llm_with_cache

response = llm_with_cache(
    messages=[{"role": "user", "content": "Hello"}],
    llm_func=chat,
    model="deepseek-chat",
    use_cache=True
)
```

**注意**: LLM 缓存仅对 `temperature < 0.2` 的确定性请求有效

---

### 4. API 限流

#### 4.1 限流配置

```bash
# .env 配置
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=60  # 每分钟请求数
```

#### 4.2 限流算法

采用**滑动窗口**算法：
- 精确控制时间窗口内的请求数
- 基于 Redis 有序集合实现
- 分布式环境下一致性好

#### 4.3 响应头

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1700000000
```

#### 4.4 超限响应

```json
{
  "error": "Too Many Requests",
  "message": "请求过于频繁，请 30 秒后重试",
  "retry_after": 30
}
```

---

### 5. 用户配额

#### 5.1 配额类型

| 类型 | 默认值 | 说明 |
|-----|--------|------|
| 每日配额 | 50 次 | 每天 00:00 重置 |
| 每月配额 | 1000 次 | 每月 1 日重置 |

#### 5.2 使用方式

```bash
# 请求头携带用户 ID
curl -H "X-User-ID: user123" http://localhost:8000/api/reports
```

#### 5.3 配额查询

```sql
-- 查看用户配额
SELECT * FROM user_quotas WHERE user_id = 'user123';

-- 重置每日配额
UPDATE user_quotas SET daily_used = 0 WHERE user_id = 'user123';
```

---

## API 接口

### 基础 URL

```
http://localhost:8000
```

### 认证

所有 API 支持 API Key 认证：

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:8000/api/reports
```

### 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /api/reports | 创建报告任务 |
| GET | /api/reports/{id} | 查询任务状态 |
| POST | /api/reports/{id}/resume | 恢复任务执行 |
| GET | /api/models | 列出可用模型 |
| POST | /api/models/{id}/select | 选择模型 |
| GET | /api/data-sources | 列出数据源 |
| GET | /api/reports/{id}/download | 下载报告 |
| GET | /api/security/audit | 安全审计 |

### 示例

#### 创建报告

```bash
curl -X POST http://localhost:8000/api/reports \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "人工智能发展趋势",
    "abstract": "分析 AI 最新进展和未来方向",
    "report_type": "research",
    "language": "中文",
    "quality_threshold": 0.7
  }'
```

响应：
```json
{
  "thread_id": "abc12345",
  "status": "pending",
  "message": "任务已提交，正在处理中"
}
```

#### 查询状态

```bash
curl http://localhost:8000/api/reports/abc12345
```

响应：
```json
{
  "thread_id": "abc12345",
  "current_step": "drafting",
  "status": "processing",
  "progress": 0.5,
  "quality_score": null
}
```

#### 恢复执行

```bash
curl -X POST "http://localhost:8000/api/reports/abc12345/resume?decision=approve"
```

---

## 部署指南

### 环境要求

| 组件 | 版本 | 说明 |
|-----|------|------|
| Python | 3.10+ | 运行环境 |
| Redis | 7.0+ | 状态存储/队列 |
| PostgreSQL | 15+ | 数据库 |
| Docker | 24+ | 容器运行时 |

### Docker Compose 部署

#### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入 API Key
```

#### 2. 启动服务

```bash
docker-compose up -d
```

#### 3. 查看服务状态

```bash
docker-compose ps
```

#### 4. 水平扩展

```bash
docker-compose up -d --scale api=5 --scale worker=10
```

### Kubernetes 部署

#### 1. 创建命名空间

```bash
kubectl apply -f k8s/namespace.yaml
```

#### 2. 创建配置

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
```

#### 3. 部署数据库

```bash
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
```

#### 4. 部署应用

```bash
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
```

#### 5. 配置入口

```bash
kubectl apply -f k8s/ingress.yaml
```

---

## 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| DEBUG | false | 调试模式 |
| LOG_LEVEL | INFO | 日志级别 |
| PORT | 8000 | API 端口 |
| REDIS_URL | redis://localhost:6379/0 | Redis 连接 |
| DATABASE_URL | postgresql://... | 数据库连接 |
| DEEPSEEK_API_KEY | - | DeepSeek API Key |
| TAVILY_API_KEY | - | Tavily API Key |
| RATE_LIMIT_ENABLED | true | 启用限流 |
| RATE_LIMIT_REQUESTS | 60 | 限流阈值 |
| SEARCH_CACHE_TTL | 3600 | 搜索缓存 TTL |
| LLM_CACHE_TTL | 7200 | LLM 缓存 TTL |

---

## 监控与运维

### 健康检查

```bash
curl http://localhost:8000/health
```

### 日志查看

```bash
# Docker Compose
docker-compose logs -f api
docker-compose logs -f worker

# Kubernetes
kubectl logs -f deployment/api -n report-agent
```

### 性能指标

| 指标 | 正常值 | 告警阈值 |
|-----|--------|---------|
| API 响应时间 | < 200ms | > 1s |
| Worker 队列长度 | < 100 | > 500 |
| Redis 内存使用 | < 1GB | > 2GB |
| PostgreSQL 连接数 | < 50 | > 100 |

### 故障排查

#### API 返回 429

```bash
# 检查限流状态
redis-cli get "ratelimit:ip:{your_ip}"

# 清除限流记录
redis-cli del "ratelimit:ip:{your_ip}"
```

#### Worker 无响应

```bash
# 检查 Worker 状态
celery -A tasks inspect active

# 重启 Worker
docker-compose restart worker
```

---

## 安全注意事项

### 生产环境清单

#### 安全

- [ ] 修改所有默认密码
- [ ] 配置 SSL/TLS 证书
- [ ] 启用 API 认证
- [ ] 配置防火墙规则
- [ ] 设置网络策略

#### 性能

- [ ] 调整副本数量
- [ ] 配置资源限制
- [ ] 启用缓存
- [ ] 配置 CDN

#### 可靠性

- [ ] 配置健康检查
- [ ] 设置自动重启策略
- [ ] 配置备份策略
- [ ] 设置监控告警

---

## 版本历史

### v2.0.0 (2026-05-09)

- 新增 Redis 状态持久化
- 新增 Celery 任务队列
- 新增 PostgreSQL 数据库持久化
- 新增搜索/LLM 缓存层
- 新增 API 限流和用户配额
- 新增多实例水平扩展支持
- 新增 Kubernetes 部署配置

### v1.0.0

- 基础报告生成功能
- LangGraph 状态机
- 多模型支持
- 人工审核流程

---

## 技术支持

- **文档**: [SCALING.md](SCALING.md)
- **问题反馈**: GitHub Issues
- **邮件支持**: nolaughjun@gmail.com
