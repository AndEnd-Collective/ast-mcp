"""Comprehensive tests for the concurrency module.

Covers ConcurrencyConfig, RequestPriority, QueuedRequest,
DistributedLock, and ConcurrentRequestManager.
"""

import asyncio
import time

import pytest

from ast_grep_mcp.concurrency import (
    ConcurrencyConfig,
    ConcurrentRequestManager,
    DistributedLock,
    QueuedRequest,
    RequestPriority,
)


# ---------------------------------------------------------------------------
# ConcurrencyConfig
# ---------------------------------------------------------------------------

class TestConcurrencyConfig:
    """Tests for ConcurrencyConfig dataclass."""

    def test_default_values(self):
        config = ConcurrencyConfig()
        assert config.max_concurrent_requests == 50
        assert config.max_concurrent_search == 20
        assert config.max_concurrent_scan == 10
        assert config.max_concurrent_run == 5
        assert config.max_concurrent_call_graph == 15
        assert config.max_queue_size == 200
        assert config.queue_timeout == 30.0
        assert config.priority_boost_cache_hits is True
        assert config.global_rate_limit == 1000
        assert config.search_rate_limit == 300
        assert config.scan_rate_limit == 120
        assert config.run_rate_limit == 60
        assert config.call_graph_rate_limit == 180
        assert config.per_user_rate_limit == 100
        assert config.per_ip_rate_limit == 200
        assert config.lock_timeout == 30.0
        assert config.lock_retry_delay == 0.1
        assert config.max_lock_retries == 50
        assert config.enable_per_user_limits is True
        assert config.enable_priority_queue is True
        assert config.cache_hit_priority_boost == 2

    def test_custom_values(self):
        config = ConcurrencyConfig(
            max_concurrent_requests=10,
            max_queue_size=50,
            global_rate_limit=500,
            per_user_rate_limit=25,
            lock_timeout=5.0,
        )
        assert config.max_concurrent_requests == 10
        assert config.max_queue_size == 50
        assert config.global_rate_limit == 500
        assert config.per_user_rate_limit == 25
        assert config.lock_timeout == 5.0
        # Other fields should retain defaults
        assert config.max_concurrent_search == 20


# ---------------------------------------------------------------------------
# RequestPriority
# ---------------------------------------------------------------------------

class TestRequestPriority:
    """Tests for RequestPriority dataclass and ordering."""

    def test_enum_fields_exist(self):
        prio = RequestPriority(level=3)
        assert prio.level == 3
        assert prio.cache_hit is False
        assert prio.user_id is None
        assert isinstance(prio.submitted_at, float)

    def test_ordering_by_level(self):
        high = RequestPriority(level=1)
        low = RequestPriority(level=5)
        assert high < low
        assert not low < high

    def test_ordering_cache_hit_boost(self):
        cached = RequestPriority(level=3, cache_hit=True)
        uncached = RequestPriority(level=3, cache_hit=False)
        # Same level, cached should be ordered before uncached
        assert cached < uncached

    def test_ordering_fifo_same_level_same_cache(self):
        early = RequestPriority(level=3, cache_hit=False, submitted_at=100.0)
        late = RequestPriority(level=3, cache_hit=False, submitted_at=200.0)
        assert early < late
        assert not late < early

    def test_equal_priorities(self):
        ts = time.time()
        a = RequestPriority(level=3, cache_hit=False, submitted_at=ts)
        b = RequestPriority(level=3, cache_hit=False, submitted_at=ts)
        # Neither is less than the other
        assert not a < b
        assert not b < a


# ---------------------------------------------------------------------------
# QueuedRequest
# ---------------------------------------------------------------------------

class TestQueuedRequest:
    """Tests for QueuedRequest dataclass."""

    def test_field_presence(self):
        prio = RequestPriority(level=1)
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        req = QueuedRequest(
            priority=prio,
            operation="search",
            compute_func=lambda: None,
            future=future,
            request_id="req_0",
        )
        assert req.priority is prio
        assert req.operation == "search"
        assert callable(req.compute_func)
        assert req.future is future
        assert req.request_id == "req_0"
        assert req.metadata == {}
        loop.close()

    def test_metadata_default_factory(self):
        prio = RequestPriority(level=1)
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        req1 = QueuedRequest(
            priority=prio,
            operation="scan",
            compute_func=lambda: None,
            future=future,
            request_id="r1",
        )
        req2 = QueuedRequest(
            priority=prio,
            operation="scan",
            compute_func=lambda: None,
            future=loop.create_future(),
            request_id="r2",
        )
        # Ensure separate dict instances
        assert req1.metadata is not req2.metadata
        loop.close()


# ---------------------------------------------------------------------------
# DistributedLock
# ---------------------------------------------------------------------------

class TestDistributedLock:
    """Tests for DistributedLock class methods."""

    @pytest.fixture(autouse=True)
    def _reset_locks(self):
        """Reset DistributedLock state between tests."""
        DistributedLock.reset()
        yield
        DistributedLock.reset()

    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        acquired = await DistributedLock.acquire("test_key")
        assert acquired is True
        DistributedLock.release("test_key")

    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        # Acquire the lock so a second acquire must wait
        acquired = await DistributedLock.acquire("timeout_key")
        assert acquired is True

        # Try to acquire again with a very short timeout
        acquired_again = await DistributedLock.acquire("timeout_key", timeout=0.05)
        assert acquired_again is False

        # Release to clean up
        DistributedLock.release("timeout_key")

    @pytest.mark.asyncio
    async def test_release_nonexistent_key(self):
        # Should not raise
        DistributedLock.release("nonexistent_key")

    @pytest.mark.asyncio
    async def test_acquire_after_release(self):
        await DistributedLock.acquire("reuse_key")
        DistributedLock.release("reuse_key")

        acquired = await DistributedLock.acquire("reuse_key", timeout=1.0)
        assert acquired is True
        DistributedLock.release("reuse_key")

    @pytest.mark.asyncio
    async def test_context_manager_not_supported(self):
        """DistributedLock is class-level and does not support async with."""
        with pytest.raises((TypeError, NotImplementedError)):
            async with DistributedLock:
                pass


# ---------------------------------------------------------------------------
# ConcurrentRequestManager
# ---------------------------------------------------------------------------

class TestConcurrentRequestManager:
    """Tests for ConcurrentRequestManager."""

    @pytest.fixture(autouse=True)
    def _reset_locks(self):
        """Reset DistributedLock state between tests."""
        DistributedLock.reset()
        yield
        DistributedLock.reset()

    def test_initialization_with_default_config(self):
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)
        assert manager.config is config
        assert manager._request_counter == 0
        assert manager._queue_processor_task is None

    def test_get_queue_stats_keys(self):
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)
        stats = manager.get_queue_stats()
        expected_keys = {
            "queue_size",
            "active_requests",
            "max_queue_size",
            "requests_queued",
            "requests_processed",
        }
        assert set(stats.keys()) == expected_keys

    def test_get_stats_keys(self):
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)
        stats = manager.get_stats()
        expected_keys = {
            "requests_queued",
            "requests_processed",
            "requests_failed",
            "requests_rate_limited",
            "requests_timeout",
            "average_queue_time",
            "concurrent_requests",
            "cache_hit_requests",
            "queue_size",
            "active_requests",
            "max_queue_size",
            "global_concurrent_limit",
        }
        assert set(stats.keys()) == expected_keys

    def test_get_stats_initial_values(self):
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)
        stats = manager.get_stats()
        assert stats["requests_queued"] == 0
        assert stats["requests_processed"] == 0
        assert stats["queue_size"] == 0
        assert stats["active_requests"] == 0
        assert stats["global_concurrent_limit"] == 50

    @pytest.mark.asyncio
    async def test_execute_with_concurrency_control(self):
        """Verify that a simple async function runs through the manager."""
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)
        await manager.start()

        async def compute():
            return 42

        try:
            result = await manager.execute_with_concurrency_control(
                operation="search",
                compute_func=compute,
                timeout=5.0,
            )
            assert result == 42
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_execute_updates_stats(self):
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)
        await manager.start()

        async def compute():
            return "ok"

        try:
            await manager.execute_with_concurrency_control(
                operation="scan",
                compute_func=compute,
                timeout=5.0,
            )
            stats = manager.get_stats()
            assert stats["requests_queued"] >= 1
            assert stats["requests_processed"] >= 1
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_rate_limiting_respects_limits(self):
        """With a very low rate limit, requests should be rejected."""
        config = ConcurrencyConfig(global_rate_limit=1)
        manager = ConcurrentRequestManager(config)
        await manager.start()

        async def compute():
            return "ok"

        try:
            # First request should succeed (bucket starts full with 1 token)
            result = await manager.execute_with_concurrency_control(
                operation="search",
                compute_func=compute,
                timeout=5.0,
            )
            assert result == "ok"

            # Second request should be rate limited (bucket empty)
            with pytest.raises(ValueError, match="Rate limit exceeded"):
                await manager.execute_with_concurrency_control(
                    operation="search",
                    compute_func=compute,
                    timeout=5.0,
                )
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_cache_hit_priority_boost(self):
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)
        await manager.start()

        async def compute():
            return "cached"

        try:
            result = await manager.execute_with_concurrency_control(
                operation="search",
                compute_func=compute,
                cache_hit=True,
                timeout=5.0,
            )
            assert result == "cached"
            stats = manager.get_stats()
            assert stats["cache_hit_requests"] >= 1
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending(self):
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)
        await manager.start()
        await manager.shutdown()
        # Should be safe to call shutdown twice
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_invalidate_user_cache(self):
        config = ConcurrencyConfig()
        manager = ConcurrentRequestManager(config)

        # Access user-specific resources to populate them
        _ = manager._user_rate_limiters["user_1"]
        _ = manager._user_semaphores["user_1"]

        assert "user_1" in manager._user_rate_limiters
        assert "user_1" in manager._user_semaphores

        await manager.invalidate_user_cache("user_1")

        assert "user_1" not in manager._user_rate_limiters
        assert "user_1" not in manager._user_semaphores

    @pytest.mark.asyncio
    async def test_per_user_rate_limiting(self):
        """Per-user rate limiter should reject when user exceeds limit."""
        config = ConcurrencyConfig(per_user_rate_limit=1)
        manager = ConcurrentRequestManager(config)
        await manager.start()

        async def compute():
            return "ok"

        try:
            await manager.execute_with_concurrency_control(
                operation="search",
                compute_func=compute,
                user_id="limited_user",
                timeout=5.0,
            )

            with pytest.raises(ValueError, match="Rate limit exceeded"):
                await manager.execute_with_concurrency_control(
                    operation="search",
                    compute_func=compute,
                    user_id="limited_user",
                    timeout=5.0,
                )
        finally:
            await manager.shutdown()

    def test_check_rate_limits_sync(self):
        """_check_rate_limits is synchronous and uses TokenBucket.consume()."""
        config = ConcurrencyConfig(global_rate_limit=2)
        manager = ConcurrentRequestManager(config)

        assert manager._check_rate_limits("search", None, None) is True
        assert manager._check_rate_limits("search", None, None) is True
        # Third call should fail (capacity=2)
        assert manager._check_rate_limits("search", None, None) is False
