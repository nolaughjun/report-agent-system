# tools/llm.py — LLM 和搜索工具
"""LLM 和搜索工具模块

特性：
1. 多模型支持（DeepSeek、OpenAI、Claude、本地模型等）
2. 数据多源接入（Tavily、自建API、数据库等）
3. Token 使用量统计
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Any, Literal, Optional
from dataclasses import dataclass, field

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 多模型配置
# ══════════════════════════════════════════════════════════════

@dataclass
class ModelConfig:
    """模型配置"""
    name: str                          # 配置名称
    provider: str                      # 提供商 (deepseek, openai, anthropic, local)
    model_id: str                      # 模型ID
    api_key_env: str                   # API Key 环境变量名
    base_url: Optional[str] = None     # API Base URL
    max_tokens: int = 4096             # 默认最大输出 tokens
    supports_json: bool = True         # 是否支持 JSON 模式
    supports_streaming: bool = True    # 是否支持流式输出


# 预定义的模型配置
MODEL_CONFIGS: dict[str, ModelConfig] = {
    # DeepSeek 模型
    "deepseek-chat": ModelConfig(
        name="DeepSeek Chat",
        provider="deepseek",
        model_id="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),
    "deepseek-reasoner": ModelConfig(
        name="DeepSeek Reasoner",
        provider="deepseek",
        model_id="deepseek-reasoner",
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),
    # OpenAI 模型
    "gpt-4o": ModelConfig(
        name="GPT-4o",
        provider="openai",
        model_id="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
    ),
    "gpt-4o-mini": ModelConfig(
        name="GPT-4o Mini",
        provider="openai",
        model_id="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
    ),
    # Claude 模型（通过 OpenAI 兼容接口）
    "claude-3-sonnet": ModelConfig(
        name="Claude 3 Sonnet",
        provider="anthropic",
        model_id="claude-3-5-sonnet-20241022",
        api_key_env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com/v1",
    ),
    # 本地模型（如 Ollama）
    "local-llama": ModelConfig(
        name="Local Llama",
        provider="local",
        model_id="llama3.1:70b",
        api_key_env="",  # 本地模型不需要
        base_url="http://localhost:11434/v1",
    ),
    # 自定义模型
    "custom": ModelConfig(
        name="Custom Model",
        provider="custom",
        model_id=os.environ.get("CUSTOM_MODEL_ID", "custom-model"),
        api_key_env="CUSTOM_API_KEY",
        base_url=os.environ.get("CUSTOM_API_BASE", ""),
    ),
}

# 默认模型
DEFAULT_MODEL = os.environ.get("DEFAULT_LLM_MODEL", "deepseek-chat")

# 当前活动模型
_current_model: str = DEFAULT_MODEL


def get_available_models() -> list[str]:
    """获取可用模型列表"""
    available = []
    for model_id, config in MODEL_CONFIGS.items():
        if config.provider == "local":
            # 本地模型总是可用
            available.append(model_id)
        elif config.api_key_env:
            api_key = os.environ.get(config.api_key_env, "")
            if api_key:
                available.append(model_id)
    return available


def set_current_model(model_id: str) -> bool:
    """设置当前使用的模型

    Args:
        model_id: 模型标识

    Returns:
        是否设置成功
    """
    global _current_model

    if model_id not in MODEL_CONFIGS:
        logger.warning("[llm] 未知模型: %s", model_id)
        return False

    config = MODEL_CONFIGS[model_id]

    # 检查 API Key（本地模型除外）
    if config.provider != "local" and config.api_key_env:
        api_key = os.environ.get(config.api_key_env, "")
        if not api_key:
            logger.warning("[llm] 模型 %s 缺少 API Key: %s", model_id, config.api_key_env)
            return False

    _current_model = model_id
    logger.info("[llm] 切换到模型: %s (%s)", config.name, model_id)
    return True


def get_current_model() -> str:
    """获取当前模型"""
    return _current_model


def get_model_config(model_id: str = None) -> ModelConfig:
    """获取模型配置"""
    model_id = model_id or _current_model
    return MODEL_CONFIGS.get(model_id, MODEL_CONFIGS[DEFAULT_MODEL])


# ══════════════════════════════════════════════════════════════
# LLM 客户端工厂
# ══════════════════════════════════════════════════════════════

_client_cache: dict[str, OpenAI] = {}


def get_client(model_id: str = None) -> OpenAI:
    """获取或创建 LLM 客户端

    Args:
        model_id: 模型标识，默认使用当前模型

    Returns:
        OpenAI 兼容客户端
    """
    model_id = model_id or _current_model
    config = get_model_config(model_id)

    # 检查缓存
    cache_key = f"{config.provider}:{config.base_url}"
    if cache_key in _client_cache:
        return _client_cache[cache_key]

    # 获取 API Key
    api_key = ""
    if config.api_key_env:
        api_key = os.environ.get(config.api_key_env, "")

    # 本地模型使用占位符
    if config.provider == "local":
        api_key = "local"

    # 创建客户端
    client = OpenAI(
        base_url=config.base_url,
        api_key=api_key,
    )

    _client_cache[cache_key] = client
    logger.info("[llm] 创建客户端: provider=%s, base_url=%s", config.provider, config.base_url)

    return client


# ══════════════════════════════════════════════════════════════
# Token 使用量统计
# ══════════════════════════════════════════════════════════════

_token_stats = {
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "call_count": 0,
}


def get_token_stats() -> dict:
    """获取全局 Token 统计"""
    return _token_stats.copy()


def reset_token_stats():
    """重置 Token 统计"""
    _token_stats["total_prompt_tokens"] = 0
    _token_stats["total_completion_tokens"] = 0
    _token_stats["call_count"] = 0


def now_iso() -> str:
    """获取当前 ISO8601 时间戳"""
    return datetime.now(UTC).isoformat()


# ══════════════════════════════════════════════════════════════
# LLM 调用接口
# ══════════════════════════════════════════════════════════════

def chat(
    messages: list[dict[str, str]],
    model: str = None,
    json_mode: bool = False,
    max_tokens: int = None,
    temperature: float = 0.1,
    node: str = "unknown",
    use_cache: bool = False,
    parent_run_id: str = None,
) -> str:
    """统一 LLM 调用入口

    Args:
        messages: 对话消息列表
        model: 模型名称（可选，默认使用当前模型）
        json_mode: 是否使用 JSON 模式
        max_tokens: 最大输出 token 数
        temperature: 温度参数
        node: 调用节点名称，用于统计
        use_cache: 是否使用缓存
        parent_run_id: LangSmith 父运行 ID

    Returns:
        模型输出文本
    """
    model_id = model or _current_model
    start_time = time.perf_counter()

    # 尝试从缓存获取
    if use_cache and temperature < 0.2:  # 低温度时才使用缓存
        try:
            from cache import get_llm_cache
            cached = get_llm_cache(messages, model_id)
            if cached is not None:
                logger.info("[chat] 缓存命中: model=%s, node=%s", model_id, node)
                return cached
        except Exception as e:
            logger.warning("[chat] 缓存获取失败: %s", e)

    config = get_model_config(model_id)
    client = get_client(model_id)

    # 使用配置的默认值
    if max_tokens is None:
        max_tokens = config.max_tokens

    kwargs: dict[str, Any] = {
        "model": config.model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    if json_mode and config.supports_json:
        kwargs["response_format"] = {"type": "json_object"}

    # LangSmith 追踪
    run_id = None
    try:
        from langsmith_client import trace_llm_call
    except ImportError:
        trace_llm_call = None

    try:
        resp = client.chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # 统计 Token 使用量
        prompt_tokens = 0
        completion_tokens = 0
        if resp.usage:
            prompt_tokens = resp.usage.prompt_tokens or 0
            completion_tokens = resp.usage.completion_tokens or 0

            _token_stats["total_prompt_tokens"] += prompt_tokens
            _token_stats["total_completion_tokens"] += completion_tokens
            _token_stats["call_count"] += 1

            logger.info(
                "[chat] model=%s, node=%s, prompt=%d, completion=%d, latency=%dms",
                model_id, node, prompt_tokens, completion_tokens, latency_ms
            )

        content = resp.choices[0].message.content or ""

        # LangSmith 追踪记录
        if trace_llm_call:
            try:
                usage = {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": prompt_tokens + completion_tokens,
                }
                trace_llm_call(
                    model=model_id,
                    messages=messages,
                    response=content[:1000],  # 截断避免存储过大
                    usage=usage,
                    latency_ms=latency_ms,
                    parent_run_id=parent_run_id,
                )
            except Exception as e:
                logger.warning("[chat] LangSmith 追踪失败: %s", e)

        # 写入缓存
        if use_cache and temperature < 0.2 and content:
            try:
                from cache import set_llm_cache
                set_llm_cache(messages, content, model_id)
                logger.info("[chat] 响应已缓存: model=%s", model_id)
            except Exception as e:
                logger.warning("[chat] 缓存写入失败: %s", e)

        return content

    except Exception as e:
        logger.error("[chat] 调用失败: model=%s, error=%s", model_id, e)
        raise


def chat_with_usage(
    messages: list[dict[str, str]],
    model: str = None,
    json_mode: bool = False,
    max_tokens: int = None,
    temperature: float = 0.1,
    node: str = "unknown",
) -> tuple[str, dict]:
    """带 Token 使用量返回的 LLM 调用

    Returns:
        (输出文本, Token 使用量字典)
    """
    model_id = model or _current_model
    config = get_model_config(model_id)
    client = get_client(model_id)

    if max_tokens is None:
        max_tokens = config.max_tokens

    kwargs: dict[str, Any] = {
        "model": config.model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    if json_mode and config.supports_json:
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""

    # 构建使用量字典
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "model": model_id,
        "timestamp": now_iso(),
        "node": node,
    }

    if resp.usage:
        usage["prompt_tokens"] = resp.usage.prompt_tokens or 0
        usage["completion_tokens"] = resp.usage.completion_tokens or 0
        usage["total_tokens"] = resp.usage.total_tokens or (usage["prompt_tokens"] + usage["completion_tokens"])

        _token_stats["total_prompt_tokens"] += usage["prompt_tokens"]
        _token_stats["total_completion_tokens"] += usage["completion_tokens"]
        _token_stats["call_count"] += 1

        logger.info(
            "[chat_with_usage] model=%s, node=%s, prompt=%d, completion=%d",
            model_id, node, usage["prompt_tokens"], usage["completion_tokens"]
        )

    return content, usage


def make_token_usage_update(usage: dict) -> dict:
    """创建 Token 使用量状态更新

    用于节点返回值，将 Token 使用量记录到状态中
    """
    from state import TokenUsage

    token_record: TokenUsage = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "model": usage.get("model", "unknown"),
        "timestamp": usage.get("timestamp", now_iso()),
        "node": usage.get("node", "unknown"),
    }

    return {
        "token_usage": [token_record],
        "total_prompt_tokens": usage.get("prompt_tokens", 0),
        "total_completion_tokens": usage.get("completion_tokens", 0),
    }


# ══════════════════════════════════════════════════════════════
# 数据多源接入
# ══════════════════════════════════════════════════════════════

@dataclass
class DataSourceConfig:
    """数据源配置"""
    name: str                           # 数据源名称
    source_type: str                    # 类型 (tavily, custom_api, database, file)
    api_key_env: str = ""               # API Key 环境变量
    base_url: str = ""                  # API Base URL
    enabled: bool = True                # 是否启用
    priority: int = 0                   # 优先级（越大越优先）
    extra_config: dict = field(default_factory=dict)  # 额外配置


# 预定义的数据源配置
DATA_SOURCES: dict[str, DataSourceConfig] = {
    "tavily": DataSourceConfig(
        name="Tavily Search",
        source_type="tavily",
        api_key_env="TAVILY_API_KEY",
        base_url="https://api.tavily.com/search",
        priority=10,
    ),
    "serper": DataSourceConfig(
        name="Serper (Google Search)",
        source_type="custom_api",
        api_key_env="SERPER_API_KEY",
        base_url="https://google.serper.dev/search",
        priority=8,
    ),
    "brave": DataSourceConfig(
        name="Brave Search",
        source_type="custom_api",
        api_key_env="BRAVE_API_KEY",
        base_url="https://api.search.brave.com/res/v1/web/search",
        priority=7,
    ),
    "custom_search": DataSourceConfig(
        name="Custom Search API",
        source_type="custom_api",
        api_key_env="CUSTOM_SEARCH_API_KEY",
        base_url=os.environ.get("CUSTOM_SEARCH_URL", ""),
        priority=5,
    ),
}

# 默认数据源
DEFAULT_DATA_SOURCE = os.environ.get("DEFAULT_DATA_SOURCE", "tavily")

# 当前数据源列表（按优先级排序）
_active_data_sources: list[str] = []


def get_available_data_sources() -> list[str]:
    """获取可用数据源列表"""
    available = []
    for name, config in DATA_SOURCES.items():
        if not config.enabled:
            continue
        if config.api_key_env:
            api_key = os.environ.get(config.api_key_env, "")
            if api_key:
                available.append(name)
        elif config.source_type in ["database", "file"]:
            available.append(name)
    return sorted(available, key=lambda x: DATA_SOURCES[x].priority, reverse=True)


def set_active_data_sources(sources: list[str]):
    """设置活动数据源

    Args:
        sources: 数据源名称列表
    """
    global _active_data_sources
    _active_data_sources = [s for s in sources if s in DATA_SOURCES]
    logger.info("[data_source] 设置活动数据源: %s", _active_data_sources)


def get_active_data_sources() -> list[str]:
    """获取活动数据源"""
    if not _active_data_sources:
        available = get_available_data_sources()
        return available[:1] if available else []
    return _active_data_sources


def search_multi_source(
    query: str,
    max_results: int = 5,
    sources: list[str] = None,
) -> dict[str, Any]:
    """多源搜索

    从多个数据源并行搜索，合并结果

    Args:
        query: 搜索查询
        max_results: 每个源最大结果数
        sources: 指定数据源列表（可选）

    Returns:
        合并后的搜索结果
    """
    active_sources = sources or get_active_data_sources()

    if not active_sources:
        logger.warning("[search_multi_source] 无可用数据源")
        return {"answer": "", "results": [], "source": "none"}

    # 从优先级最高的源搜索
    for source_name in active_sources:
        config = DATA_SOURCES.get(source_name)
        if not config:
            continue

        try:
            if config.source_type == "tavily":
                result = _search_tavily(query, max_results, config)
            elif config.source_type == "custom_api":
                result = _search_custom_api(query, max_results, config)
            else:
                continue

            if result.get("results"):
                result["source"] = source_name
                logger.info("[search_multi_source] 从 %s 获取 %d 条结果", source_name, len(result["results"]))
                return result

        except Exception as e:
            logger.warning("[search_multi_source] 数据源 %s 失败: %s", source_name, e)
            continue

    return {"answer": "", "results": [], "source": "failed"}


def _search_tavily(query: str, max_results: int, config: DataSourceConfig) -> dict:
    """Tavily 搜索"""
    api_key = os.environ.get(config.api_key_env, "")

    if not api_key:
        return {"answer": "", "results": []}

    try:
        resp = requests.post(
            config.base_url,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
                "include_raw_content": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        return {
            "answer": data.get("answer", ""),
            "results": [
                {"title": r["title"], "url": r["url"], "content": r["content"]}
                for r in data.get("results", [])
            ],
        }
    except Exception as e:
        logger.error("[_search_tavily] 搜索失败: %s", e)
        return {"answer": f"搜索失败：{e}", "results": []}


def _search_custom_api(query: str, max_results: int, config: DataSourceConfig) -> dict:
    """自定义 API 搜索"""
    api_key = os.environ.get(config.api_key_env, "")

    if not api_key or not config.base_url:
        return {"answer": "", "results": []}

    try:
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        resp = requests.post(
            config.base_url,
            headers=headers,
            json={"q": query, "num": max_results},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        # 适配不同 API 的响应格式
        results = []
        if "organic" in data:  # Serper 格式
            for r in data["organic"][:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "content": r.get("snippet", ""),
                })
        elif "results" in data:  # 通用格式
            for r in data["results"][:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", r.get("link", "")),
                    "content": r.get("content", r.get("snippet", "")),
                })

        return {"answer": data.get("answer", ""), "results": results}

    except Exception as e:
        logger.error("[_search_custom_api] 搜索失败: %s", e)
        return {"answer": f"搜索失败：{e}", "results": []}


# 兼容旧接口
def tavily_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """同步 Tavily 搜索（兼容旧接口）"""
    return search_multi_source(query, max_results, ["tavily"])


async def tavily_search_async(query: str, max_results: int = 5) -> dict[str, Any]:
    """异步搜索"""
    import aiohttp

    active_sources = get_active_data_sources()
    if not active_sources:
        return {"answer": "", "results": []}

    config = DATA_SOURCES.get(active_sources[0])
    if not config:
        return {"answer": "", "results": []}

    api_key = os.environ.get(config.api_key_env, "")

    if not api_key:
        return {
            "answer": f"[模拟] 关于「{query}」的搜索结果",
            "results": [{"title": "模拟来源", "url": "", "content": "无内容"}],
        }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.base_url,
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": True,
                    "include_raw_content": False,
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json()
                return {
                    "answer": data.get("answer", ""),
                    "results": [
                        {"title": r["title"], "url": r["url"], "content": r["content"]}
                        for r in data.get("results", [])
                    ],
                }
    except Exception as e:
        logger.error("[tavily_search_async] 搜索失败: %s", e)
        return {"answer": f"搜索失败：{e}", "results": []}


# ══════════════════════════════════════════════════════════════
# 日志脱敏
# ══════════════════════════════════════════════════════════════

def sanitize_for_logging(text: str) -> str:
    """日志脱敏"""
    text = re.sub(r"sk-[a-zA-Z0-9]{20,}", "sk-***", text)
    text = re.sub(r"tvly-[a-zA-Z0-9]{20,}", "tvly-***", text)
    text = re.sub(r"[a-zA-Z0-9]{32,}", "***REDACTED***", text)
    return text


# ══════════════════════════════════════════════════════════════
# 性能计时工具
# ══════════════════════════════════════════════════════════════

class Timer:
    """计时器上下文管理器"""

    def __init__(self, name: str = ""):
        self.name = name
        self.start_time = 0
        self.elapsed_ms = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = int((time.perf_counter() - self.start_time) * 1000)
        if self.name:
            logger.info("[Timer] %s: %d ms", self.name, self.elapsed_ms)

    @staticmethod
    def now_ms() -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.perf_counter() * 1000)


# ══════════════════════════════════════════════════════════════
# 初始化
# ══════════════════════════════════════════════════════════════

def _init():
    """初始化模块"""
    # 设置默认模型
    available = get_available_models()
    if DEFAULT_MODEL not in available and available:
        logger.warning("[llm] 默认模型 %s 不可用，使用 %s", DEFAULT_MODEL, available[0])
        set_current_model(available[0])
    else:
        set_current_model(DEFAULT_MODEL)

    # 初始化数据源
    data_sources = get_available_data_sources()
    if data_sources:
        set_active_data_sources(data_sources)
        logger.info("[llm] 可用数据源: %s", data_sources)
    else:
        logger.warning("[llm] 无可用数据源，请配置 API Key")


# 执行初始化
_init()
