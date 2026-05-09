# redis_client.py — Redis 连接和 Celery 配置
"""Redis 连接和 Celery 任务队列配置

特性：
1. Redis 连接池管理
2. Celery 任务队列配置
3. 状态存储支持
"""
from __future__ import annotations

import logging
import os

import redis
from celery import Celery

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# Redis 配置
# ══════════════════════════════════════════════════════════════

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Redis 连接池
redis_pool: redis.ConnectionPool | None = None


def get_redis_pool() -> redis.ConnectionPool:
    """获取 Redis 连接池（单例）"""
    global redis_pool
    if redis_pool is None:
        redis_pool = redis.ConnectionPool.from_url(REDIS_URL)
        logger.info(f"[Redis] 创建连接池: {REDIS_URL}")
    return redis_pool


def get_redis() -> redis.Redis:
    """获取 Redis 客户端"""
    return redis.Redis(connection_pool=get_redis_pool())


def check_redis_connection() -> bool:
    """检查 Redis 连接是否正常"""
    try:
        client = get_redis()
        client.ping()
        logger.info("[Redis] 连接正常")
        return True
    except Exception as e:
        logger.error(f"[Redis] 连接失败: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# Celery 配置
# ══════════════════════════════════════════════════════════════

# Celery 应用实例
celery_app = Celery(
    "report_tasks",
    broker=REDIS_URL,
    backend=f"{REDIS_URL.rsplit('/', 1)[0]}/1",  # 使用不同的 DB
    include=["tasks"]
)

# Celery 配置
celery_app.conf.update(
    # 序列化
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # 时区
    timezone="Asia/Shanghai",
    enable_utc=True,

    # 任务追踪
    task_track_started=True,
    task_time_limit=600,  # 10 分钟超时
    task_soft_time_limit=540,  # 9 分钟软超时

    # Worker 配置
    worker_prefetch_multiplier=1,  # 每次只取一个任务
    worker_max_tasks_per_child=50,  # 每个 worker 最多处理 50 个任务后重启

    # 结果过期
    result_expires=3600,  # 结果保留 1 小时

    # 任务路由（可选）
    task_routes={
        "tasks.generate_report_task": {"queue": "report"},
        "tasks.resume_report_task": {"queue": "report"},
    },

    # 任务重试
    task_acks_late=True,  # 任务完成后才确认
    task_reject_on_worker_lost=True,
)


def get_celery_app() -> Celery:
    """获取 Celery 应用实例"""
    return celery_app


# ══════════════════════════════════════════════════════════════
# 缓存工具函数
# ══════════════════════════════════════════════════════════════

def cache_get(key: str) -> str | None:
    """从缓存获取值

    Args:
        key: 缓存键

    Returns:
        缓存值，不存在返回 None

    Raises:
        RedisError: Redis 连接或操作错误
    """
    try:
        client = get_redis()
        value = client.get(key)
        if value is None:
            logger.debug(f"[Cache] 键不存在: {key}")
            return None
        decoded = value.decode('utf-8')
        logger.debug(f"[Cache] 获取成功: {key}, 长度: {len(decoded)}")
        return decoded
    except redis.RedisError as e:
        logger.error(f"[Cache] 获取失败: key={key}, error={e}")
        raise
    except Exception as e:
        logger.error(f"[Cache] 获取异常: key={key}, error={e}")
        raise


def cache_set(key: str, value: str, ttl: int = 3600) -> bool:
    """设置缓存值

    Args:
        key: 缓存键
        value: 缓存值
        ttl: 过期时间（秒），默认 1 小时

    Returns:
        是否设置成功

    Raises:
        RedisError: Redis 连接或操作错误
    """
    try:
        client = get_redis()
        result = client.setex(key, ttl, value)
        if result:
            logger.debug(f"[Cache] 设置成功: key={key}, ttl={ttl}")
        else:
            logger.warning(f"[Cache] 设置失败: key={key}")
        return bool(result)
    except redis.RedisError as e:
        logger.error(f"[Cache] 设置失败: key={key}, error={e}")
        raise
    except Exception as e:
        logger.error(f"[Cache] 设置异常: key={key}, error={e}")
        raise


def cache_delete(key: str) -> bool:
    """删除缓存

    Args:
        key: 缓存键

    Returns:
        是否删除成功（键存在并被删除）

    Raises:
        RedisError: Redis 连接或操作错误
    """
    try:
        client = get_redis()
        result = client.delete(key)
        deleted = result > 0
        if deleted:
            logger.debug(f"[Cache] 删除成功: key={key}")
        else:
            logger.debug(f"[Cache] 键不存在，无需删除: key={key}")
        return deleted
    except redis.RedisError as e:
        logger.error(f"[Cache] 删除失败: key={key}, error={e}")
        raise
    except Exception as e:
        logger.error(f"[Cache] 删除异常: key={key}, error={e}")
        raise


def cache_exists(key: str) -> bool:
    """检查缓存是否存在

    Args:
        key: 缓存键

    Returns:
        键是否存在

    Raises:
        RedisError: Redis 连接或操作错误
    """
    try:
        client = get_redis()
        result = client.exists(key)
        return result > 0
    except redis.RedisError as e:
        logger.error(f"[Cache] 检查存在失败: key={key}, error={e}")
        raise
    except Exception as e:
        logger.error(f"[Cache] 检查存在异常: key={key}, error={e}")
        raise


# ══════════════════════════════════════════════════════════════
# 分布式锁
# ══════════════════════════════════════════════════════════════

import uuid
from contextlib import contextmanager


@contextmanager
def distributed_lock(lock_name: str, timeout: int = 30):
    """分布式锁上下文管理器

    Args:
        lock_name: 锁名称
        timeout: 锁超时时间（秒）

    Yields:
        bool: 是否获取到锁
    """
    client = get_redis()
    lock_id = str(uuid.uuid4())
    lock_key = f"lock:{lock_name}"

    # 尝试获取锁
    acquired = client.set(lock_key, lock_id, nx=True, ex=timeout)

    try:
        yield bool(acquired)
    finally:
        # 释放锁（只有持有锁的人才能释放）
        if acquired:
            current_value = client.get(lock_key)
            if current_value and current_value.decode('utf-8') == lock_id:
                client.delete(lock_key)


# ══════════════════════════════════════════════════════════════
# 初始化检查
# ══════════════════════════════════════════════════════════════

def init_redis():
    """初始化 Redis 连接"""
    logger.info("[Redis] 初始化连接...")

    if check_redis_connection():
        logger.info("[Redis] 初始化成功")
        return True
    else:
        logger.warning("[Redis] 初始化失败，将使用降级模式")
        return False
