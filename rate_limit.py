# rate_limit.py — API 限流和用户配额管理
"""API 限流和用户配额管理

特性：
1. 基于 IP 的限流
2. 基于用户的限流
3. 用户配额管理
4. 分布式限流（Redis）
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 限流配置
# ══════════════════════════════════════════════════════════════

# 默认限流配置
DEFAULT_RATE_LIMIT = int(os.environ.get("DEFAULT_RATE_LIMIT", 60))  # 每分钟请求数
DEFAULT_DAILY_QUOTA = int(os.environ.get("DEFAULT_DAILY_QUOTA", 50))  # 每日配额
DEFAULT_MONTHLY_QUOTA = int(os.environ.get("DEFAULT_MONTHLY_QUOTA", 1000))  # 每月配额

# 限流键前缀
RATE_LIMIT_PREFIX = "ratelimit:"
QUOTA_PREFIX = "quota:"


# ══════════════════════════════════════════════════════════════
# Redis 客户端
# ══════════════════════════════════════════════════════════════

from typing import Any

def _get_redis_client():
    """获取 Redis 客户端"""
    if os.environ.get("REDIS_URL"):
        from redis_client import get_redis
        return get_redis()
    return None


# ══════════════════════════════════════════════════════════════
# 滑动窗口限流核心实现
# ══════════════════════════════════════════════════════════════

def _sliding_window_check(
    key: str,
    limit: int,
    window: int
) -> tuple[bool, dict]:
    """滑动窗口限流检查（核心实现）

    使用 Redis pipeline 优化性能，减少网络往返。

    Args:
        key: Redis 键
        limit: 时间窗口内最大请求数
        window: 时间窗口（秒）

    Returns:
        (是否允许, 限流信息)
    """
    client = _get_redis_client()
    if not client:
        return True, {"limit": limit, "remaining": limit, "reset": time.time() + window}

    try:
        now = time.time()
        window_start = now - window

        # 使用 pipeline 减少网络往返
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        results = pipe.execute()

        count = results[1]

        if count >= limit:
            # 计算重置时间
            oldest = client.zrange(key, 0, 0, withscores=True)
            reset_time = oldest[0][1] + window if oldest else now + window

            return False, {
                "limit": limit,
                "remaining": 0,
                "reset": reset_time,
                "retry_after": int(reset_time - now),
            }

        # 添加新请求
        client.zadd(key, {str(now): now})
        client.expire(key, window)

        return True, {
            "limit": limit,
            "remaining": limit - count - 1,
            "reset": now + window,
        }

    except Exception as e:
        logger.warning(f"[RateLimit] 滑动窗口检查失败: {e}")
        # 降级策略：Redis 故障时允许通过（可根据业务需求改为拒绝）
        return True, {"limit": limit, "remaining": limit, "reset": time.time() + window, "degraded": True}


# ══════════════════════════════════════════════════════════════
# 基于 IP 的限流
# ══════════════════════════════════════════════════════════════

def get_client_ip(request: Any) -> str:
    """获取客户端 IP 地址

    Args:
        request: FastAPI Request 对象

    Returns:
        客户端 IP 地址

    Note:
        在生产环境中，应验证代理服务器 IP 以防止 IP 伪造。
        可通过 TRUSTED_PROXY_IPS 环境变量配置受信任的代理列表。
    """
    # 检查代理头（仅在信任代理的情况下）
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # 取第一个 IP（最左边的原始客户端 IP）
        # 警告：此 IP 可能被伪造，生产环境应验证代理
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # 直接连接
    if hasattr(request, 'client') and request.client:
        return request.client.host

    return "unknown"


def check_rate_limit_ip(
    ip: str,
    limit: int = DEFAULT_RATE_LIMIT,
    window: int = 60
) -> tuple[bool, dict]:
    """检查 IP 限流

    使用滑动窗口算法实现精确的限流控制。

    Args:
        ip: 客户端 IP
        limit: 时间窗口内最大请求数
        window: 时间窗口（秒）

    Returns:
        (是否允许, 限流信息)
    """
    key = f"{RATE_LIMIT_PREFIX}ip:{ip}"
    return _sliding_window_check(key, limit, window)


# ══════════════════════════════════════════════════════════════
# 基于用户的限流
# ══════════════════════════════════════════════════════════════

def check_rate_limit_user(
    user_id: str,
    limit: int = DEFAULT_RATE_LIMIT,
    window: int = 60
) -> tuple[bool, dict]:
    """检查用户限流

    使用滑动窗口算法实现精确的限流控制。

    Args:
        user_id: 用户 ID
        limit: 时间窗口内最大请求数
        window: 时间窗口（秒）

    Returns:
        (是否允许, 限流信息)
    """
    key = f"{RATE_LIMIT_PREFIX}user:{user_id}"
    return _sliding_window_check(key, limit, window)


# ══════════════════════════════════════════════════════════════
# 用户配额管理
# ══════════════════════════════════════════════════════════════

def check_user_quota(user_id: str) -> tuple[bool, dict]:
    """检查用户配额

    Args:
        user_id: 用户 ID

    Returns:
        (是否允许, 配额信息)
    """
    if not user_id:
        return True, {"quota": "unlimited"}

    # 优先使用数据库
    if os.environ.get("DATABASE_URL"):
        try:
            from models import check_user_quota as db_check_quota

            if not db_check_quota(user_id):
                return False, {
                    "quota": "exceeded",
                    "message": "用户配额已用尽",
                }

            from models import get_user_quota_info
            quota_info = get_user_quota_info(user_id)
            return True, quota_info

        except Exception as e:
            logger.warning(f"[Quota] 数据库检查失败: {e}")

    # 使用 Redis 作为备选
    return _check_quota_redis(user_id)


def _check_quota_redis(user_id: str) -> tuple[bool, dict]:
    """使用 Redis 检查配额"""
    client = _get_redis_client()
    if not client:
        return True, {"quota": "unlimited"}

    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")

    daily_key = f"{QUOTA_PREFIX}{user_id}:daily:{today}"
    monthly_key = f"{QUOTA_PREFIX}{user_id}:monthly:{month}"

    try:
        daily_used = int(client.get(daily_key) or 0)
        monthly_used = int(client.get(monthly_key) or 0)

        if daily_used >= DEFAULT_DAILY_QUOTA:
            return False, {
                "quota": "daily_exceeded",
                "daily_used": daily_used,
                "daily_limit": DEFAULT_DAILY_QUOTA,
                "message": "每日配额已用尽",
            }

        if monthly_used >= DEFAULT_MONTHLY_QUOTA:
            return False, {
                "quota": "monthly_exceeded",
                "monthly_used": monthly_used,
                "monthly_limit": DEFAULT_MONTHLY_QUOTA,
                "message": "每月配额已用尽",
            }

        return True, {
            "daily_used": daily_used,
            "daily_limit": DEFAULT_DAILY_QUOTA,
            "monthly_used": monthly_used,
            "monthly_limit": DEFAULT_MONTHLY_QUOTA,
        }

    except Exception as e:
        logger.warning(f"[Quota] Redis 检查失败: {e}")
        return True, {"quota": "error", "message": str(e)}


def increment_quota_usage(user_id: str):
    """增加用户使用量"""
    if not user_id:
        return

    client = _get_redis_client()
    if not client:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")

    daily_key = f"{QUOTA_PREFIX}{user_id}:daily:{today}"
    monthly_key = f"{QUOTA_PREFIX}{user_id}:monthly:{month}"

    try:
        # 增加计数
        client.incr(daily_key)
        client.incr(monthly_key)

        # 设置过期时间
        client.expire(daily_key, 86400)  # 1 天
        client.expire(monthly_key, 2592000)  # 30 天

    except Exception as e:
        logger.warning(f"[Quota] 增加使用量失败: {e}")


# ══════════════════════════════════════════════════════════════
# 全局限流（API 级别）
# ══════════════════════════════════════════════════════════════

def check_global_rate_limit(limit: int = 1000, window: int = 60) -> bool:
    """检查全局限流（保护系统）"""
    client = _get_redis_client()
    if not client:
        return True

    key = f"{RATE_LIMIT_PREFIX}global"

    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, window)

        return count <= limit

    except Exception as e:
        logger.warning(f"[RateLimit] 全局限流检查失败: {e}")
        return True


# ══════════════════════════════════════════════════════════════
# FastAPI 依赖
# ══════════════════════════════════════════════════════════════

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse


class RateLimitMiddleware:
    """限流中间件"""

    def __init__(self, app, rate_limit: int = DEFAULT_RATE_LIMIT):
        self.app = app
        self.rate_limit = rate_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # 跳过健康检查
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            await self.app(scope, receive, send)
            return

        # 检查 IP 限流
        ip = get_client_ip(request)
        allowed, info = check_rate_limit_ip(ip, self.rate_limit)

        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"请求过于频繁，请 {info.get('retry_after', 60)} 秒后重试",
                    "retry_after": info.get("retry_after", 60),
                },
                headers={
                    "Retry-After": str(info.get("retry_after", 60)),
                    "X-RateLimit-Limit": str(info.get("limit", self.rate_limit)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(info.get("reset", time.time() + 60))),
                }
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


async def check_rate_limit_dependency(request: Request):
    """FastAPI 限流依赖"""
    ip = get_client_ip(request)
    allowed, info = check_rate_limit_ip(ip)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Too Many Requests",
                "message": f"请求过于频繁，请 {info.get('retry_after', 60)} 秒后重试",
                "retry_after": info.get("retry_after", 60),
            },
            headers={
                "Retry-After": str(info.get("retry_after", 60)),
            }
        )

    return info


async def check_quota_dependency(request: Request, user_id: str = None):
    """FastAPI 配额依赖"""
    if not user_id:
        # 尝试从请求中获取用户 ID
        user_id = request.headers.get("X-User-ID")

    if user_id:
        allowed, info = check_user_quota(user_id)

        if not allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Quota Exceeded",
                    "message": info.get("message", "用户配额已用尽"),
                    **info
                }
            )

        return info

    return {"quota": "unlimited"}


# ══════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════

def get_user_quota_info(user_id: str) -> dict:
    """获取用户配额信息（从数据库）"""
    if os.environ.get("DATABASE_URL"):
        try:
            from database import get_db
            from models import UserQuota
            from sqlalchemy.orm import Session

            with get_db() as db:
                quota = db.query(UserQuota).filter(
                    UserQuota.user_id == user_id
                ).first()

                if quota:
                    return {
                        "user_id": user_id,
                        "daily_used": quota.daily_used,
                        "daily_limit": quota.daily_limit,
                        "monthly_used": quota.monthly_used,
                        "monthly_limit": quota.monthly_limit,
                        "total_reports": quota.total_reports,
                        "is_active": quota.is_active,
                    }
        except Exception as e:
            logger.warning(f"[Quota] 获取配额信息失败: {e}")

    return {"quota": "unknown"}


def reset_user_quota(user_id: str, quota_type: str = "daily"):
    """重置用户配额"""
    if os.environ.get("DATABASE_URL"):
        try:
            from models import update_user_quota_reset
            update_user_quota_reset(user_id, quota_type)
        except Exception as e:
            logger.warning(f"[Quota] 重置配额失败: {e}")

    # 同时重置 Redis
    client = _get_redis_client()
    if client:
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        if quota_type == "daily":
            key = f"{QUOTA_PREFIX}{user_id}:daily:{today}"
            client.delete(key)
        elif quota_type == "monthly":
            key = f"{QUOTA_PREFIX}{user_id}:monthly:{month}"
            client.delete(key)
