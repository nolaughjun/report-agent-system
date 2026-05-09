# test_performance.py — 性能测试
"""性能测试

测试场景：
1. API 响应时间测试
2. 缓存性能测试
3. 限流性能测试
4. 数据库操作性能测试
5. 并发处理性能测试
"""
from __future__ import annotations

import os
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ════════════════════════════════════════════════════════════════════════════
# 测试配置
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def test_client():
    """创建测试客户端"""
    os.environ["REDIS_URL"] = ""
    os.environ["DATABASE_URL"] = ""

    from api import app
    return TestClient(app)


# 性能基准（毫秒）
PERFORMANCE_BENCHMARKS = {
    "health_check_p50": 50,  # 健康检查 P50 延迟
    "health_check_p99": 100,  # 健康检查 P99 延迟
    "api_response_p50": 200,  # API 响应 P50
    "api_response_p99": 500,  # API 响应 P99
    "cache_get": 5,  # 缓存获取
    "cache_set": 10,  # 缓存设置
    "rate_limit_check": 10,  # 限流检查
}


def measure_response_times(func, iterations=100):
    """测量响应时间

    Args:
        func: 要测试的函数
        iterations: 迭代次数

    Returns:
        dict: 包含 P50, P95, P99 延迟
    """
    times = []

    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # 转换为毫秒

    times.sort()

    return {
        "min": times[0],
        "max": times[-1],
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "p50": times[int(len(times) * 0.50)],
        "p95": times[int(len(times) * 0.95)],
        "p99": times[int(len(times) * 0.99)],
        "stddev": statistics.stdev(times) if len(times) > 1 else 0,
    }


# ════════════════════════════════════════════════════════════════════════════
# API 响应时间测试
# ════════════════════════════════════════════════════════════════════════════

class TestAPIPerformance:
    """API 性能测试"""

    def test_health_check_performance(self, test_client):
        """测试健康检查端点性能"""
        def make_request():
            return test_client.get("/health")

        metrics = measure_response_times(make_request, iterations=50)

        print(f"\n健康检查性能:")
        print(f"  P50: {metrics['p50']:.2f}ms")
        print(f"  P95: {metrics['p95']:.2f}ms")
        print(f"  P99: {metrics['p99']:.2f}ms")
        print(f"  平均: {metrics['mean']:.2f}ms")

        # 验证性能基准
        assert metrics["p50"] < PERFORMANCE_BENCHMARKS["health_check_p50"], \
            f"P50 延迟 {metrics['p50']:.2f}ms 超过基准 {PERFORMANCE_BENCHMARKS['health_check_p50']}ms"

    def test_models_endpoint_performance(self, test_client):
        """测试模型列表端点性能"""
        def make_request():
            return test_client.get("/api/models")

        metrics = measure_response_times(make_request, iterations=30)

        print(f"\n模型列表性能:")
        print(f"  P50: {metrics['p50']:.2f}ms")
        print(f"  P99: {metrics['p99']:.2f}ms")

        # 应该在合理时间内响应
        assert metrics["p99"] < PERFORMANCE_BENCHMARKS["api_response_p99"]

    def test_data_sources_endpoint_performance(self, test_client):
        """测试数据源列表端点性能"""
        def make_request():
            return test_client.get("/api/data-sources")

        metrics = measure_response_times(make_request, iterations=30)

        print(f"\n数据源列表性能:")
        print(f"  P50: {metrics['p50']:.2f}ms")
        print(f"  P99: {metrics['p99']:.2f}ms")

        assert metrics["p99"] < PERFORMANCE_BENCHMARKS["api_response_p99"]


# ════════════════════════════════════════════════════════════════════════════
# 缓存性能测试
# ════════════════════════════════════════════════════════════════════════════

class TestCachePerformance:
    """缓存性能测试"""

    @patch("cache._get_redis_client")
    def test_cache_get_performance(self, mock_get_client):
        """测试缓存获取性能"""
        import cache

        mock_client = MagicMock()
        mock_client.get.return_value = b"cached_value"
        mock_get_client.return_value = mock_client

        def cache_operation():
            return cache.cache_get("test_key")

        metrics = measure_response_times(cache_operation, iterations=1000)

        print(f"\n缓存获取性能:")
        print(f"  P50: {metrics['p50']:.3f}ms")
        print(f"  P99: {metrics['p99']:.3f}ms")
        print(f"  平均: {metrics['mean']:.3f}ms")

        assert metrics["p99"] < PERFORMANCE_BENCHMARKS["cache_get"]

    @patch("cache._get_redis_client")
    def test_cache_set_performance(self, mock_get_client):
        """测试缓存设置性能"""
        import cache

        mock_client = MagicMock()
        mock_client.setex.return_value = True
        mock_get_client.return_value = mock_client

        def cache_operation():
            return cache.cache_set("test_key", "test_value", ttl=3600)

        metrics = measure_response_times(cache_operation, iterations=1000)

        print(f"\n缓存设置性能:")
        print(f"  P50: {metrics['p50']:.3f}ms")
        print(f"  P99: {metrics['p99']:.3f}ms")

        assert metrics["p99"] < PERFORMANCE_BENCHMARKS["cache_set"]

    @patch("cache._get_redis_client")
    def test_cache_key_generation_performance(self, mock_get_client):
        """测试缓存键生成性能"""
        import cache

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is AI?"},
        ]

        def key_generation():
            return cache.get_llm_cache_key(messages, "deepseek-chat")

        metrics = measure_response_times(key_generation, iterations=1000)

        print(f"\n缓存键生成性能:")
        print(f"  P50: {metrics['p50']:.3f}ms")
        print(f"  P99: {metrics['p99']:.3f}ms")

        # 键生成应该非常快
        assert metrics["p99"] < 5


# ════════════════════════════════════════════════════════════════════════════
# 限流性能测试
# ════════════════════════════════════════════════════════════════════════════

class TestRateLimitPerformance:
    """限流性能测试"""

    @patch("rate_limit._get_redis_client")
    def test_rate_limit_check_performance(self, mock_get_client):
        """测试限流检查性能"""
        import rate_limit

        mock_client = MagicMock()
        mock_client.zcard.return_value = 10
        mock_client.zrange.return_value = []
        mock_client.zremrangebyscore.return_value = 0
        mock_client.zadd.return_value = 1
        mock_get_client.return_value = mock_client

        def rate_limit_operation():
            return rate_limit.check_rate_limit_ip("192.168.1.1", limit=60, window=60)

        metrics = measure_response_times(rate_limit_operation, iterations=1000)

        print(f"\n限流检查性能:")
        print(f"  P50: {metrics['p50']:.3f}ms")
        print(f"  P99: {metrics['p99']:.3f}ms")

        assert metrics["p99"] < PERFORMANCE_BENCHMARKS["rate_limit_check"]

    @patch("rate_limit._get_redis_client")
    def test_quota_check_performance(self, mock_get_client):
        """测试配额检查性能"""
        import rate_limit

        mock_client = MagicMock()
        mock_client.get.return_value = b"25"
        mock_get_client.return_value = mock_client

        def quota_operation():
            return rate_limit._check_quota_redis("user123")

        metrics = measure_response_times(quota_operation, iterations=1000)

        print(f"\n配额检查性能:")
        print(f"  P50: {metrics['p50']:.3f}ms")
        print(f"  P99: {metrics['p99']:.3f}ms")

        assert metrics["p99"] < PERFORMANCE_BENCHMARKS["rate_limit_check"]


# ════════════════════════════════════════════════════════════════════════════
# 状态操作性能测试
# ════════════════════════════════════════════════════════════════════════════

class TestStatePerformance:
    """状态操作性能测试"""

    def test_state_initialization_performance(self):
        """测试状态初始化性能"""
        from state import create_initial_state

        def state_init():
            return create_initial_state(
                topic="Test Topic",
                abstract="Test Abstract",
                report_type="research",
                language="中文",
                quality_threshold=0.55,
                max_retry=3,
                max_concurrent=5,
            )

        metrics = measure_response_times(state_init, iterations=1000)

        print(f"\n状态初始化性能:")
        print(f"  P50: {metrics['p50']:.3f}ms")
        print(f"  P99: {metrics['p99']:.3f}ms")

        # 状态初始化应该非常快
        assert metrics["p99"] < 5

    def test_hash_key_performance(self):
        """测试哈希键生成性能"""
        import cache

        content = "This is a test content for hash key generation performance testing."

        def hash_operation():
            return cache._hash_key(content)

        metrics = measure_response_times(hash_operation, iterations=10000)

        print(f"\n哈希键生成性能:")
        print(f"  P50: {metrics['p50']:.4f}ms")
        print(f"  P99: {metrics['p99']:.4f}ms")

        # 哈希应该非常快
        assert metrics["p99"] < 1


# ════════════════════════════════════════════════════════════════════════════
# 并发处理性能测试
# ════════════════════════════════════════════════════════════════════════════

class TestConcurrencyPerformance:
    """并发处理性能测试"""

    def test_concurrent_health_checks(self, test_client):
        """测试并发健康检查"""
        num_threads = 10
        requests_per_thread = 10

        def make_requests():
            times = []
            for _ in range(requests_per_thread):
                start = time.perf_counter()
                response = test_client.get("/health")
                end = time.perf_counter()
                times.append((end - start) * 1000)
            return times

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(make_requests) for _ in range(num_threads)]

            all_times = []
            for future in as_completed(futures):
                all_times.extend(future.result())

        all_times.sort()
        p50 = all_times[int(len(all_times) * 0.50)]
        p99 = all_times[int(len(all_times) * 0.99)]

        print(f"\n并发健康检查性能 ({num_threads} 线程 x {requests_per_thread} 请求):")
        print(f"  总请求数: {len(all_times)}")
        print(f"  P50: {p50:.2f}ms")
        print(f"  P99: {p99:.2f}ms")
        print(f"  平均: {statistics.mean(all_times):.2f}ms")

        # 并发时 P99 应该仍然在可接受范围
        assert p99 < PERFORMANCE_BENCHMARKS["health_check_p99"] * 2

    def test_concurrent_cache_operations(self):
        """测试并发缓存操作"""
        import cache

        with patch("cache._get_redis_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get.return_value = b"cached"
            mock_client.setex.return_value = True
            mock_get_client.return_value = mock_client

            num_threads = 20
            operations_per_thread = 100

            def cache_operations():
                for i in range(operations_per_thread):
                    cache.cache_get(f"key_{i}")
                    cache.cache_set(f"key_{i}", f"value_{i}")

            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(cache_operations) for _ in range(num_threads)]
                for future in as_completed(futures):
                    future.result()
            end = time.perf_counter()

            total_ops = num_threads * operations_per_thread * 2
            duration_ms = (end - start) * 1000
            ops_per_second = total_ops / (duration_ms / 1000)

            print(f"\n并发缓存操作性能:")
            print(f"  总操作数: {total_ops}")
            print(f"  总耗时: {duration_ms:.2f}ms")
            print(f"  吞吐量: {ops_per_second:.0f} ops/s")

            # 吞吐量应该足够高
            assert ops_per_second > 1000


# ════════════════════════════════════════════════════════════════════════════
# 内存使用测试
# ════════════════════════════════════════════════════════════════════════════

class TestMemoryUsage:
    """内存使用测试"""

    def test_state_memory_usage(self):
        """测试状态内存使用"""
        from state import create_initial_state
        import sys

        states = []
        for i in range(1000):
            state = create_initial_state(
                topic=f"Topic {i}",
                abstract=f"Abstract {i}" * 10,
            )
            states.append(state)

        # 粗略估算内存使用
        total_size = sum(sys.getsizeof(str(s)) for s in states)

        print(f"\n状态内存使用 (1000 个状态):")
        print(f"  总大小: {total_size / 1024:.2f} KB")
        print(f"  平均大小: {total_size / 1000:.2f} bytes")

        # 每个状态应该不超过 10KB
        assert total_size / 1000 < 10240

    def test_cache_stats_memory(self):
        """测试缓存统计内存使用"""
        import cache

        # 重置并创建大量统计
        cache.reset_cache_stats()

        for i in range(10000):
            cache._cache_stats["hits"] += 1
            cache._cache_stats["misses"] += 1

        import sys
        stats_size = sys.getsizeof(cache._cache_stats)

        print(f"\n缓存统计内存使用:")
        print(f"  大小: {stats_size} bytes")

        # 统计应该非常小
        assert stats_size < 1000


# ════════════════════════════════════════════════════════════════════════════
# 运行测试
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
