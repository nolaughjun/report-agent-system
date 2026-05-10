# 报告智能体系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.1.9+-green.svg)](https://github.com/langchain-ai/langgraph)

基于 LLM 大语言模型和 LangGraph 框架的自动化报告生成平台。

**核心价值**: 输入主题，自动生成专业级报告

## ✨ 特性

### 核心功能
- 🚀 **端到端自动化** - 从主题到报告，全程自动
- 🔄 **并发数据收集** - asyncio 驱动的高效并发搜索
- 🤖 **多模型支持** - DeepSeek、OpenAI、Claude、本地模型
- 🌐 **多数据源** - Tavily、Serper、Brave、自定义 API
- 👤 **人工审核** - Human-in-the-loop 关键决策干预
- ⏰ **定时执行** - 支持单次/每日/每周/每月调度

### 企业级特性 (v2.0)
- 🔥 **高并发支持** - 支持 100 人同时使用
- 📦 **任务队列** - Celery 异步任务处理
- 💾 **持久化存储** - Redis 状态 + PostgreSQL 数据
- ⚡ **智能缓存** - 搜索结果和 LLM 响应缓存
- 🛡️ **API 限流** - 多层次限流保护
- 📊 **用户配额** - 每日/每月使用限制
- 🐳 **水平扩展** - Docker Compose / Kubernetes 部署
- 🔒 **安全审计** - 内置红黑对抗安全检查
- 📈 **Token 统计** - 完整的使用量追踪
- ⏪ **版本回滚** - 基于快照的时间旅行功能
- 📚 **Wiki 知识库** - 报告自动入库，知识复用加速生成
- 📡 **LangSmith 监控** - LLM 调用追踪和性能分析

## 📋 目录

- [快速开始](#-快速开始)
- [安装](#-安装)
- [使用方法](#-使用方法)
- [Wiki 知识库](#-wiki-知识库)
- [并发架构](#-并发架构)
- [项目结构](#-项目结构)
- [配置说明](#-配置说明)
- [API 文档](#-api-文档)
- [部署指南](#-部署指南)
- [开发指南](#-开发指南)
- [测试](#-测试)
- [贡献指南](#-贡献指南)
- [许可证](#-许可证)

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Redis 7.0+ (并发模式)
- PostgreSQL 15+ (并发模式)
- [pandoc](https://pandoc.org/installing.html) (PDF 导出)
- [MiKTeX](https://miktex.org/) 或 TeX Live (PDF 导出，中文支持)

### 安装

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

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入您的 API Key
```

### 最简示例

```bash
# 交互模式
python main.py -i

# 命令行模式
python main.py --topic "AI发展趋势报告" --type research

# 启动 API 服务（并发模式）
docker-compose up -d
```

## 📦 安装

### 使用 pip

```bash
pip install -r requirements.txt
```

### 使用 Docker (单实例)

```bash
# 构建镜像
docker build -t report-agent .

# 运行容器
docker run -d \
  -p 8000:8000 \
  -e DEEPSEEK_API_KEY=your-key \
  -e TAVILY_API_KEY=your-key \
  report-agent
```

### 使用 Docker Compose (并发模式)

```bash
# 启动所有服务（Redis + PostgreSQL + API + Workers）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 水平扩展
docker-compose up -d --scale api=5 --scale worker=10
```

### 使用 Kubernetes (生产环境)

```bash
# 部署到 Kubernetes
kubectl apply -f k8s/

# 查看部署状态
kubectl get all -n report-agent
```

## 🔧 使用方法

### 命令行模式

```bash
# 生成研究报告
python main.py --topic "人工智能发展趋势" --type research --lang zh

# 并发收集（5个并发）
python main.py --topic "市场分析报告" --concurrent 5

# 定时执行
python main.py --topic "日报" --schedule "09:00" --recurrence daily
```

### Python API

```python
from graph import create_report_graph
from state import create_initial_state

# 创建图
app = create_report_graph()

# 初始化状态
initial_state = create_initial_state(
    topic="AI发展趋势",
    report_type="research",
    language="zh"
)

# 执行
result = app.invoke(initial_state)

# 获取报告
print(result["final_report"])
```

### REST API

```bash
# 启动服务
uvicorn api:app --host 0.0.0.0 --port 8000

# 创建报告任务
curl -X POST http://localhost:8000/api/reports \
  -H "Content-Type: application/json" \
  -d '{"topic": "AI发展趋势", "report_type": "research"}'

# 响应
# {"thread_id": "abc12345", "status": "pending", "message": "任务已提交"}

# 查询任务状态
curl http://localhost:8000/api/reports/abc12345

# 恢复任务执行（人工审核后）
curl -X POST "http://localhost:8000/api/reports/abc12345/resume?decision=approve"
```

## 📚 Wiki 知识库

Wiki 知识库是一个智能知识管理系统，能够自动将生成的报告转化为可复用的知识点，加速后续报告生成。

### 核心功能

- **自动入库**: 报告生成完成后自动提取知识点存入知识库
- **智能检索**: 支持关键词搜索和语义搜索
- **知识复用**: 新报告生成时自动获取相关知识作为参考
- **分类管理**: 按技术、市场、数据、风险、建议等分类组织

### 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                    Wiki 知识库系统                           │
├─────────────────────────────────────────────────────────────┤
│  报告生成完成 ──▶ 章节分割 ──▶ 关键词提取 ──▶ 知识点入库    │
│       │                                          │          │
│       │                                          ▼          │
│       │              知识索引 + 向量存储                     │
│       │                                          │          │
│       ▼                                          ▼          │
│  新报告主题 ──▶ 知识检索 ──▶ 上下文生成 ──▶ 加速生成       │
└─────────────────────────────────────────────────────────────┘
```

### API 端点

```bash
# 搜索知识库
curl -X POST http://localhost:8000/api/wiki/search \
  -H "Content-Type: application/json" \
  -d '{"query": "人工智能", "limit": 5}'

# 获取知识库统计
curl http://localhost:8000/api/wiki/stats

# 推荐相关知识
curl "http://localhost:8000/api/wiki/recommend?topic=AI发展趋势"

# 手动入库报告
curl -X POST http://localhost:8000/api/wiki/ingest/{report_id}
```

### 配置选项

```bash
# 启用 Wiki 知识库
WIKI_ENABLED=true

# 知识点最小内容长度（字符）
WIKI_MIN_CONTENT_LENGTH=100

# 知识点最大分块大小（字符）
WIKI_MAX_CHUNK_SIZE=1000

# 相似度阈值（0-1）
WIKI_SIMILARITY_THRESHOLD=0.7
```

### 使用示例

```python
from wiki import search_knowledge, auto_ingest_report

# 搜索知识
results = search_knowledge("人工智能发展趋势", limit=5)
for r in results:
    print(f"标题: {r['title']}")
    print(f"分类: {r['category']}")
    print(f"相关度: {r['relevance_score']}")

# 手动入库报告
count = auto_ingest_report(
    report_content=report_text,
    report_id="report_001",
    report_title="AI 发展报告",
    report_type="research",
)
print(f"入库了 {count} 个知识点")
```

## 🏗️ 并发架构

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
              │  任务队列 │ 状态存储 │ 缓存层 │ 限流计数 │ 配额追踪         │
              └──────────────────────────┬───────────────────────────────────┘
                                         │
              ┌──────────────────────────┴───────────────────────────────────┐
              ↓                                                              ↓
    ┌──────────────────┐                                 ┌────────────────────┐
    │  PostgreSQL      │                                 │  Celery Workers    │
    │  任务持久化      │                                 │  Worker #1..N      │
    │  用户配额        │                                 │                    │
    │  报告历史        │                                 │                    │
    └──────────────────┘                                 └────────────────────┘
```

### 并发能力

| 配置 | 并发任务 | 100请求等待 |
|-----|---------|------------|
| 3 API + 5 Worker | 20 | ~5分钟 |
| 5 API + 10 Worker | 40 | ~2.5分钟 |
| 10 API + 20 Worker | 80 | ~1.5分钟 |

详细架构说明请参考 [SCALING.md](SCALING.md)。

## 📁 项目结构

```
report-agent-system/
├── state.py              # 状态定义
├── graph.py              # 图构建
├── main.py               # 主入口
├── api.py                # REST API
├── redis_client.py       # Redis 连接和 Celery 配置
├── database.py           # 数据库连接管理
├── models.py             # SQLAlchemy 数据模型
├── tasks.py              # Celery 后台任务
├── cache.py              # 缓存层模块
├── rate_limit.py         # API 限流和用户配额
├── wiki.py               # Wiki 知识库模块
├── langsmith_client.py   # LangSmith 监控客户端
├── tools/
│   ├── llm.py            # LLM + 多源搜索
│   ├── export.py         # 导出工具
│   └── time_travel.py    # 版本回滚
├── nodes/
│   ├── plan.py           # 规划节点
│   ├── gather_data.py    # 并发数据收集
│   ├── draft.py          # 草案撰写
│   ├── review.py         # 质量审核
│   ├── finalize.py       # 最终输出（含 Wiki 入库）
│   └── scheduler.py      # 时间施行
├── security/
│   └── security_audit.py # 安全审计
├── frontend/             # React 前端
│   ├── src/
│   │   ├── pages/        # 页面组件
│   │   ├── components/   # UI 组件
│   │   ├── store/        # 状态管理
│   │   └── lib/          # API 客户端
│   └── package.json
├── tests/
│   ├── test_unit_scaling.py      # 单元测试
│   ├── test_integration_scaling.py # 集成测试
│   ├── test_performance.py       # 性能测试
│   ├── test_concurrency.py       # 并发测试
│   ├── test_wiki.py              # Wiki 知识库测试
│   └── TEST_REPORT.md            # 测试报告
├── k8s/                   # Kubernetes 配置
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml
│   ├── postgres.yaml
│   ├── redis.yaml
│   ├── api-deployment.yaml
│   ├── worker-deployment.yaml
│   └── ingress.yaml
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── nginx.conf             # 负载均衡配置
├── .env.example
├── PRODUCT_GUIDE.md       # 产品说明文档
├── SCALING.md             # 并发扩展文档
├── LICENSE
├── CONTRIBUTING.md
├── SECURITY.md
└── CHANGELOG.md
```

## ⚙️ 配置说明

### 环境变量

```bash
# ══════════════════════════════════════════════════════════════
# LLM 配置
# ══════════════════════════════════════════════════════════════
DEEPSEEK_API_KEY=sk-xxx          # DeepSeek API Key
OPENAI_API_KEY=sk-xxx            # OpenAI API Key (可选)
ANTHROPIC_API_KEY=sk-xxx         # Claude API Key (可选)

# ══════════════════════════════════════════════════════════════
# 数据源配置
# ══════════════════════════════════════════════════════════════
TAVILY_API_KEY=tvly-xxx          # Tavily 搜索 API
SERPER_API_KEY=xxx               # Serper 搜索 API (可选)

# ══════════════════════════════════════════════════════════════
# 并发配置
# ══════════════════════════════════════════════════════════════
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/report_db

# ══════════════════════════════════════════════════════════════
# 缓存配置
# ══════════════════════════════════════════════════════════════
SEARCH_CACHE_TTL=3600            # 搜索缓存 TTL (秒)
LLM_CACHE_TTL=7200               # LLM 缓存 TTL (秒)

# ══════════════════════════════════════════════════════════════
# 限流配置
# ══════════════════════════════════════════════════════════════
RATE_LIMIT_ENABLED=true          # 启用限流
RATE_LIMIT_REQUESTS=60           # 每分钟请求数

# ══════════════════════════════════════════════════════════════
# 应用配置
# ══════════════════════════════════════════════════════════════
DEFAULT_LLM_MODEL=deepseek-chat  # 默认模型
DEFAULT_DATA_SOURCE=tavily       # 默认数据源
DEBUG=false
LOG_LEVEL=INFO
```

### 多模型配置

```python
from tools.llm import set_current_model, get_available_models

# 查看可用模型
print(get_available_models())
# ['deepseek-chat', 'openai-gpt4', 'anthropic-claude', 'local-llm']

# 切换模型
set_current_model('openai-gpt4')
```

### 多数据源配置

```python
from tools.llm import set_active_data_sources, get_available_data_sources

# 查看可用数据源
print(get_available_data_sources())
# ['tavily', 'serper', 'brave', 'custom']

# 设置活动数据源
set_active_data_sources(['tavily', 'serper'])
```

## 📖 API 文档

启动服务后访问：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Flower 监控: `http://localhost:5555`

### 主要端点

| 端点 | 方法 | 描述 |
|-----|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/reports` | POST | 创建报告任务 |
| `/api/reports/{id}` | GET | 获取报告状态 |
| `/api/reports/{id}/resume` | POST | 恢复任务执行 |
| `/api/models` | GET | 列出可用模型 |
| `/api/data-sources` | GET | 列出可用数据源 |
| `/api/reports/{id}/download` | GET | 下载报告 |
| `/api/security/audit` | GET | 运行安全审计 |
| `/api/wiki/search` | POST | 搜索知识库 |
| `/api/wiki/stats` | GET | 知识库统计 |
| `/api/wiki/recommend` | GET | 推荐相关知识 |
| `/api/monitoring/status` | GET | LangSmith 监控状态 |

详细 API 文档请参考 [PRODUCT_GUIDE.md](PRODUCT_GUIDE.md)。

## 🐳 部署指南

### Docker Compose (开发/测试)

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f api

# 水平扩展
docker-compose up -d --scale api=5 --scale worker=10
```

### Kubernetes (生产环境)

```bash
# 部署
kubectl apply -f k8s/

# 查看状态
kubectl get all -n report-agent

# 手动扩展
kubectl scale deployment api --replicas=5 -n report-agent
kubectl scale deployment worker --replicas=10 -n report-agent
```

详细部署说明请参考 [SCALING.md](SCALING.md)。

## 🛠️ 开发指南

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试类型
pytest tests/test_unit_scaling.py -v         # 单元测试
pytest tests/test_integration_scaling.py -v  # 集成测试
pytest tests/test_performance.py -v          # 性能测试
pytest tests/test_concurrency.py -v          # 并发测试

# 运行覆盖率
pytest tests/ --cov=. --cov-report=html
```

### 代码规范

```bash
# 格式化
black .
isort .

# 类型检查
mypy .

# 安全检查
safety check
pip-audit
```

### 内置安全审计

```python
from security import run_security_audit

# 运行完整审计
report = run_security_audit()
print(f"通过: {report.passed}")
print(f"问题: {report.summary['total_issues']}")
```

## 🧪 测试

### 测试报告

最新测试结果请查看 [TEST_REPORT.md](tests/TEST_REPORT.md)。

### 测试覆盖

| 测试类型 | 测试文件 | 覆盖模块 |
|---------|---------|---------|
| 单元测试 | test_unit_scaling.py | Redis、缓存、限流、模型、状态 |
| 集成测试 | test_integration_scaling.py | API 端点、缓存集成、配额集成 |
| 性能测试 | test_performance.py | API 响应、缓存操作、并发处理 |
| 并发测试 | test_concurrency.py | 限流并发、缓存并发、压力测试 |

## 🤝 贡献指南

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - AI Agent 工作流框架
- [DeepSeek](https://www.deepseek.com/) - LLM 服务
- [Tavily](https://tavily.com/) - 搜索 API
- [Celery](https://docs.celeryq.dev/) - 分布式任务队列
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Web 框架

## 📞 联系方式

- 问题反馈: [GitHub Issues](https://github.com/your-username/report-agent-system/issues)
- 安全问题: nolaughjun@gmail.com

---

**⭐ 如果这个项目对您有帮助，请给一个 Star！**
