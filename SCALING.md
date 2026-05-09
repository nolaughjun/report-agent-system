# 并发扩展说明

## 概述

系统已完整支持 100 人并发使用，包含：

| 阶段 | 特性 | 状态 |
|-----|------|------|
| Phase 1 | Redis 状态持久化 + Celery 任务队列 | ✅ 完成 |
| Phase 2 | PostgreSQL 数据库持久化 | ✅ 完成 |
| Phase 3 | 缓存层（搜索/LLM） | ✅ 完成 |
| Phase 4 | API 限流 + 用户配额 | ✅ 完成 |
| Phase 5 | 多实例水平扩展 | ✅ 完成 |

## 架构

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

## 服务说明

| 服务 | 端口 | 说明 |
|-----|------|------|
| Nginx | 80/443 | 负载均衡 + SSL 终止 |
| API | 8000 | FastAPI 服务（多实例） |
| PostgreSQL | 5432 | 数据库持久化 |
| Redis | 6379 | 状态存储 + 任务队列 + 缓存 |
| Flower | 5555 | Celery 监控面板 |

## 快速启动

### Docker Compose（本地/测试环境）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 2. 启动所有服务
docker-compose up -d

# 3. 查看服务状态
docker-compose ps

# 4. 水平扩展
docker-compose up -d --scale api=5 --scale worker=10
```

### Kubernetes（生产环境）

```bash
# 1. 创建命名空间
kubectl apply -f k8s/namespace.yaml

# 2. 创建配置
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml

# 3. 部署数据库
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml

# 4. 部署应用
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml

# 5. 配置入口
kubectl apply -f k8s/ingress.yaml

# 6. 查看状态
kubectl get all -n report-agent
```

## API 限流

### 配置

```bash
# .env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=60  # 每分钟请求数
```

### 响应头

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1700000000
```

### 超限响应

```json
{
  "error": "Too Many Requests",
  "message": "请求过于频繁，请 30 秒后重试",
  "retry_after": 30
}
```

## 用户配额

### 配额类型

| 类型 | 默认值 | 说明 |
|-----|--------|------|
| 每日配额 | 50 次 | 每天 00:00 重置 |
| 每月配额 | 1000 次 | 每月 1 日重置 |

### 检查配额

```bash
# 请求头携带用户 ID
curl -H "X-User-ID: user123" http://localhost:8000/api/reports
```

### 配额超限

```json
{
  "error": "Quota Exceeded",
  "message": "每日配额已用尽",
  "daily_used": 50,
  "daily_limit": 50
}
```

## 缓存策略

### 搜索结果缓存

```python
from cache import search_with_cache

# 自动缓存搜索结果
results = search_with_cache(
    query="AI发展趋势",
    search_func=tavily_search,
    source="tavily",
    ttl=3600  # 1 小时
)
```

### LLM 响应缓存

```python
from tools.llm import chat

# 低温度时自动缓存
response = chat(
    messages=[...],
    use_cache=True,
    temperature=0.1  # < 0.2 时才缓存
)
```

### 缓存统计

```python
from cache import get_cache_stats

stats = get_cache_stats()
# {
#   "hits": 150,
#   "misses": 50,
#   "hit_rate": 0.75
# }
```

## 水平扩展

### Docker Compose

```bash
# 扩展 API 到 5 个实例
docker-compose up -d --scale api=5

# 扩展 Worker 到 10 个实例
docker-compose up -d --scale worker=10

# 查看运行实例
docker-compose ps
```

### Kubernetes HPA

```yaml
# 自动扩展配置
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

```bash
# 手动扩展
kubectl scale deployment api --replicas=5 -n report-agent
kubectl scale deployment worker --replicas=10 -n report-agent

# 查看自动扩展状态
kubectl get hpa -n report-agent
```

## 性能指标

### 单个报告生成

| 阶段 | 无缓存 | 有缓存 |
|-----|--------|--------|
| 规划 | ~5秒 | ~5秒 |
| 数据收集 | ~15秒 | ~2秒 |
| 草案撰写 | ~30秒 | ~5秒 |
| 质量审核 | ~5秒 | ~5秒 |
| **总计** | ~55秒 | ~17秒 |

### 并发能力

| 配置 | 并发任务 | 100请求等待 |
|-----|---------|------------|
| 3 API + 5 Worker | 20 | ~5分钟 |
| 5 API + 10 Worker | 40 | ~2.5分钟 |
| 10 API + 20 Worker | 80 | ~1.5分钟 |

### 资源使用

| 服务 | CPU | 内存 |
|-----|-----|------|
| API (单实例) | 0.5-2核 | 1-4GB |
| Worker (单实例) | 1-4核 | 2-8GB |
| PostgreSQL | 0.5-2核 | 0.5-2GB |
| Redis | 0.5-1核 | 1-2GB |

## 监控

### Flower 监控

访问 http://localhost:5555 查看：
- 任务执行状态
- Worker 状态
- 任务历史

### Prometheus 指标

```bash
# API 指标
curl http://localhost:8000/metrics

# Nginx 状态
curl http://localhost:8080/nginx_status
```

### 日志查看

```bash
# Docker Compose
docker-compose logs -f api
docker-compose logs -f worker

# Kubernetes
kubectl logs -f deployment/api -n report-agent
kubectl logs -f deployment/worker -n report-agent
```

## 故障排查

### API 返回 429

```bash
# 检查限流状态
redis-cli get "ratelimit:ip:{your_ip}"

# 清除限流记录
redis-cli del "ratelimit:ip:{your_ip}"
```

### 用户配额问题

```sql
-- 查看用户配额
SELECT * FROM user_quotas WHERE user_id = 'user123';

-- 重置每日配额
UPDATE user_quotas SET daily_used = 0 WHERE user_id = 'user123';
```

### Worker 无响应

```bash
# 检查 Worker 状态
celery -A tasks inspect active

# 重启 Worker
docker-compose restart worker
# 或
kubectl rollout restart deployment/worker -n report-agent
```

### 数据库连接问题

```bash
# 检查数据库连接
docker exec -it report-postgres psql -U postgres -c "SELECT 1"

# 查看连接数
docker exec -it report-postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity"
```

## 生产环境清单

### 安全

- [ ] 修改所有默认密码
- [ ] 配置 SSL/TLS 证书
- [ ] 启用 API 认证
- [ ] 配置防火墙规则
- [ ] 设置网络策略（Kubernetes）

### 性能

- [ ] 调整副本数量
- [ ] 配置资源限制
- [ ] 启用缓存
- [ ] 配置 CDN（静态资源）

### 可靠性

- [ ] 配置健康检查
- [ ] 设置自动重启策略
- [ ] 配置备份策略
- [ ] 设置监控告警

### 运维

- [ ] 配置日志收集
- [ ] 设置监控面板
- [ ] 准备故障恢复方案
- [ ] 文档化部署流程
