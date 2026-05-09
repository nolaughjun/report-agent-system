# test_unit_scaling.py — 并发扩展模块单元测试
"""并发扩展模块单元测试

测试模块：
1. redis_client - Redis 连接和 Celery 配置
2. cache - 缓存层
3. rate_limit - API 限流
4. models - 数据库模型
5. database - 数据库连接
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Redis Client 单元测试
# ════════════════════════════════════════════════════════════════════════════

class TestRedisClient:
    """Redis 客户端测试"""

    def test_redis_url_default(self):
        """测试默认 Redis URL"""
        # 清除环境变量
        old_val = os.environ.pop("REDIS_URL", None)
        try:
            # 需要重新导入才能获取默认值
            import importlib
            import redis_client
            importlib.reload(redis_client)
            assert redis_client.REDIS_URL == "redis://localhost:6379/0"
        finally:
            if old_val:
                os.environ["REDIS_URL"] = old_val

    @patch("redis_client.redis.Redis")
    def test_get_redis_pool_singleton(self, mock_redis):
        """测试连接池单例模式"""
        import redis_client
        import importlib
        importlib.reload(redis_client)

        pool1 = redis_client.get_redis_pool()
        pool2 = redis_client.get_redis_pool()
        # 应该返回同一个实例
        assert pool1 is pool2

    @patch("redis_client.get_redis")
    def test_check_redis_connection_success(self, mock_get_redis):
        """测试 Redis 连接检查成功"""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_get_redis.return_value = mock_client

        import redis_client
        result = redis_client.check_redis_connection()
        assert result is True
        mock_client.ping.assert_called_once()

    @patch("redis_client.get_redis")
    def test_check_redis_connection_failure(self, mock_get_redis):
        """测试 Redis 连接检查失败"""
        mock_get_redis.side_effect = Exception("Connection refused")

        import redis_client
        result = redis_client.check_redis_connection()
        assert result is False

    @patch("redis_client.get_redis")
    def test_cache_get(self, mock_get_redis):
        """测试缓存获取"""
        mock_client = MagicMock()
        mock_client.get.return_value = b"test_value"
        mock_get_redis.return_value = mock_client

        import redis_client
        result = redis_client.cache_get("test_key")
        assert result == "test_value"

    @patch("redis_client.get_redis")
    def test_cache_set(self, mock_get_redis):
        """测试缓存设置"""
        mock_client = MagicMock()
        mock_client.setex.return_value = True
        mock_get_redis.return_value = mock_client

        import redis_client
        result = redis_client.cache_set("test_key", "test_value", ttl=3600)
        assert result is True
        mock_client.setex.assert_called_once_with("test_key", 3600, "test_value")

    @patch("redis_client.get_redis")
    def test_distributed_lock_acquire_success(self, mock_get_redis):
        """测试分布式锁获取成功"""
        mock_client = MagicMock()
        mock_client.set.return_value = True
        mock_get_redis.return_value = mock_client

        import redis_client
        with redis_client.distributed_lock("test_lock") as acquired:
            assert acquired is True

    @patch("redis_client.get_redis")
    def test_distributed_lock_acquire_failure(self, mock_get_redis):
        """测试分布式锁获取失败"""
        mock_client = MagicMock()
        mock_client.set.return_value = False
        mock_get_redis.return_value = mock_client

        import redis_client
        with redis_client.distributed_lock("test_lock") as acquired:
            assert acquired is False


# ════════════════════════════════════════════════════════════════════════════
# Cache 模块单元测试
# ════════════════════════════════════════════════════════════════════════════

class TestCache:
    """缓存模块测试"""

    def test_hash_key_consistency(self):
        """测试哈希键一致性"""
        import cache
        key1 = cache._hash_key("test content")
        key2 = cache._hash_key("test content")
        assert key1 == key2
        assert len(key1) == 32  # MD5 哈希长度

    def test_hash_key_different(self):
        """测试不同内容的哈希键不同"""
        import cache
        key1 = cache._hash_key("content 1")
        key2 = cache._hash_key("content 2")
        assert key1 != key2

    def test_get_search_cache_key_format(self):
        """测试搜索缓存键格式"""
        import cache
        key = cache.get_search_cache_key("test query", "tavily")
        assert key.startswith(cache.CACHE_PREFIX_SEARCH)
        assert len(key) == len(cache.CACHE_PREFIX_SEARCH) + 32

    def test_get_llm_cache_key_format(self):
        """测试 LLM 缓存键格式"""
        import cache
        messages = [{"role": "user", "content": "test"}]
        key = cache.get_llm_cache_key(messages, "deepseek-chat")
        assert key.startswith(cache.CACHE_PREFIX_LLM)
        assert len(key) == len(cache.CACHE_PREFIX_LLM) + 32

    def test_cache_stats_initialization(self):
        """测试缓存统计初始化"""
        import cache
        cache.reset_cache_stats()
        stats = cache.get_cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0

    def test_cache_stats_calculation(self):
        """测试缓存统计计算"""
        import cache
        cache.reset_cache_stats()
        cache._cache_stats["hits"] = 75
        cache._cache_stats["misses"] = 25
        stats = cache.get_cache_stats()
        assert stats["total_requests"] == 100
        assert stats["hit_rate"] == 0.75

    @patch("cache._get_redis_client")
    def test_cache_get_hit(self, mock_get_client):
        """测试缓存命中"""
        mock_client = MagicMock()
        mock_client.get.return_value = b'"cached_result"'
        mock_get_client.return_value = mock_client

        import cache
        cache.reset_cache_stats()
        result = cache.cache_get("test_key")
        assert result == '"cached_result"'
        assert cache._cache_stats["hits"] == 1

    @patch("cache._get_redis_client")
    def test_cache_get_miss(self, mock_get_client):
        """测试缓存未命中"""
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_get_client.return_value = mock_client

        import cache
        cache.reset_cache_stats()
        result = cache.cache_get("test_key")
        assert result is None
        assert cache._cache_stats["misses"] == 1

    @patch("cache._get_redis_client")
    def test_search_with_cache_hit(self, mock_get_client):
        """测试带缓存的搜索命中"""
        cached_results = [{"title": "Cached Result"}]
        mock_client = MagicMock()
        mock_client.get.return_value = json.dumps(cached_results).encode()
        mock_get_client.return_value = mock_client

        import cache
        cache.reset_cache_stats()
        results = cache.search_with_cache(
            query="test query",
            search_func=lambda q: [{"title": "New Result"}],
            source="tavily"
        )
        assert results == cached_results
        assert cache._cache_stats["search_hits"] == 1

    @patch("cache._get_redis_client")
    def test_search_with_cache_miss(self, mock_get_client):
        """测试带缓存的搜索未命中"""
        new_results = [{"title": "New Result"}]
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_client.setex.return_value = True
        mock_get_client.return_value = mock_client

        import cache
        cache.reset_cache_stats()
        results = cache.search_with_cache(
            query="test query",
            search_func=lambda q: new_results,
            source="tavily"
        )
        assert results == new_results
        assert cache._cache_stats["search_misses"] == 1


# ════════════════════════════════════════════════════════════════════════════
# Rate Limit 模块单元测试
# ════════════════════════════════════════════════════════════════════════════

class TestRateLimit:
    """限流模块测试"""

    def test_default_config(self):
        """测试默认配置"""
        import rate_limit
        assert rate_limit.DEFAULT_RATE_LIMIT == 60
        assert rate_limit.DEFAULT_DAILY_QUOTA == 50
        assert rate_limit.DEFAULT_MONTHLY_QUOTA == 1000

    def test_get_client_ip_direct(self):
        """测试直接获取客户端 IP"""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.1"

        import rate_limit
        ip = rate_limit.get_client_ip(mock_request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_forwarded(self):
        """测试通过代理头获取 IP"""
        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        mock_request.client = None

        import rate_limit
        ip = rate_limit.get_client_ip(mock_request)
        assert ip == "10.0.0.1"

    def test_get_client_ip_real_ip(self):
        """测试通过 X-Real-IP 获取 IP"""
        mock_request = MagicMock()
        mock_request.headers = {"X-Real-IP": "10.0.0.2"}
        mock_request.client = None

        import rate_limit
        ip = rate_limit.get_client_ip(mock_request)
        assert ip == "10.0.0.2"

    @patch("rate_limit._get_redis_client")
    def test_check_rate_limit_ip_allowed(self, mock_get_client):
        """测试 IP 限流允许"""
        mock_client = MagicMock()
        mock_client.zcard.return_value = 10  # 当前 10 个请求
        mock_client.zrange.return_value = []
        mock_get_client.return_value = mock_client

        import rate_limit
        allowed, info = rate_limit.check_rate_limit_ip("192.168.1.1", limit=60, window=60)
        assert allowed is True
        assert info["remaining"] == 49  # 60 - 10 - 1

    @patch("rate_limit._get_redis_client")
    def test_check_rate_limit_ip_blocked(self, mock_get_client):
        """测试 IP 限流阻止"""
        mock_client = MagicMock()
        mock_client.zcard.return_value = 60  # 已达限制
        mock_client.zrange.return_value = [(b"1234567890.0", 1234567890.0)]
        mock_get_client.return_value = mock_client

        import rate_limit
        allowed, info = rate_limit.check_rate_limit_ip("192.168.1.1", limit=60, window=60)
        assert allowed is False
        assert info["remaining"] == 0
        assert "retry_after" in info

    @patch("rate_limit._get_redis_client")
    def test_check_rate_limit_ip_no_redis(self, mock_get_client):
        """测试无 Redis 时限流降级"""
        mock_get_client.return_value = None

        import rate_limit
        allowed, info = rate_limit.check_rate_limit_ip("192.168.1.1", limit=60, window=60)
        assert allowed is True  # 无 Redis 时允许通过

    @patch("rate_limit._get_redis_client")
    def test_check_user_quota_allowed(self, mock_get_client):
        """测试用户配额检查允许"""
        mock_client = MagicMock()
        mock_client.get.return_value = b"25"  # 已使用 25 次
        mock_get_client.return_value = mock_client

        import rate_limit
        # 不使用数据库
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            allowed, info = rate_limit._check_quota_redis("user123")
        assert allowed is True
        assert info["daily_used"] == 25

    @patch("rate_limit._get_redis_client")
    def test_check_user_quota_exceeded_daily(self, mock_get_client):
        """测试用户每日配额超限"""
        mock_client = MagicMock()
        mock_client.get.return_value = b"50"  # 已用尽
        mock_get_client.return_value = mock_client

        import rate_limit
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            allowed, info = rate_limit._check_quota_redis("user123")
        assert allowed is False
        assert info["quota"] == "daily_exceeded"

    @patch("rate_limit._get_redis_client")
    def test_increment_quota_usage(self, mock_get_client):
        """测试增加用户使用量"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        import rate_limit
        rate_limit.increment_quota_usage("user123")
        # 应该调用两次 incr（每日和每月）
        assert mock_client.incr.call_count == 2

    @patch("rate_limit._get_redis_client")
    def test_global_rate_limit(self, mock_get_client):
        """测试全局限流"""
        mock_client = MagicMock()
        mock_client.incr.return_value = 500
        mock_get_client.return_value = mock_client

        import rate_limit
        result = rate_limit.check_global_rate_limit(limit=1000, window=60)
        assert result is True

        mock_client.incr.return_value = 1500
        result = rate_limit.check_global_rate_limit(limit=1000, window=60)
        assert result is False


# ════════════════════════════════════════════════════════════════════════════
# Models 单元测试
# ════════════════════════════════════════════════════════════════════════════

class TestModels:
    """数据库模型测试"""

    def test_report_task_to_dict(self):
        """测试 ReportTask 模型转换为字典"""
        from models import ReportTask

        task = ReportTask(
            thread_id="test123",
            topic="Test Topic",
            report_type="research",
            status="pending",
            current_step="init",
            progress=0.0,
            retry_count=0,
        )

        result = task.to_dict()
        assert result["thread_id"] == "test123"
        assert result["topic"] == "Test Topic"
        assert result["status"] == "pending"

    def test_user_quota_can_create_report(self):
        """测试 UserQuota 配额检查"""
        from models import UserQuota

        # 配额充足
        quota = UserQuota(
            user_id="user123",
            daily_used=25,
            daily_limit=50,
            monthly_used=100,
            monthly_limit=1000,
            is_active=True,
        )
        assert quota.can_create_report() is True

        # 每日配额用尽
        quota.daily_used = 50
        assert quota.can_create_report() is False

        # 每月配额用尽
        quota.daily_used = 25
        quota.monthly_used = 1000
        assert quota.can_create_report() is False

        # 账户禁用
        quota.monthly_used = 100
        quota.is_active = False
        assert quota.can_create_report() is False

    def test_user_quota_increment_usage(self):
        """测试 UserQuota 使用量增加"""
        from models import UserQuota

        quota = UserQuota(
            user_id="user123",
            daily_used=10,
            monthly_used=100,
            total_reports=50,
        )

        old_updated = quota.updated_at
        quota.increment_usage()

        assert quota.daily_used == 11
        assert quota.monthly_used == 101
        assert quota.total_reports == 51

    def test_user_quota_reset_daily(self):
        """测试每日配额重置"""
        from models import UserQuota

        quota = UserQuota(
            user_id="user123",
            daily_used=50,
        )

        quota.reset_daily()
        assert quota.daily_used == 0
        assert quota.last_daily_reset is not None

    def test_user_quota_reset_monthly(self):
        """测试每月配额重置"""
        from models import UserQuota

        quota = UserQuota(
            user_id="user123",
            monthly_used=1000,
        )

        quota.reset_monthly()
        assert quota.monthly_used == 0
        assert quota.last_monthly_reset is not None


# ════════════════════════════════════════════════════════════════════════════
# Database 单元测试
# ════════════════════════════════════════════════════════════════════════════

class TestDatabase:
    """数据库连接测试"""

    def test_database_url_default(self):
        """测试默认数据库 URL"""
        old_val = os.environ.pop("DATABASE_URL", None)
        try:
            import importlib
            import database
            importlib.reload(database)
            assert "report_db" in database.DATABASE_URL
        finally:
            if old_val:
                os.environ["DATABASE_URL"] = old_val

    def test_async_database_url_conversion(self):
        """测试异步数据库 URL 转换"""
        import database
        assert "asyncpg" in database.ASYNC_DATABASE_URL

    @patch("database.engine.connect")
    def test_check_database_connection_success(self, mock_connect):
        """测试数据库连接检查成功"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value = None
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        import database
        result = database.check_database_connection()
        assert result is True

    @patch("database.engine.connect")
    def test_check_database_connection_failure(self, mock_connect):
        """测试数据库连接检查失败"""
        mock_connect.side_effect = Exception("Connection refused")

        import database
        result = database.check_database_connection()
        assert result is False


# ════════════════════════════════════════════════════════════════════════════
# State 单元测试
# ════════════════════════════════════════════════════════════════════════════

class TestState:
    """状态定义测试"""

    def test_create_initial_state(self):
        """测试创建初始状态"""
        from state import create_initial_state

        state = create_initial_state(
            topic="Test Topic",
            abstract="Test Abstract",
            report_type="research",
            language="中文",
            quality_threshold=0.7,
            max_retry=5,
            max_concurrent=10,
        )

        assert state["topic"] == "Test Topic"
        assert state["abstract"] == "Test Abstract"
        assert state["report_type"] == "research"
        assert state["language"] == "中文"
        assert state["quality_threshold"] == 0.7
        assert state["max_retry"] == 5
        assert state["max_concurrent"] == 10
        assert state["current_step"] == "init"
        assert state["retry_count"] == 0
        assert state["research_sources"] == []
        assert state["quality_checks"] == []

    def test_create_schedule_config(self):
        """测试创建定时执行配置"""
        from state import create_schedule_config

        schedule = create_schedule_config(
            scheduled_time="2024-12-25T10:00:00",
            recurrence="daily",
            timezone="Asia/Shanghai",
        )

        assert schedule["enabled"] is True
        assert schedule["scheduled_time"] == "2024-12-25T10:00:00"
        assert schedule["recurrence"] == "daily"
        assert schedule["timezone"] == "Asia/Shanghai"
        assert schedule["last_run"] is None

    def test_append_item_reducer(self):
        """测试列表追加 reducer"""
        from state import append_item

        # 追加单个元素
        result = append_item([1, 2], 3)
        assert result == [1, 2, 3]

        # 追加列表
        result = append_item([1, 2], [3, 4])
        assert result == [1, 2, 3, 4]

        # 空列表
        result = append_item(None, [1, 2])
        assert result == [1, 2]

        # None 追加
        result = append_item([1, 2], None)
        assert result == [1, 2]


# ════════════════════════════════════════════════════════════════════════════
# 运行测试
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
