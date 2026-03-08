"""Comprehensive tests for the cache module."""

import asyncio
import time

import pytest

from ast_grep_mcp.cache import (
    AsyncLRUCache,
    CacheConfig,
    CacheEntry,
    CacheStatistics,
    cache_key,
    cached,
)


# ---------------------------------------------------------------------------
# CacheConfig tests
# ---------------------------------------------------------------------------

class TestCacheConfig:
    """Tests for CacheConfig dataclass."""

    def test_default_values(self):
        config = CacheConfig()
        assert config.max_entries == 1000
        assert config.max_memory_mb == 512
        assert config.default_ttl == 300
        assert config.max_ttl == 3600
        assert config.min_ttl == 30
        assert config.cleanup_interval == 60
        assert config.statistics_interval == 30
        assert config.enable_memory_monitoring is True
        assert config.enable_statistics is True
        assert config.enable_persistence is False
        assert config.persistence_file is None
        assert config.persistence_interval == 300

    def test_custom_values(self):
        config = CacheConfig(
            max_entries=500,
            max_memory_mb=256,
            default_ttl=60,
            max_ttl=1800,
            min_ttl=10,
            cleanup_interval=30,
            statistics_interval=15,
            enable_memory_monitoring=False,
            enable_statistics=False,
            enable_persistence=True,
            persistence_file="/tmp/cache.json",
            persistence_interval=120,
        )
        assert config.max_entries == 500
        assert config.max_memory_mb == 256
        assert config.default_ttl == 60
        assert config.max_ttl == 1800
        assert config.min_ttl == 10
        assert config.cleanup_interval == 30
        assert config.statistics_interval == 15
        assert config.enable_memory_monitoring is False
        assert config.enable_statistics is False
        assert config.enable_persistence is True
        assert config.persistence_file == "/tmp/cache.json"
        assert config.persistence_interval == 120


# ---------------------------------------------------------------------------
# CacheEntry tests
# ---------------------------------------------------------------------------

class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_is_expired_false(self):
        entry = CacheEntry(
            value="test",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=0,
            ttl=300,
        )
        assert entry.is_expired() is False

    def test_is_expired_true(self):
        entry = CacheEntry(
            value="test",
            created_at=time.time() - 400,
            last_accessed=time.time() - 400,
            access_count=0,
            ttl=300,
        )
        assert entry.is_expired() is True

    def test_touch(self):
        now = time.time()
        entry = CacheEntry(
            value="test",
            created_at=now - 100,
            last_accessed=now - 100,
            access_count=0,
            ttl=300,
        )
        old_last_accessed = entry.last_accessed
        old_access_count = entry.access_count

        entry.touch()

        assert entry.last_accessed > old_last_accessed
        assert entry.access_count == old_access_count + 1

    def test_size_bytes_default(self):
        entry = CacheEntry(
            value="test",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=0,
            ttl=300,
        )
        assert entry.size_bytes == 0

    def test_size_bytes_custom(self):
        entry = CacheEntry(
            value="test",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=0,
            ttl=300,
            size_bytes=1024,
        )
        assert entry.size_bytes == 1024


# ---------------------------------------------------------------------------
# CacheStatistics tests
# ---------------------------------------------------------------------------

class TestCacheStatistics:
    """Tests for CacheStatistics dataclass."""

    def test_default_counters(self):
        stats = CacheStatistics()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.expired_evictions == 0
        assert stats.manual_invalidations == 0
        assert stats.memory_evictions == 0
        assert stats.total_entries == 0
        assert stats.total_memory_bytes == 0
        assert stats.cleanup_runs == 0
        assert stats.average_hit_time_ms == 0.0
        assert stats.average_miss_time_ms == 0.0
        assert stats.hit_rate == 0.0

    def test_calculate_hit_rate_no_requests(self):
        stats = CacheStatistics()
        assert stats.calculate_hit_rate() == 0.0

    def test_calculate_hit_rate(self):
        stats = CacheStatistics(hits=75, misses=25)
        rate = stats.calculate_hit_rate()
        assert rate == 75.0
        assert stats.hit_rate == 75.0

    def test_reset(self):
        stats = CacheStatistics(hits=100, misses=50, evictions=10)
        stats.reset()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0


# ---------------------------------------------------------------------------
# AsyncLRUCache tests
# ---------------------------------------------------------------------------

class TestAsyncLRUCache:
    """Tests for AsyncLRUCache."""

    @pytest.fixture
    def config(self):
        return CacheConfig(
            max_entries=10,
            default_ttl=300,
            min_ttl=1,
            enable_memory_monitoring=False,
        )

    @pytest.fixture
    def cache(self, config):
        return AsyncLRUCache(config)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key_returns_none(self, cache):
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_missing_key_returns_default(self, cache):
        result = await cache.get("nonexistent", default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, cache):
        await cache.set("key1", "value1")
        deleted = await cache.delete("key1")
        assert deleted is True
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, cache):
        deleted = await cache.delete("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        count = await cache.clear()
        assert count == 3
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        config = CacheConfig(
            max_entries=3,
            default_ttl=300,
            min_ttl=1,
            enable_memory_monitoring=False,
        )
        cache = AsyncLRUCache(config)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        # Adding a 4th entry should evict key1 (LRU)
        await cache.set("key4", "value4")

        assert await cache.get("key1") is None  # evicted
        assert await cache.get("key2") == "value2"
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"

    @pytest.mark.asyncio
    async def test_lru_eviction_respects_access_order(self):
        config = CacheConfig(
            max_entries=3,
            default_ttl=300,
            min_ttl=1,
            enable_memory_monitoring=False,
        )
        cache = AsyncLRUCache(config)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        # Access key1 so it becomes most recently used
        await cache.get("key1")

        # Adding key4 should evict key2 (now the LRU)
        await cache.set("key4", "value4")

        assert await cache.get("key1") == "value1"  # still present (was accessed)
        assert await cache.get("key2") is None  # evicted
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        config = CacheConfig(
            max_entries=10,
            default_ttl=300,
            min_ttl=1,
            enable_memory_monitoring=False,
        )
        cache = AsyncLRUCache(config)

        # Set with a very short TTL
        await cache.set("key1", "value1", ttl=1)

        # Should be present immediately
        assert await cache.get("key1") == "value1"

        # Wait for expiry
        await asyncio.sleep(1.1)

        # Should be expired now
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_statistics_tracking_hits(self, cache):
        await cache.set("key1", "value1")
        await cache.get("key1")
        await cache.get("key1")

        stats = cache.get_statistics()
        assert stats.hits == 2

    @pytest.mark.asyncio
    async def test_statistics_tracking_misses(self, cache):
        await cache.get("missing1")
        await cache.get("missing2")

        stats = cache.get_statistics()
        assert stats.misses == 2

    @pytest.mark.asyncio
    async def test_statistics_hit_rate(self, cache):
        await cache.set("key1", "value1")
        await cache.get("key1")  # hit
        await cache.get("key1")  # hit
        await cache.get("missing")  # miss

        stats = cache.get_statistics()
        assert stats.hit_rate == pytest.approx(66.66, abs=0.1)

    @pytest.mark.asyncio
    async def test_statistics_evictions(self):
        config = CacheConfig(
            max_entries=2,
            default_ttl=300,
            min_ttl=1,
            enable_memory_monitoring=False,
        )
        cache = AsyncLRUCache(config)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")  # triggers eviction

        stats = cache.get_statistics()
        assert stats.evictions == 1

    @pytest.mark.asyncio
    async def test_invalidate_group(self, cache):
        await cache.set("key1", "value1", group="group_a")
        await cache.set("key2", "value2", group="group_a")
        await cache.set("key3", "value3", group="group_b")

        count = await cache.invalidate_group("group_a")
        assert count == 2

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") == "value3"

    @pytest.mark.asyncio
    async def test_invalidate_group_nonexistent(self, cache):
        count = await cache.invalidate_group("nonexistent_group")
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_size(self, cache):
        assert cache.get_size() == 0

        await cache.set("key1", "value1")
        assert cache.get_size() == 1

        await cache.set("key2", "value2")
        assert cache.get_size() == 2

        await cache.delete("key1")
        assert cache.get_size() == 1

        await cache.clear()
        assert cache.get_size() == 0

    @pytest.mark.asyncio
    async def test_overwrite_existing_key(self, cache):
        await cache.set("key1", "value1")
        await cache.set("key1", "value2")
        result = await cache.get("key1")
        assert result == "value2"
        assert cache.get_size() == 1

    @pytest.mark.asyncio
    async def test_ttl_clamping_to_max(self):
        config = CacheConfig(
            max_entries=10,
            max_ttl=100,
            min_ttl=1,
            enable_memory_monitoring=False,
        )
        cache = AsyncLRUCache(config)
        await cache.set("key1", "value1", ttl=9999)
        # The entry should still exist; its TTL was clamped to max_ttl
        entry = cache._cache["key1"]
        assert entry.ttl == 100

    @pytest.mark.asyncio
    async def test_ttl_clamping_to_min(self):
        config = CacheConfig(
            max_entries=10,
            min_ttl=30,
            enable_memory_monitoring=False,
        )
        cache = AsyncLRUCache(config)
        await cache.set("key1", "value1", ttl=1)
        entry = cache._cache["key1"]
        assert entry.ttl == 30

    @pytest.mark.asyncio
    async def test_cache_complex_values(self, cache):
        complex_value = {
            "list": [1, 2, 3],
            "nested": {"a": "b"},
            "number": 42,
        }
        await cache.set("complex", complex_value)
        result = await cache.get("complex")
        assert result == complex_value

    @pytest.mark.asyncio
    async def test_event_listener(self, cache):
        events = []

        def listener(event_type, data):
            events.append((event_type, data))

        cache.add_event_listener(listener)
        await cache.set("key1", "value1")
        await cache.get("key1")
        await cache.get("missing")

        event_types = [e[0] for e in events]
        assert "cache_set" in event_types
        assert "cache_hit" in event_types
        assert "cache_miss" in event_types

    @pytest.mark.asyncio
    async def test_remove_event_listener(self, cache):
        events = []

        def listener(event_type, data):
            events.append(event_type)

        cache.add_event_listener(listener)
        await cache.set("key1", "value1")
        assert len(events) > 0

        cache.remove_event_listener(listener)
        events.clear()
        await cache.set("key2", "value2")
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_manual_invalidation_stats(self, cache):
        await cache.set("key1", "value1")
        await cache.delete("key1")

        stats = cache.get_statistics()
        assert stats.manual_invalidations == 1


# ---------------------------------------------------------------------------
# cache_key() tests
# ---------------------------------------------------------------------------

class TestCacheKey:
    """Tests for the cache_key helper function."""

    def test_deterministic(self):
        key1 = cache_key("op", args=(1, 2))
        key2 = cache_key("op", args=(1, 2))
        assert key1 == key2

    def test_different_operations_yield_different_keys(self):
        key1 = cache_key("op_a", args=(1,))
        key2 = cache_key("op_b", args=(1,))
        assert key1 != key2

    def test_different_args_yield_different_keys(self):
        key1 = cache_key("op", args=(1,))
        key2 = cache_key("op", args=(2,))
        assert key1 != key2


# ---------------------------------------------------------------------------
# cached() decorator tests
# ---------------------------------------------------------------------------

class TestCachedDecorator:
    """Tests for the cached() decorator."""

    @pytest.mark.asyncio
    async def test_caches_async_function_results(self):
        config = CacheConfig(
            max_entries=10,
            default_ttl=300,
            min_ttl=1,
            enable_memory_monitoring=False,
        )
        cache_inst = AsyncLRUCache(config)
        call_count = 0

        @cached(cache_instance=cache_inst)
        async def expensive_function(x: int, y: int) -> int:
            nonlocal call_count
            call_count += 1
            return x + y

        result1 = await expensive_function(1, 2)
        assert result1 == 3
        assert call_count == 1

        # Same args should return cached result without calling again
        result2 = await expensive_function(1, 2)
        assert result2 == 3
        assert call_count == 1  # still 1, used cache

    @pytest.mark.asyncio
    async def test_different_args_not_cached(self):
        config = CacheConfig(
            max_entries=10,
            default_ttl=300,
            min_ttl=1,
            enable_memory_monitoring=False,
        )
        cache_inst = AsyncLRUCache(config)
        call_count = 0

        @cached(cache_instance=cache_inst)
        async def expensive_function(x: int, y: int) -> int:
            nonlocal call_count
            call_count += 1
            return x + y

        await expensive_function(1, 2)
        await expensive_function(3, 4)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_cached_with_custom_key_func(self):
        config = CacheConfig(
            max_entries=10,
            default_ttl=300,
            min_ttl=1,
            enable_memory_monitoring=False,
        )
        cache_inst = AsyncLRUCache(config)
        call_count = 0

        def my_key_func(x, y):
            return f"custom:{x}:{y}"

        @cached(cache_instance=cache_inst, key_func=my_key_func)
        async def add(x: int, y: int) -> int:
            nonlocal call_count
            call_count += 1
            return x + y

        result1 = await add(1, 2)
        result2 = await add(1, 2)
        assert result1 == 3
        assert result2 == 3
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_cached_raises_without_cache_instance(self):
        @cached()
        async def func():
            return 42

        with pytest.raises(ValueError, match="cache_instance must be provided"):
            await func()
