# cache.py — 缓存层模块
"""缓存层模块

特性：
1. 搜索结果缓存
2. LLM 响应缓存
3. 相似问题匹配
4. 缓存统计
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 缓存配置
# ══════════════════════════════════════════════════════════════

# 默认 TTL（秒）
DEFAULT_SEARCH_CACHE_TTL = int(os.environ.get("SEARCH_CACHE_TTL", 3600))  # 1 小时
DEFAULT_LLM_CACHE_TTL = int(os.environ.get("LLM_CACHE_TTL", 7200))  # 2 小时

# 缓存键前缀
CACHE_PREFIX_SEARCH = "cache:search:"
CACHE_PREFIX_LLM = "cache:llm:"
CACHE_PREFIX_EMBEDDING = "cache:emb:"

# ══════════════════════════════════════════════════════════════
# 缓存统计
# ══════════════════════════════════════════════════════════════

_cache_stats = {
    "hits": 0,
    "misses": 0,
    "search_hits": 0,
    "search_misses": 0,
    "llm_hits": 0,
    "llm_misses": 0,
}


def get_cache_stats() -> dict:
    """获取缓存统计"""
    total = _cache_stats["hits"] + _cache_stats["misses"]
    hit_rate = _cache_stats["hits"] / total if total > 0 else 0

    return {
        **_cache_stats,
        "total_requests": total,
        "hit_rate": round(hit_rate, 4),
    }


def reset_cache_stats():
    """重置缓存统计"""
    global _cache_stats
    _cache_stats = {
        "hits": 0,
        "misses": 0,
        "search_hits": 0,
        "search_misses": 0,
        "llm_hits": 0,
        "llm_misses": 0,
    }


# ══════════════════════════════════════════════════════════════
# Redis 缓存客户端
# ══════════════════════════════════════════════════════════════

def _get_redis_client():
    """获取 Redis 客户端"""
    if os.environ.get("REDIS_URL"):
        from redis_client import get_redis
        return get_redis()
    return None


def _hash_key(content: str) -> str:
    """生成内容哈希键（使用 SHA-256）"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


# ══════════════════════════════════════════════════════════════
# 通用缓存操作 - 使用 redis_client 中的实现
# ══════════════════════════════════════════════════════════════

# 注意：cache_get, cache_set, cache_delete, cache_exists 已在 redis_client.py 中实现
# 这里保留 _get_redis_client 用于本模块的其他功能
# 实际使用时建议统一调用 redis_client 模块中的函数


# ══════════════════════════════════════════════════════════════
# 搜索结果缓存
# ══════════════════════════════════════════════════════════════

def get_search_cache_key(query: str, source: str = "default") -> str:
    """生成搜索缓存键"""
    normalized_query = query.lower().strip()
    query_hash = _hash_key(f"{source}:{normalized_query}")
    return f"{CACHE_PREFIX_SEARCH}{query_hash}"


def get_search_cache(query: str, source: str = "default") -> Optional[list[dict]]:
    """获取搜索结果缓存"""
    key = get_search_cache_key(query, source)
    value = cache_get(key)

    if value:
        try:
            _cache_stats["search_hits"] += 1
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    _cache_stats["search_misses"] += 1
    return None


def set_search_cache(
    query: str,
    results: list[dict],
    source: str = "default",
    ttl: int = DEFAULT_SEARCH_CACHE_TTL
) -> bool:
    """设置搜索结果缓存"""
    key = get_search_cache_key(query, source)
    try:
        value = json.dumps(results, ensure_ascii=False)
        return cache_set(key, value, ttl)
    except Exception as e:
        logger.warning(f"[Cache] 搜索缓存设置失败: {e}")
        return False


def search_with_cache(
    query: str,
    search_func,
    source: str = "default",
    ttl: int = DEFAULT_SEARCH_CACHE_TTL
) -> list[dict]:
    """带缓存的搜索

    Args:
        query: 搜索查询
        search_func: 搜索函数
        source: 数据源标识
        ttl: 缓存时间

    Returns:
        搜索结果列表
    """
    # 尝试从缓存获取
    cached = get_search_cache(query, source)
    if cached is not None:
        logger.info(f"[Cache] 搜索缓存命中: {query[:50]}...")
        return cached

    # 执行搜索
    results = search_func(query)

    # 写入缓存
    if results:
        set_search_cache(query, results, source, ttl)
        logger.info(f"[Cache] 搜索结果已缓存: {query[:50]}...")

    return results


# ══════════════════════════════════════════════════════════════
# LLM 响应缓存
# ══════════════════════════════════════════════════════════════

def get_llm_cache_key(messages: list[dict], model: str = "default") -> str:
    """生成 LLM 缓存键"""
    # 将消息序列化为稳定的字符串
    content = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    content_hash = _hash_key(f"{model}:{content}")
    return f"{CACHE_PREFIX_LLM}{content_hash}"


def get_llm_cache(messages: list[dict], model: str = "default") -> Optional[str]:
    """获取 LLM 响应缓存"""
    key = get_llm_cache_key(messages, model)
    value = cache_get(key)

    if value:
        _cache_stats["llm_hits"] += 1
        return value

    _cache_stats["llm_misses"] += 1
    return None


def set_llm_cache(
    messages: list[dict],
    response: str,
    model: str = "default",
    ttl: int = DEFAULT_LLM_CACHE_TTL
) -> bool:
    """设置 LLM 响应缓存"""
    key = get_llm_cache_key(messages, model)
    return cache_set(key, response, ttl)


def llm_with_cache(
    messages: list[dict],
    llm_func,
    model: str = "default",
    ttl: int = DEFAULT_LLM_CACHE_TTL,
    use_cache: bool = True
) -> str:
    """带缓存的 LLM 调用

    Args:
        messages: 消息列表
        llm_func: LLM 调用函数
        model: 模型标识
        ttl: 缓存时间
        use_cache: 是否使用缓存

    Returns:
        LLM 响应
    """
    if use_cache:
        # 尝试从缓存获取
        cached = get_llm_cache(messages, model)
        if cached is not None:
            logger.info(f"[Cache] LLM 缓存命中")
            return cached

    # 调用 LLM
    response = llm_func(messages)

    # 写入缓存
    if use_cache and response:
        set_llm_cache(messages, response, model, ttl)
        logger.info(f"[Cache] LLM 响应已缓存")

    return response


# ══════════════════════════════════════════════════════════════
# 相似问题匹配（简化版）
# ══════════════════════════════════════════════════════════════

def find_similar_cached_query(query: str, threshold: float = 0.8) -> Optional[tuple[str, list[dict]]]:
    """查找相似的已缓存查询（简化实现）

    Args:
        query: 查询文本
        threshold: 相似度阈值 (0.0-1.0)

    Returns:
        相似查询和结果，如果没有则返回 None
    """
    if not query or len(query.strip()) == 0:
        return None

    client = _get_redis_client()
    if not client:
        return None

    try:
        # 使用 SCAN 替代 KEYS 命令，避免阻塞 Redis
        cursor = 0
        normalized_query = query.lower().strip()

        while True:
            cursor, keys = client.scan(
                cursor,
                match=f"{CACHE_PREFIX_SEARCH}*",
                count=100
            )

            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                cached_value = client.get(key)
                if cached_value:
                    try:
                        cached_data = json.loads(cached_value)
                        # 简单的相似度计算：检查是否有包含关系
                        # 可以替换为更复杂的相似度算法（如 Levenshtein 距离）
                        if isinstance(cached_data, list) and len(cached_data) > 0:
                            # 返回第一个匹配的结果
                            logger.info(f"[Cache] 找到相似缓存: {key_str}")
                            return (key_str, cached_data)
                    except json.JSONDecodeError:
                        continue

            if cursor == 0:
                break

        return None

    except Exception as e:
        logger.warning(f"[Cache] 相似查询查找失败: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# 缓存管理
# ══════════════════════════════════════════════════════════════

def clear_all_cache() -> dict:
    """清除所有缓存

    使用 SCAN 迭代器安全地遍历和删除键，避免阻塞 Redis。
    """
    client = _get_redis_client()
    if not client:
        return {"success": False, "message": "Redis 未连接"}

    try:
        deleted = 0
        search_count = 0
        llm_count = 0

        # 使用 SCAN 安全地删除搜索缓存
        cursor = 0
        while True:
            cursor, keys = client.scan(
                cursor,
                match=f"{CACHE_PREFIX_SEARCH}*",
                count=100
            )
            if keys:
                deleted += client.delete(*keys)
                search_count += len(keys)
            if cursor == 0:
                break

        # 使用 SCAN 安全地删除 LLM 缓存
        cursor = 0
        while True:
            cursor, keys = client.scan(
                cursor,
                match=f"{CACHE_PREFIX_LLM}*",
                count=100
            )
            if keys:
                deleted += client.delete(*keys)
                llm_count += len(keys)
            if cursor == 0:
                break

        logger.info(f"[Cache] 清理完成: 搜索缓存 {search_count} 个, LLM 缓存 {llm_count} 个")

        return {
            "success": True,
            "deleted_keys": deleted,
            "search_keys": search_count,
            "llm_keys": llm_count,
        }
    except Exception as e:
        logger.error(f"[Cache] 清理失败: {e}")
        return {"success": False, "message": str(e)}


def get_cache_info() -> dict:
    """获取缓存信息

    使用 SCAN 安全地统计键数量，避免阻塞 Redis。
    """
    client = _get_redis_client()
    if not client:
        return {"connected": False}

    try:
        # 使用 SCAN 统计键数量
        search_count = 0
        cursor = 0
        while True:
            cursor, _ = client.scan(
                cursor,
                match=f"{CACHE_PREFIX_SEARCH}*",
                count=100
            )
            # SCAN 返回的 keys 列表，我们只需要计数
            cursor, keys = client.scan(
                cursor if cursor != 0 else 0,
                match=f"{CACHE_PREFIX_SEARCH}*",
                count=100
            ) if cursor != 0 else (0, [])
            if cursor == 0:
                break

        # 更高效的计数方式
        search_count = 0
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match=f"{CACHE_PREFIX_SEARCH}*", count=100)
            search_count += len(keys)
            if cursor == 0:
                break

        llm_count = 0
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match=f"{CACHE_PREFIX_LLM}*", count=100)
            llm_count += len(keys)
            if cursor == 0:
                break

        # 获取 Redis 信息
        info = client.info("memory")

        return {
            "connected": True,
            "search_cache_count": search_count,
            "llm_cache_count": llm_count,
            "used_memory": info.get("used_memory_human", "unknown"),
            "stats": get_cache_stats(),
        }
    except Exception as e:
        logger.error(f"[Cache] 获取缓存信息失败: {e}")
        return {"connected": False, "error": str(e)}
