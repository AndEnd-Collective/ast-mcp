"""Async-compatible result caching with TTL and LRU eviction."""

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar

from threading import RLock

T = TypeVar('T')
CacheKey = str
CacheValue = Any

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Configuration for caching behavior."""

    # Cache size limits
    max_entries: int = 1000
    max_memory_mb: int = 512

    # TTL settings (in seconds)
    default_ttl: int = 300  # 5 minutes
    max_ttl: int = 3600     # 1 hour
    min_ttl: int = 30       # 30 seconds

    # Performance settings
    cleanup_interval: int = 60  # seconds
    statistics_interval: int = 30  # seconds

    # Feature flags
    enable_memory_monitoring: bool = True
    enable_statistics: bool = True
    enable_persistence: bool = False

    # Persistence settings
    persistence_file: Optional[str] = None
    persistence_interval: int = 300  # 5 minutes


@dataclass
class CacheEntry:
    """Represents a cached entry with metadata."""

    value: Any
    created_at: float
    last_accessed: float
    access_count: int
    ttl: int
    size_bytes: int = 0

    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return time.time() - self.created_at > self.ttl

    def touch(self) -> None:
        """Update last accessed time and increment access count."""
        self.last_accessed = time.time()
        self.access_count += 1


@dataclass
class CacheStatistics:
    """Cache performance statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expired_evictions: int = 0
    manual_invalidations: int = 0
    memory_evictions: int = 0
    total_entries: int = 0
    total_memory_bytes: int = 0
    cleanup_runs: int = 0

    # Performance metrics
    average_hit_time_ms: float = 0.0
    average_miss_time_ms: float = 0.0
    hit_rate: float = 0.0

    def calculate_hit_rate(self) -> float:
        """Calculate current hit rate percentage."""
        total_requests = self.hits + self.misses
        if total_requests == 0:
            return 0.0
        self.hit_rate = (self.hits / total_requests) * 100
        return self.hit_rate

    def reset(self) -> None:
        """Reset all statistics."""
        self.__dict__.update(CacheStatistics().__dict__)


class AsyncLRUCache:
    """
    High-performance async-compatible LRU cache with TTL expiration.

    Features:
    - LRU eviction policy with configurable size limits
    - TTL-based expiration with cleanup
    - Memory usage monitoring and limits
    - Thread-safe operations
    - Comprehensive statistics
    - Manual and automatic invalidation
    """

    def __init__(self, config: CacheConfig):
        self.config = config
        self._cache: OrderedDict[CacheKey, CacheEntry] = OrderedDict()
        self._lock = RLock()
        self._statistics = CacheStatistics()

        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stats_task: Optional[asyncio.Task] = None
        self._persistence_task: Optional[asyncio.Task] = None

        # Event listeners for cache events
        self._event_listeners: List[Callable[[str, Any], None]] = []

        # Invalidation groups for event-driven invalidation
        self._invalidation_groups: Dict[str, Set[CacheKey]] = {}

        logger.info(f"AsyncLRUCache initialized with config: {config}")

    async def get(self, key: CacheKey, default: Any = None) -> Any:
        """
        Get a value from cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            Cached value or default
        """
        start_time = time.time()

        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._statistics.misses += 1
                self._statistics.average_miss_time_ms = self._update_average_time(
                    self._statistics.average_miss_time_ms,
                    self._statistics.misses,
                    start_time
                )
                await self._emit_event("cache_miss", {"key": key})
                return default

            if entry.is_expired():
                self._remove_entry(key)
                self._statistics.misses += 1
                self._statistics.expired_evictions += 1
                await self._emit_event("cache_expired", {"key": key})
                return default

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.touch()

            self._statistics.hits += 1
            self._statistics.average_hit_time_ms = self._update_average_time(
                self._statistics.average_hit_time_ms,
                self._statistics.hits,
                start_time
            )

            await self._emit_event("cache_hit", {"key": key, "access_count": entry.access_count})
            return entry.value

    async def set(self, key: CacheKey, value: Any, ttl: Optional[int] = None, group: Optional[str] = None) -> None:
        """
        Set a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
            group: Invalidation group for event-driven invalidation
        """
        if ttl is None:
            ttl = self.config.default_ttl
        elif ttl > self.config.max_ttl:
            ttl = self.config.max_ttl
        elif ttl < self.config.min_ttl:
            ttl = self.config.min_ttl

        size_bytes = self._calculate_size(value)
        current_time = time.time()

        entry = CacheEntry(
            value=value,
            created_at=current_time,
            last_accessed=current_time,
            access_count=0,
            ttl=ttl,
            size_bytes=size_bytes
        )

        with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                self._remove_entry(key)

            # Check memory limits before adding
            await self._enforce_memory_limits(size_bytes)

            # Add new entry
            self._cache[key] = entry
            self._statistics.total_entries = len(self._cache)
            self._statistics.total_memory_bytes += size_bytes

            # Add to invalidation group if specified
            if group:
                if group not in self._invalidation_groups:
                    self._invalidation_groups[group] = set()
                self._invalidation_groups[group].add(key)

            # Enforce size limits
            await self._enforce_size_limits()

        await self._emit_event("cache_set", {
            "key": key,
            "size_bytes": size_bytes,
            "ttl": ttl,
            "group": group
        })

    async def delete(self, key: CacheKey) -> bool:
        """
        Delete a specific key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was found and deleted, False otherwise
        """
        with self._lock:
            if key in self._cache:
                self._remove_entry(key)
                self._statistics.manual_invalidations += 1
                await self._emit_event("cache_delete", {"key": key})
                return True
            return False

    async def invalidate_group(self, group: str) -> int:
        """
        Invalidate all entries in a specific group.

        Args:
            group: Invalidation group name

        Returns:
            Number of entries invalidated
        """
        if group not in self._invalidation_groups:
            return 0

        keys_to_remove = list(self._invalidation_groups[group])
        count = 0

        with self._lock:
            for key in keys_to_remove:
                if key in self._cache:
                    self._remove_entry(key)
                    count += 1

            del self._invalidation_groups[group]
            self._statistics.manual_invalidations += count

        await self._emit_event("group_invalidated", {"group": group, "count": count})
        return count

    async def clear(self) -> int:
        """
        Clear all entries from cache.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._invalidation_groups.clear()
            self._statistics.total_entries = 0
            self._statistics.total_memory_bytes = 0
            self._statistics.manual_invalidations += count

        await self._emit_event("cache_cleared", {"count": count})
        return count

    def get_statistics(self) -> CacheStatistics:
        """Get current cache statistics."""
        with self._lock:
            stats = CacheStatistics(**self._statistics.__dict__)
            stats.calculate_hit_rate()
            return stats

    def get_size(self) -> int:
        """Get the current number of entries in the cache."""
        with self._lock:
            return len(self._cache)

    def add_event_listener(self, listener: Callable[[str, Any], None]) -> None:
        """Add an event listener for cache events."""
        self._event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[str, Any], None]) -> None:
        """Remove an event listener."""
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)

    async def start_background_tasks(self) -> None:
        """Start background maintenance tasks."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        if self.config.enable_statistics and self._stats_task is None:
            self._stats_task = asyncio.create_task(self._statistics_loop())

        if self.config.enable_persistence and self._persistence_task is None:
            self._persistence_task = asyncio.create_task(self._persistence_loop())

    async def stop_background_tasks(self) -> None:
        """Stop background maintenance tasks."""
        tasks = [
            self._cleanup_task,
            self._stats_task,
            self._persistence_task
        ]

        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._cleanup_task = None
        self._stats_task = None
        self._persistence_task = None

    # Private methods

    def _remove_entry(self, key: CacheKey) -> None:
        """Remove an entry from cache (must be called with lock held)."""
        if key in self._cache:
            entry = self._cache[key]
            del self._cache[key]
            self._statistics.total_entries = len(self._cache)
            self._statistics.total_memory_bytes -= entry.size_bytes

            # Remove from invalidation groups
            for group_keys in self._invalidation_groups.values():
                group_keys.discard(key)

    async def _enforce_size_limits(self) -> None:
        """Enforce cache size limits by evicting LRU entries."""
        while len(self._cache) > self.config.max_entries:
            # Remove least recently used (first item in OrderedDict)
            lru_key = next(iter(self._cache))
            self._remove_entry(lru_key)
            self._statistics.evictions += 1
            await self._emit_event("cache_evicted_lru", {"key": lru_key})

    async def _enforce_memory_limits(self, incoming_size: int = 0) -> None:
        """Enforce memory limits by evicting entries if needed."""
        if not self.config.enable_memory_monitoring:
            return

        max_bytes = self.config.max_memory_mb * 1024 * 1024
        current_bytes = self._statistics.total_memory_bytes + incoming_size

        while current_bytes > max_bytes and self._cache:
            # Remove least recently used
            lru_key = next(iter(self._cache))
            entry = self._cache[lru_key]
            self._remove_entry(lru_key)
            current_bytes -= entry.size_bytes
            self._statistics.memory_evictions += 1
            await self._emit_event("cache_evicted_memory", {"key": lru_key, "size_bytes": entry.size_bytes})

    def _calculate_size(self, value: Any) -> int:
        """Estimate memory size of a value in bytes."""
        try:
            if isinstance(value, (str, bytes)):
                return len(value.encode('utf-8') if isinstance(value, str) else value)
            elif isinstance(value, (dict, list, tuple)):
                return len(json.dumps(value, default=str).encode('utf-8'))
            else:
                return len(str(value).encode('utf-8'))
        except (TypeError, ValueError):
            # Fallback estimation
            return 1024  # 1KB default estimate

    def _update_average_time(self, current_avg: float, count: int, start_time: float) -> float:
        """Update rolling average response time."""
        duration_ms = (time.time() - start_time) * 1000
        return ((current_avg * (count - 1)) + duration_ms) / count

    async def _emit_event(self, event_type: str, data: Any) -> None:
        """Emit cache event to all listeners."""
        for listener in self._event_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event_type, data)
                else:
                    listener(event_type, data)
            except Exception as e:
                logger.warning(f"Cache event listener error: {e}")

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    async def _cleanup_expired(self) -> None:
        """Remove expired entries from cache."""
        current_time = time.time()
        expired_keys = []

        with self._lock:
            for key, entry in self._cache.items():
                if current_time - entry.created_at > entry.ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                self._remove_entry(key)
                self._statistics.expired_evictions += 1

            self._statistics.cleanup_runs += 1

        if expired_keys:
            await self._emit_event("cleanup_completed", {
                "expired_count": len(expired_keys),
                "keys": expired_keys
            })

    async def _statistics_loop(self) -> None:
        """Background task to log cache statistics."""
        while True:
            try:
                await asyncio.sleep(self.config.statistics_interval)
                stats = self.get_statistics()
                logger.info(f"Cache stats: {stats.hits} hits, {stats.misses} misses, "
                           f"{stats.hit_rate:.1f}% hit rate, {stats.total_entries} entries, "
                           f"{stats.total_memory_bytes/1024/1024:.1f}MB memory")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache statistics error: {e}")

    async def _persistence_loop(self) -> None:
        """Background task to persist cache to disk."""
        if not self.config.persistence_file:
            return

        while True:
            try:
                await asyncio.sleep(self.config.persistence_interval)
                await self._save_to_disk()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache persistence error: {e}")

    async def _save_to_disk(self) -> None:
        """Save cache contents to disk."""
        if not self.config.persistence_file:
            return

        try:
            data = {
                "entries": {},
                "statistics": self._statistics.__dict__,
                "timestamp": time.time()
            }

            with self._lock:
                for key, entry in self._cache.items():
                    # Only save non-expired entries
                    if not entry.is_expired():
                        data["entries"][key] = {
                            "value": entry.value,
                            "created_at": entry.created_at,
                            "last_accessed": entry.last_accessed,
                            "access_count": entry.access_count,
                            "ttl": entry.ttl,
                            "size_bytes": entry.size_bytes
                        }

            with open(self.config.persistence_file, 'w') as f:
                json.dump(data, f, default=str, indent=2)

        except Exception as e:
            logger.error(f"Failed to save cache to disk: {e}")

    async def load_from_disk(self) -> None:
        """Load cache contents from disk."""
        if not self.config.persistence_file or not os.path.exists(self.config.persistence_file):
            return

        try:
            with open(self.config.persistence_file, 'r') as f:
                data = json.load(f)

            loaded_count = 0

            with self._lock:
                for key, entry_data in data.get("entries", {}).items():
                    entry = CacheEntry(
                        value=entry_data["value"],
                        created_at=entry_data["created_at"],
                        last_accessed=entry_data["last_accessed"],
                        access_count=entry_data["access_count"],
                        ttl=entry_data["ttl"],
                        size_bytes=entry_data["size_bytes"]
                    )

                    # Only load non-expired entries
                    if not entry.is_expired():
                        self._cache[key] = entry
                        loaded_count += 1

                self._statistics.total_entries = len(self._cache)
                self._statistics.total_memory_bytes = sum(
                    entry.size_bytes for entry in self._cache.values()
                )

            logger.info(f"Loaded {loaded_count} cache entries from disk")

        except Exception as e:
            logger.error(f"Failed to load cache from disk: {e}")


def cache_key(operation: str, **kwargs) -> str:
    """
    Generate a cache key for an operation with parameters.

    Args:
        operation: Operation name
        **kwargs: Operation parameters

    Returns:
        Cache key string
    """
    param_str = json.dumps(kwargs, sort_keys=True, default=str)
    key_data = f"{operation}:{param_str}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]


def cached(
    ttl: Optional[int] = None,
    group: Optional[str] = None,
    key_func: Optional[Callable[..., str]] = None,
    cache_instance: Optional[AsyncLRUCache] = None
):
    """
    Decorator to cache async function results.

    Args:
        ttl: Cache TTL in seconds
        group: Invalidation group
        key_func: Custom key generation function
        cache_instance: AsyncLRUCache instance to use for caching
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            _cache = cache_instance
            if _cache is None:
                raise ValueError("cache_instance must be provided to the cached() decorator")

            if key_func:
                the_cache_key = key_func(*args, **kwargs)
            else:
                # Default key generation using function name and parameters
                the_cache_key = cache_key(func.__name__, args=args, kwargs=kwargs)

            # Try cache first
            result = await _cache.get(the_cache_key)
            if result is not None:
                return result

            # Compute and cache
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await _cache.set(the_cache_key, result, ttl=ttl, group=group)
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else func

    return decorator
