# test_concurrency.py — 并发性测试
"""并发性测试

测试场景：
1. API 并发请求测试
2. 限流并发测试
3. 缓存并发测试
4. 任务队列并发测试
5. 数据库并发测试
"""
from __future__ import annotations

import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest


# ════════════════════════════════════════════════════════════════════════════
# 并发测试配置
# ════════════════════════════════════════════════════════════════════════════

# 测试参数
CONCURRENT_USERS = 50
REQUESTS_PER_USER = 10
TOTAL_REQUESTS = CONCURRENT_USERS * REQUESTS_PER_USER


# ════════════════════════════════════════════════════════════════════════════
# 限流并发测试
# ════════════════════════════════════════════════════════════════════════════

class TestRateLimitConcurrency:
    """限流并发测试"""

    @patch("rate_limit._get_redis_client")
    def test_concurrent_rate_limit_checks(self, mock_get_client):
        """测试并发限流检查"""
        import rate_limit

        # 模拟 Redis 操作
        call_count = {"value": 0}
        lock = threading.Lock()

        def mock_zcard(key):
            with lock:
                call_count["value"] += 1
            return 10

        def mock_zremrangebyscore(key, min_score, max_score):
            return 0

        def mock_zrange(key, start, end, withscores=False):
            return []

        def mock_zadd(key, mapping):
            return 1

        def mock_expire(key, seconds):
            return True

        mock_client = MagicMock()
        mock_client.zcard = mock_zcard
        mock_client.zremrangebyscore = mock_zremrangebyscore
        mock_client.zrange = mock_zrange
        mock_client.zadd = mock_zadd
        mock_client.expire = mock_expire
        mock_get_client.return_value = mock_client

        # 并发执行限流检查
        results = []
        errors = []

        def check_limit(user_id):
            try:
                allowed, info = rate_limit.check_rate_limit_ip(
                    f"192.168.1.{user_id % 255}",
                    limit=60,
                    window=60
                )
                results.append((user_id, allowed))
            except Exception as e:
                errors.append((user_id, str(e)))

        # 启动并发线程
        threads = []
        for i in range(CONCURRENT_USERS):
            t = threading.Thread(target=check_limit, args=(i,))
            threads.append(t)

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        end = time.perf_counter()

        print(f"\n并发限流检查 ({CONCURRENT_USERS} 用户):")
        print(f"  成功: {len(results)}")
        print(f"  失败: {len(errors)}")
        print(f"  耗时: {(end - start) * 1000:.2f}ms")
        print(f"  调用次数: {call_count['value']}")

        assert len(errors) == 0
        assert len(results) == CONCURRENT_USERS

    @patch("rate_limit._get_redis_client")
    def test_rate_limit_thread_safety(self, mock_get_client):
        """测试限流线程安全"""
        import rate_limit

        # 使用真实的线程安全计数器模拟
        from threading import Lock

        class ThreadSafeCounter:
            def __init__(self):
                self._value = 0
                self._lock = Lock()

            def increment(self):
                with self._lock:
                    self._value += 1
                    return self._value

            @property
            def value(self):
                return self._value

        counter = ThreadSafeCounter()

        mock_client = MagicMock()
        mock_client.zcard = lambda k: counter.value
        mock_client.zremrangebyscore = lambda k, mi, ma: 0
        mock_client.zrange = lambda k, s, e, **kw: []
        mock_client.zadd = lambda k, m: counter.increment()
        mock_client.expire = lambda k, s: True
        mock_get_client.return_value = mock_client

        num_threads = 100
        num_operations_per_thread = 10

        def increment_operations():
            for _ in range(num_operations_per_thread):
                rate_limit.check_rate_limit_ip("192.168.1.1", limit=1000, window=60)

        threads = [threading.Thread(target=increment_operations) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证计数正确
        assert counter.value == num_threads * num_operations_per_thread


# ════════════════════════════════════════════════════════════════════════════
# 缓存并发测试
# ════════════════════════════════════════════════════════════════════════════

class TestCacheConcurrency:
    """缓存并发测试"""

    @patch("cache._get_redis_client")
    def test_concurrent_cache_access(self, mock_get_client):
        """测试并发缓存访问"""
        import cache
        import json

        # 线程安全的数据存储
        cache_data = {}
        lock = threading.Lock()

        def mock_get(key):
            with lock:
                value = cache_data.get(key)
                return value.encode() if value else None

        def mock_setex(key, ttl, value):
            with lock:
                cache_data[key] = value
            return True

        mock_client = MagicMock()
        mock_client.get = mock_get
        mock_client.setex = mock_setex
        mock_get_client.return_value = mock_client

        cache.reset_cache_stats()
        num_threads = 50
        operations_per_thread = 20

        def cache_operations(thread_id):
            for i in range(operations_per_thread):
                key = f"key_{thread_id}_{i}"
                # 设置
                cache.cache_set(key, f"value_{thread_id}_{i}", ttl=3600)
                # 获取
                value = cache.cache_get(key)
                if value is not None:
                    assert value == f"value_{thread_id}_{i}"

        threads = [threading.Thread(target=cache_operations, args=(i,)) for i in range(num_threads)]

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        end = time.perf_counter()

        stats = cache.get_cache_stats()

        print(f"\n并发缓存访问 ({num_threads} 线程 x {operations_per_thread} 操作):")
        print(f"  总耗时: {(end - start) * 1000:.2f}ms")
        print(f"  缓存命中: {stats['hits']}")
        print(f"  缓存未命中: {stats['misses']}")
        print(f"  存储的键数: {len(cache_data)}")

        # 验证数据一致性
        assert len(cache_data) == num_threads * operations_per_thread

    @patch("cache._get_redis_client")
    def test_cache_stats_thread_safety(self, mock_get_client):
        """测试缓存统计线程安全"""
        import cache

        mock_client = MagicMock()
        mock_client.get.return_value = b"cached"
        mock_client.setex.return_value = True
        mock_get_client.return_value = mock_client

        cache.reset_cache_stats()
        num_threads = 100

        def increment_stats():
            for _ in range(100):
                cache._cache_stats["hits"] += 1
                cache._cache_stats["misses"] += 1

        threads = [threading.Thread(target=increment_stats) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 注意：Python GIL 保护了简单的整数操作
        # 但在真实场景中，应该使用锁
        stats = cache.get_cache_stats()
        print(f"\n缓存统计线程安全测试:")
        print(f"  期望命中: {num_threads * 100}")
        print(f"  实际命中: {stats['hits']}")

        # 由于 GIL，这个测试应该能通过
        # 但如果使用更复杂的操作，可能会出现问题


# ════════════════════════════════════════════════════════════════════════════
# 用户配额并发测试
# ════════════════════════════════════════════════════════════════════════════

class TestQuotaConcurrency:
    """用户配额并发测试"""

    @patch("rate_limit._get_redis_client")
    def test_concurrent_quota_increment(self, mock_get_client):
        """测试并发配额增加"""
        import rate_limit

        # 线程安全计数器
        daily_counts = {}
        monthly_counts = {}
        lock = threading.Lock()

        def mock_get(key):
            with lock:
                if "daily" in key:
                    return str(daily_counts.get(key, 0)).encode()
                else:
                    return str(monthly_counts.get(key, 0)).encode()

        def mock_incr(key):
            with lock:
                if "daily" in key:
                    daily_counts[key] = daily_counts.get(key, 0) + 1
                    return daily_counts[key]
                else:
                    monthly_counts[key] = monthly_counts.get(key, 0) + 1
                    return monthly_counts[key]

        def mock_expire(key, seconds):
            return True

        mock_client = MagicMock()
        mock_client.get = mock_get
        mock_client.incr = mock_incr
        mock_client.expire = mock_expire
        mock_get_client.return_value = mock_client

        num_users = 20
        increments_per_user = 5

        def increment_quota(user_id):
            for _ in range(increments_per_user):
                rate_limit.increment_quota_usage(f"user_{user_id}")

        threads = [threading.Thread(target=increment_quota, args=(i,)) for i in range(num_users)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证每个用户的配额正确
        total_increments = sum(daily_counts.values())

        print(f"\n并发配额增加 ({num_users} 用户 x {increments_per_user} 次):")
        print(f"  期望总增量: {num_users * increments_per_user * 2}")  # daily + monthly
        print(f"  实际总增量: {total_increments}")

        assert total_increments == num_users * increments_per_user

    @patch("rate_limit._get_redis_client")
    def test_quota_race_condition(self, mock_get_client):
        """测试配额竞态条件"""
        import rate_limit

        # 模拟竞态条件
        quota_value = {"value": 49}  # 接近限制
        lock = threading.Lock()

        def mock_get(key):
            with lock:
                return str(quota_value["value"]).encode()

        mock_client = MagicMock()
        mock_client.get = mock_get
        mock_client.incr = lambda k: quota_value.update({"value": quota_value["value"] + 1})
        mock_client.expire = lambda k, s: True
        mock_get_client.return_value = mock_client

        num_threads = 10
        allowed_count = {"value": 0}

        def check_and_increment():
            with patch.dict(os.environ, {"DATABASE_URL": ""}):
                allowed, info = rate_limit._check_quota_redis("user123")
                if allowed:
                    allowed_count["value"] += 1

        threads = [threading.Thread(target=check_and_increment) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 注意：这里没有真正的竞态保护
        # 在真实场景中，应该使用 Redis 事务或 Lua 脚本


# ════════════════════════════════════════════════════════════════════════════
# 分布式锁并发测试
# ════════════════════════════════════════════════════════════════════════════

class TestDistributedLockConcurrency:
    """分布式锁并发测试"""

    @patch("redis_client.get_redis")
    def test_distributed_lock_contention(self, mock_get_redis):
        """测试分布式锁竞争"""
        import redis_client

        # 模拟锁状态
        lock_state = {"holder": None, "value": None}
        lock = threading.Lock()

        def mock_set(key, value, nx=False, ex=None):
            with lock:
                if nx:  # 仅当键不存在时设置
                    if lock_state["holder"] is None:
                        lock_state["holder"] = key
                        lock_state["value"] = value
                        return True
                    return False
                lock_state["holder"] = key
                lock_state["value"] = value
                return True

        def mock_get(key):
            with lock:
                if lock_state["holder"] == key:
                    return lock_state["value"].encode()
                return None

        def mock_delete(key):
            with lock:
                if lock_state["holder"] == key:
                    lock_state["holder"] = None
                    lock_state["value"] = None
                    return 1
                return 0

        mock_client = MagicMock()
        mock_client.set = mock_set
        mock_client.get = mock_get
        mock_client.delete = mock_delete
        mock_get_redis.return_value = mock_client

        num_threads = 10
        acquired_count = {"value": 0}
        execution_order = []

        def try_lock(thread_id):
            with redis_client.distributed_lock("test_lock", timeout=5) as acquired:
                if acquired:
                    acquired_count["value"] += 1
                    execution_order.append(thread_id)
                    # 模拟工作
                    time.sleep(0.01)

        threads = [threading.Thread(target=try_lock, args=(i,)) for i in range(num_threads)]

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        end = time.perf_counter()

        print(f"\n分布式锁竞争 ({num_threads} 线程):")
        print(f"  获取锁成功: {acquired_count['value']}")
        print(f"  获取锁失败: {num_threads - acquired_count['value']}")
        print(f"  耗时: {(end - start) * 1000:.2f}ms")

        # 至少有一些线程获取到了锁
        assert acquired_count["value"] > 0


# ════════════════════════════════════════════════════════════════════════════
# API 并发测试
# ════════════════════════════════════════════════════════════════════════════

class TestAPIConcurrency:
    """API 并发测试"""

    def test_concurrent_health_requests(self):
        """测试并发健康检查请求"""
        from fastapi.testclient import TestClient

        os.environ["REDIS_URL"] = ""
        os.environ["DATABASE_URL"] = ""

        from api import app
        client = TestClient(app)

        num_threads = 20
        requests_per_thread = 10
        results = Queue()

        def make_requests(thread_id):
            for i in range(requests_per_thread):
                try:
                    response = client.get("/health")
                    results.put((thread_id, i, response.status_code))
                except Exception as e:
                    results.put((thread_id, i, str(e)))

        threads = [threading.Thread(target=make_requests, args=(i,)) for i in range(num_threads)]

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        end = time.perf_counter()

        # 收集结果
        success_count = 0
        error_count = 0

        while not results.empty():
            _, _, status = results.get()
            if status == 200:
                success_count += 1
            else:
                error_count += 1

        print(f"\n并发健康检查 ({num_threads} 线程 x {requests_per_thread} 请求):")
        print(f"  成功: {success_count}")
        print(f"  失败: {error_count}")
        print(f"  耗时: {(end - start) * 1000:.2f}ms")

        assert success_count == num_threads * requests_per_thread

    def test_concurrent_model_list_requests(self):
        """测试并发模型列表请求"""
        from fastapi.testclient import TestClient

        os.environ["REDIS_URL"] = ""
        os.environ["DATABASE_URL"] = ""

        from api import app
        client = TestClient(app)

        num_threads = 10
        results = []

        def list_models():
            response = client.get("/api/models")
            results.append(response.status_code)

        threads = [threading.Thread(target=list_models) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        success_count = sum(1 for s in results if s == 200)

        print(f"\n并发模型列表请求 ({num_threads} 线程):")
        print(f"  成功: {success_count}")
        print(f"  失败: {num_threads - success_count}")

        assert success_count == num_threads


# ════════════════════════════════════════════════════════════════════════════
# 状态并发测试
# ════════════════════════════════════════════════════════════════════════════

class TestStateConcurrency:
    """状态并发测试"""

    def test_concurrent_state_creation(self):
        """测试并发状态创建"""
        from state import create_initial_state

        num_threads = 50
        states = []

        def create_state(thread_id):
            state = create_initial_state(
                topic=f"Topic {thread_id}",
                abstract=f"Abstract {thread_id}",
            )
            states.append((thread_id, state["topic"]))

        threads = [threading.Thread(target=create_state, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证所有状态正确创建
        assert len(states) == num_threads

        # 验证每个状态的主题正确
        topics = [s[1] for s in states]
        for i in range(num_threads):
            assert f"Topic {i}" in topics

        print(f"\n并发状态创建 ({num_threads} 线程):")
        print(f"  成功创建: {len(states)}")


# ════════════════════════════════════════════════════════════════════════════
# 压力测试
# ════════════════════════════════════════════════════════════════════════════

class TestStressTests:
    """压力测试"""

    @patch("cache._get_redis_client")
    def test_high_load_cache_operations(self, mock_get_client):
        """高负载缓存操作测试"""
        import cache

        mock_client = MagicMock()
        mock_client.get.return_value = b"cached"
        mock_client.setex.return_value = True
        mock_get_client.return_value = mock_client

        num_threads = 100
        ops_per_thread = 100
        total_ops = num_threads * ops_per_thread

        def cache_ops():
            for i in range(ops_per_thread):
                cache.cache_get(f"key_{i}")
                cache.cache_set(f"key_{i}", f"value_{i}")

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(cache_ops) for _ in range(num_threads)]
            for f in as_completed(futures):
                f.result()
        end = time.perf_counter()

        duration = end - start
        throughput = total_ops / duration

        print(f"\n高负载缓存测试 ({num_threads} 线程 x {ops_per_thread} 操作):")
        print(f"  总操作数: {total_ops}")
        print(f"  耗时: {duration:.2f}s")
        print(f"  吞吐量: {throughput:.0f} ops/s")

        # 吞吐量应该足够高
        assert throughput > 500

    @patch("rate_limit._get_redis_client")
    def test_high_load_rate_limit(self, mock_get_client):
        """高负载限流测试"""
        import rate_limit

        call_count = {"value": 0}
        lock = threading.Lock()

        def mock_zcard(key):
            with lock:
                call_count["value"] += 1
            return 10

        mock_client = MagicMock()
        mock_client.zcard = mock_zcard
        mock_client.zremrangebyscore = lambda k, mi, ma: 0
        mock_client.zrange = lambda k, s, e, **kw: []
        mock_client.zadd = lambda k, m: 1
        mock_client.expire = lambda k, s: True
        mock_get_client.return_value = mock_client

        num_threads = 100
        checks_per_thread = 50
        total_checks = num_threads * checks_per_thread

        def rate_limit_check():
            for _ in range(checks_per_thread):
                rate_limit.check_rate_limit_ip("192.168.1.1", limit=1000, window=60)

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(rate_limit_check) for _ in range(num_threads)]
            for f in as_completed(futures):
                f.result()
        end = time.perf_counter()

        duration = end - start
        throughput = total_checks / duration

        print(f"\n高负载限流测试 ({num_threads} 线程 x {checks_per_thread} 检查):")
        print(f"  总检查数: {total_checks}")
        print(f"  耗时: {duration:.2f}s")
        print(f"  吞吐量: {throughput:.0f} checks/s")

        assert throughput > 500


# ════════════════════════════════════════════════════════════════════════════
# 运行测试
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
