"""
Performance Optimization and Caching System for AST-Grep MCP Server.

This module provides comprehensive performance optimization capabilities including:
- Async-compatible result caching with TTL and LRU eviction
- Cache invalidation strategies (manual, TTL-based, event-driven)
- Performance metrics collection and monitoring
- Memory usage optimization and leak detection
- Request concurrency management
- Result streaming for large outputs
"""

import asyncio
import hashlib
import logging
import time
import weakref
import gc
import sys
import tracemalloc
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar, Union, AsyncIterator, Iterator, Awaitable
from threading import RLock
import json
import psutil
import os
import statistics
from collections import deque
from typing import Dict, List, Optional, Any, Callable, Tuple
import math

# Type definitions
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
        
        # Memory monitoring
        self._memory_monitor = psutil.Process() if config.enable_memory_monitoring else None
        
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
            
            current_time = time.time()
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


class PerformanceManager:
    """
    Central performance management system for AST-Grep MCP Server.
    
    Provides:
    - Result caching with configurable policies
    - Cache warming and preloading
    - Performance metrics collection
    - Memory usage optimization
    - Cache invalidation strategies
    """
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.cache = AsyncLRUCache(self.config)
        
        # Performance metrics
        self._operation_times: Dict[str, List[float]] = {}
        self._operation_counts: Dict[str, int] = {}
        
        # Setup logging
        self.cache.add_event_listener(self._log_cache_events)
        
        logger.info("PerformanceManager initialized")
    
    async def initialize(self) -> None:
        """Initialize the performance manager and start background tasks."""
        await self.cache.load_from_disk()
        await self.cache.start_background_tasks()
        logger.info("PerformanceManager started")
    
    async def shutdown(self) -> None:
        """Shutdown the performance manager and cleanup resources."""
        await self.cache.stop_background_tasks()
        if self.config.enable_persistence:
            await self.cache._save_to_disk()
        logger.info("PerformanceManager shutdown")
    
    def cache_key(self, operation: str, **kwargs) -> str:
        """
        Generate a cache key for an operation with parameters.
        
        Args:
            operation: Operation name
            **kwargs: Operation parameters
            
        Returns:
            Cache key string
        """
        # Create a deterministic key from operation and sorted parameters
        param_str = json.dumps(kwargs, sort_keys=True, default=str)
        key_data = f"{operation}:{param_str}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]
    
    async def get_or_compute(
        self, 
        operation: str, 
        compute_func: Callable[[], Any],
        ttl: Optional[int] = None,
        group: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Get result from cache or compute and cache it.
        
        Args:
            operation: Operation name for cache key generation
            compute_func: Function to compute result if not cached
            ttl: Cache TTL in seconds
            group: Invalidation group
            **kwargs: Parameters for cache key generation
            
        Returns:
            Cached or computed result
        """
        cache_key = self.cache_key(operation, **kwargs)
        
        # Try to get from cache first
        result = await self.cache.get(cache_key)
        
        if result is not None:
            return result
        
        # Compute result and cache it
        start_time = time.time()
        
        try:
            if asyncio.iscoroutinefunction(compute_func):
                result = await compute_func()
            else:
                result = compute_func()
            
            # Record performance metrics
            duration = time.time() - start_time
            self._record_operation_time(operation, duration)
            
            # Cache the result
            await self.cache.set(cache_key, result, ttl=ttl, group=group)
            
            return result
            
        except Exception as e:
            # Record failed operation
            duration = time.time() - start_time
            self._record_operation_time(f"{operation}_failed", duration)
            raise
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate cache entries matching a pattern.
        
        Args:
            pattern: Pattern to match against cache keys
            
        Returns:
            Number of entries invalidated
        """
        # This is a simple implementation - in production you might want
        # more sophisticated pattern matching
        count = 0
        keys_to_remove = []
        
        # Get all cache keys (this is expensive, but necessary for pattern matching)
        with self.cache._lock:
            for key in self.cache._cache.keys():
                if pattern in key:
                    keys_to_remove.append(key)
        
        # Remove matching keys
        for key in keys_to_remove:
            if await self.cache.delete(key):
                count += 1
        
        return count
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        cache_stats = self.cache.get_statistics()
        
        # Calculate operation statistics
        operation_stats = {}
        for operation, times in self._operation_times.items():
            if times:
                operation_stats[operation] = {
                    "count": len(times),
                    "avg_time_ms": sum(times) * 1000 / len(times),
                    "min_time_ms": min(times) * 1000,
                    "max_time_ms": max(times) * 1000,
                    "total_time_ms": sum(times) * 1000
                }
        
        return {
            "cache": {
                "hits": cache_stats.hits,
                "misses": cache_stats.misses,
                "hit_rate": cache_stats.hit_rate,
                "total_entries": cache_stats.total_entries,
                "memory_mb": cache_stats.total_memory_bytes / 1024 / 1024,
                "evictions": cache_stats.evictions,
                "expired_evictions": cache_stats.expired_evictions
            },
            "operations": operation_stats,
            "system": {
                "memory_usage_mb": psutil.Process().memory_info().rss / 1024 / 1024,
                "cpu_percent": psutil.Process().cpu_percent()
            }
        }
    
    def _record_operation_time(self, operation: str, duration: float) -> None:
        """Record execution time for an operation."""
        if operation not in self._operation_times:
            self._operation_times[operation] = []
            self._operation_counts[operation] = 0
        
        self._operation_times[operation].append(duration)
        self._operation_counts[operation] += 1
        
        # Keep only last 100 measurements per operation to prevent memory growth
        if len(self._operation_times[operation]) > 100:
            self._operation_times[operation] = self._operation_times[operation][-50:]
    
    async def _log_cache_events(self, event_type: str, data: Any) -> None:
        """Log cache events for monitoring."""
        if event_type in ["cache_hit", "cache_miss"]:
            # Only log cache operations at debug level to avoid noise
            logger.debug(f"Cache {event_type}: {data}")
        else:
            logger.info(f"Cache {event_type}: {data}")


# Decorator for caching function results
def cached(
    ttl: Optional[int] = None,
    group: Optional[str] = None,
    key_func: Optional[Callable[..., str]] = None,
    manager: Optional[PerformanceManager] = None
):
    """
    Decorator to cache function results.
    
    Args:
        ttl: Cache TTL in seconds
        group: Invalidation group
        key_func: Custom key generation function
        manager: Performance manager instance (uses global if None)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            perf_manager = manager or get_global_performance_manager()
            
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default key generation using function name and parameters
                cache_key = perf_manager.cache_key(func.__name__, args=args, kwargs=kwargs)
            
            # Try cache first
            result = await perf_manager.cache.get(cache_key)
            if result is not None:
                return result
            
            # Compute and cache
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            await perf_manager.cache.set(cache_key, result, ttl=ttl, group=group)
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            # For synchronous functions, we need to run the async cache operations
            # This requires an event loop to be running
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_wrapper(*args, **kwargs))
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


# Global performance manager instance
_global_performance_manager: Optional[PerformanceManager] = None


def get_global_performance_manager() -> PerformanceManager:
    """Get or create the global performance manager instance."""
    global _global_performance_manager
    if _global_performance_manager is None:
        _global_performance_manager = PerformanceManager()
    return _global_performance_manager


def set_global_performance_manager(manager: PerformanceManager) -> None:
    """Set the global performance manager instance."""
    global _global_performance_manager
    _global_performance_manager = manager


# Utility functions for cache warming and preloading
async def warm_cache_for_paths(
    performance_manager: PerformanceManager,
    paths: List[Union[str, Path]],
    operations: List[str] = None
) -> None:
    """
    Warm cache by pre-computing results for common operations on given paths.
    
    Args:
        performance_manager: Performance manager instance
        paths: List of file/directory paths to warm cache for
        operations: List of operations to pre-compute (default: common operations)
    """
    if operations is None:
        operations = ["search", "scan", "call_graph"]
    
    logger.info(f"Warming cache for {len(paths)} paths with {len(operations)} operations")
    
    # This would be implemented based on specific caching needs
    # For now, it's a placeholder for the warming logic
    for path in paths:
        for operation in operations:
            try:
                # Pre-compute and cache common queries for this path
                cache_key = performance_manager.cache_key(operation, path=str(path))
                # The actual warming logic would depend on the specific operations
                logger.debug(f"Cache warming: {operation} on {path}")
            except Exception as e:
                logger.warning(f"Cache warming failed for {operation} on {path}: {e}")


# ===================================
# CONCURRENT REQUEST HANDLING SYSTEM
# ===================================

@dataclass
class ConcurrencyConfig:
    """Configuration for concurrent request handling and rate limiting."""
    
    # Global concurrency limits
    max_concurrent_requests: int = 50
    max_concurrent_search: int = 20
    max_concurrent_scan: int = 10
    max_concurrent_run: int = 5
    max_concurrent_call_graph: int = 15
    
    # Queue configuration
    max_queue_size: int = 200
    queue_timeout: float = 30.0
    priority_boost_cache_hits: bool = True
    
    # Rate limiting (requests per minute)
    global_rate_limit: int = 1000
    search_rate_limit: int = 300
    scan_rate_limit: int = 120
    run_rate_limit: int = 60
    call_graph_rate_limit: int = 180
    
    # Per-user rate limiting
    per_user_rate_limit: int = 100
    per_ip_rate_limit: int = 200
    
    # Distributed lock configuration
    lock_timeout: float = 30.0
    lock_retry_delay: float = 0.1
    max_lock_retries: int = 50
    
    # Fair resource allocation
    enable_per_user_limits: bool = True
    enable_priority_queue: bool = True
    cache_hit_priority_boost: int = 2


@dataclass
class StreamingConfig:
    """Configuration for streaming large result sets."""
    
    # Chunk size settings
    default_chunk_size: int = 1000        # Default items per chunk
    max_chunk_size: int = 5000           # Maximum items per chunk
    min_chunk_size: int = 100            # Minimum items per chunk
    
    # Buffer and memory settings
    max_buffer_size_mb: int = 100        # Maximum buffer size in MB
    memory_check_interval: int = 50       # Check memory every N chunks
    
    # Timing settings
    chunk_processing_delay: float = 0.001 # Delay between chunks (seconds)
    chunk_timeout: float = 15.0          # Timeout for processing a single chunk
    total_stream_timeout: float = 600.0   # Total timeout for entire stream
    
    # Flow control settings
    backpressure_threshold: int = 3       # Max concurrent streams before backpressure
    enable_backpressure: bool = True     # Enable flow control
    enable_buffering: bool = True        # Enable smart buffering
    enable_compression: bool = False     # Enable response compression


@dataclass
class MemoryConfig:
    """Configuration for memory monitoring and optimization."""
    
    # Memory monitoring settings
    enable_detailed_monitoring: bool = True
    enable_leak_detection: bool = True
    enable_tracemalloc: bool = True
    tracemalloc_limit: int = 25  # Top N memory allocations to track
    
    # Memory thresholds (in MB)
    warning_threshold_mb: int = 512     # Warn when memory usage exceeds this
    critical_threshold_mb: int = 1024   # Critical memory usage threshold
    max_memory_mb: int = 2048           # Maximum allowed memory usage
    
    # Monitoring intervals (in seconds)
    monitoring_interval: int = 30       # General monitoring interval
    leak_check_interval: int = 300      # Memory leak detection interval
    gc_optimization_interval: int = 60  # Garbage collection optimization interval
    
    # Memory optimization settings
    enable_aggressive_gc: bool = False   # Enable aggressive garbage collection
    gc_threshold_adjustment: bool = True # Adjust GC thresholds dynamically
    
    # Alert settings
    enable_memory_alerts: bool = True    # Enable memory usage alerts
    alert_cooldown: int = 300           # Cooldown between alerts (seconds)


@dataclass
class MetricsConfig:
    """Configuration for performance metrics collection and adaptive timeouts."""
    
    # Metrics collection settings
    enable_detailed_metrics: bool = True
    enable_adaptive_timeouts: bool = True
    metrics_window_size: int = 1000           # Number of recent measurements to keep
    percentile_calculation_interval: int = 60  # Recalculate percentiles every N seconds
    
    # Latency tracking settings
    latency_buckets: List[float] = field(default_factory=lambda: [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000])  # ms
    track_percentiles: List[int] = field(default_factory=lambda: [50, 90, 95, 99])
    
    # Timeout adaptation settings
    base_timeout_ms: float = 10000            # Base timeout (10 seconds)
    min_timeout_ms: float = 1000              # Minimum timeout (1 second)
    max_timeout_ms: float = 60000             # Maximum timeout (60 seconds)
    timeout_percentile: int = 95              # Use P95 latency for timeout calculation
    timeout_safety_factor: float = 1.5       # Multiply P95 by this factor
    
    # System load adaptation settings
    enable_load_aware_timeouts: bool = True
    cpu_threshold_high: float = 80.0          # High CPU usage threshold (%)
    memory_threshold_high: float = 85.0       # High memory usage threshold (%)
    load_factor_high: float = 0.8             # Reduce timeout by this factor under high load
    load_factor_low: float = 1.2              # Increase timeout by this factor under low load
    
    # Throughput monitoring settings
    throughput_window_seconds: int = 60       # Calculate throughput over this window
    error_rate_window_seconds: int = 300      # Calculate error rate over this window


@dataclass
class TokenBucketRateLimit:
    """Token bucket rate limiter for smooth request rate control."""
    
    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    
    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.time()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """
        Acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens were acquired, False if bucket is empty
        """
        now = time.time()
        
        # Refill bucket based on elapsed time
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    async def wait_for_tokens(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Wait for tokens to become available.
        
        Args:
            tokens: Number of tokens needed
            timeout: Maximum time to wait
            
        Returns:
            True if tokens were acquired, False if timeout
        """
        start_time = time.time()
        
        while True:
            if await self.acquire(tokens):
                return True
            
            if timeout and (time.time() - start_time) >= timeout:
                return False
            
            # Calculate wait time until next token is available
            wait_time = min(0.1, tokens / self.refill_rate)
            await asyncio.sleep(wait_time)


@dataclass
class RequestPriority:
    """Request priority information for queue ordering."""
    
    level: int  # Lower numbers = higher priority
    cache_hit: bool = False
    user_id: Optional[str] = None
    submitted_at: float = field(default_factory=time.time)
    
    def __lt__(self, other: 'RequestPriority') -> bool:
        """Define ordering for priority queue."""
        # First by priority level (lower = higher priority)
        if self.level != other.level:
            return self.level < other.level
        
        # Cache hits get priority boost
        if self.cache_hit != other.cache_hit:
            return self.cache_hit > other.cache_hit
        
        # Finally by submission time (FIFO)
        return self.submitted_at < other.submitted_at


@dataclass
class QueuedRequest:
    """A request waiting in the processing queue."""
    
    priority: RequestPriority
    operation: str
    compute_func: Callable[[], Any]
    future: asyncio.Future
    request_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class DistributedLock:
    """
    Distributed lock implementation for preventing cache stampede.
    Uses in-memory locks for single-process deployment.
    Can be extended to use Redis for multi-process deployment.
    """
    
    _locks: Dict[str, asyncio.Lock] = {}
    _lock_creation_lock = asyncio.Lock()
    
    @classmethod
    async def acquire(cls, key: str, timeout: float = 30.0) -> bool:
        """
        Acquire a distributed lock for the given key.
        
        Args:
            key: Lock identifier
            timeout: Maximum time to wait for lock
            
        Returns:
            True if lock acquired, False if timeout
        """
        async with cls._lock_creation_lock:
            if key not in cls._locks:
                cls._locks[key] = asyncio.Lock()
        
        lock = cls._locks[key]
        
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    @classmethod
    def release(cls, key: str) -> None:
        """Release the distributed lock for the given key."""
        if key in cls._locks:
            cls._locks[key].release()


class ConcurrentRequestManager:
    """
    Manages concurrent request handling, rate limiting, and fair resource allocation.
    Integrates with PerformanceManager for cache-aware concurrency optimization.
    """
    
    def __init__(self, config: ConcurrencyConfig):
        self.config = config
        self._logger = logging.getLogger(__name__)
        
        # Semaphores for concurrency control
        self._global_semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self._operation_semaphores = {
            'search': asyncio.Semaphore(config.max_concurrent_search),
            'scan': asyncio.Semaphore(config.max_concurrent_scan),
            'run': asyncio.Semaphore(config.max_concurrent_run),
            'call_graph': asyncio.Semaphore(config.max_concurrent_call_graph),
        }
        
        # Rate limiters using token bucket algorithm
        self._global_rate_limiter = TokenBucketRateLimit(
            capacity=config.global_rate_limit,
            refill_rate=config.global_rate_limit / 60.0  # per second
        )
        
        self._operation_rate_limiters = {
            'search': TokenBucketRateLimit(
                capacity=config.search_rate_limit,
                refill_rate=config.search_rate_limit / 60.0
            ),
            'scan': TokenBucketRateLimit(
                capacity=config.scan_rate_limit,
                refill_rate=config.scan_rate_limit / 60.0
            ),
            'run': TokenBucketRateLimit(
                capacity=config.run_rate_limit,
                refill_rate=config.run_rate_limit / 60.0
            ),
            'call_graph': TokenBucketRateLimit(
                capacity=config.call_graph_rate_limit,
                refill_rate=config.call_graph_rate_limit / 60.0
            ),
        }
        
        # Per-user and per-IP rate limiters
        self._user_rate_limiters: Dict[str, TokenBucketRateLimit] = defaultdict(
            lambda: TokenBucketRateLimit(
                capacity=config.per_user_rate_limit,
                refill_rate=config.per_user_rate_limit / 60.0
            )
        )
        
        self._ip_rate_limiters: Dict[str, TokenBucketRateLimit] = defaultdict(
            lambda: TokenBucketRateLimit(
                capacity=config.per_ip_rate_limit,
                refill_rate=config.per_ip_rate_limit / 60.0
            )
        )
        
        # Per-user semaphores for fair resource allocation
        self._user_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(max(1, config.max_concurrent_requests // 10))
        )
        
        # Request queue with priority support
        self._request_queue = asyncio.PriorityQueue(maxsize=config.max_queue_size)
        self._active_requests: Dict[str, QueuedRequest] = {}
        self._request_counter = 0
        
        # Statistics
        self._stats = {
            'requests_queued': 0,
            'requests_processed': 0,
            'requests_failed': 0,
            'requests_rate_limited': 0,
            'requests_timeout': 0,
            'average_queue_time': 0.0,
            'concurrent_requests': 0,
            'cache_hit_requests': 0,
        }
        
        # Background task for processing queue
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
    async def start(self) -> None:
        """Start the concurrent request manager."""
        if self._queue_processor_task is None:
            self._queue_processor_task = asyncio.create_task(self._process_queue())
            self._logger.info("Concurrent request manager started")
    
    async def shutdown(self) -> None:
        """Shutdown the concurrent request manager."""
        self._shutdown_event.set()
        
        if self._queue_processor_task and not self._queue_processor_task.done():
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all pending requests
        for request in self._active_requests.values():
            if not request.future.done():
                request.future.cancel()
        
        self._logger.info("Concurrent request manager shutdown complete")
    
    async def execute_with_concurrency_control(
        self,
        operation: str,
        compute_func: Callable[[], Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        priority: int = 5,
        cache_hit: bool = False,
        timeout: Optional[float] = None,
        **metadata
    ) -> Any:
        """
        Execute a function with full concurrency control including rate limiting,
        queue management, and fair resource allocation.
        
        Args:
            operation: Type of operation (search, scan, run, call_graph)
            compute_func: Function to execute
            user_id: User identifier for per-user limits
            ip_address: IP address for per-IP limits
            priority: Request priority (lower = higher priority)
            cache_hit: Whether this is a cache hit (gets priority boost)
            timeout: Maximum execution time
            **metadata: Additional request metadata
            
        Returns:
            Result of compute_func
            
        Raises:
            asyncio.TimeoutError: If request times out
            ValueError: If rate limited or queue full
        """
        request_id = f"{operation}_{self._request_counter}"
        self._request_counter += 1
        
        # Check rate limits first
        if not await self._check_rate_limits(operation, user_id, ip_address):
            self._stats['requests_rate_limited'] += 1
            raise ValueError(f"Rate limit exceeded for operation: {operation}")
        
        # Apply priority boost for cache hits
        effective_priority = priority
        if cache_hit and self.config.priority_boost_cache_hits:
            effective_priority = max(1, priority - self.config.cache_hit_priority_boost)
        
        # Create request priority
        request_priority = RequestPriority(
            level=effective_priority,
            cache_hit=cache_hit,
            user_id=user_id
        )
        
        # Create future for result
        result_future = asyncio.Future()
        
        # Create queued request
        queued_request = QueuedRequest(
            priority=request_priority,
            operation=operation,
            compute_func=compute_func,
            future=result_future,
            request_id=request_id,
            metadata={
                'user_id': user_id,
                'ip_address': ip_address,
                'timeout': timeout,
                **metadata
            }
        )
        
        # Add to queue
        try:
            self._request_queue.put_nowait((request_priority, queued_request))
            self._active_requests[request_id] = queued_request
            self._stats['requests_queued'] += 1
            
            self._logger.debug(f"Queued request {request_id} with priority {effective_priority}")
            
        except asyncio.QueueFull:
            raise ValueError("Request queue is full")
        
        # Wait for result
        try:
            if timeout:
                result = await asyncio.wait_for(result_future, timeout=timeout)
            else:
                result = await result_future
            
            self._stats['requests_processed'] += 1
            if cache_hit:
                self._stats['cache_hit_requests'] += 1
            
            return result
            
        except asyncio.TimeoutError:
            self._stats['requests_timeout'] += 1
            # Clean up
            if request_id in self._active_requests:
                del self._active_requests[request_id]
            raise
        
        except Exception:
            self._stats['requests_failed'] += 1
            raise
        
        finally:
            # Clean up
            if request_id in self._active_requests:
                del self._active_requests[request_id]
    
    async def _check_rate_limits(
        self,
        operation: str,
        user_id: Optional[str],
        ip_address: Optional[str]
    ) -> bool:
        """Check if request is within rate limits."""
        
        # Check global rate limit
        if not await self._global_rate_limiter.acquire():
            return False
        
        # Check operation-specific rate limit
        if operation in self._operation_rate_limiters:
            if not await self._operation_rate_limiters[operation].acquire():
                return False
        
        # Check per-user rate limit
        if user_id and self.config.enable_per_user_limits:
            if not await self._user_rate_limiters[user_id].acquire():
                return False
        
        # Check per-IP rate limit
        if ip_address:
            if not await self._ip_rate_limiters[ip_address].acquire():
                return False
        
        return True
    
    async def _process_queue(self) -> None:
        """Background task to process the request queue."""
        self._logger.info("Starting request queue processor")
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for a request with timeout
                try:
                    priority, request = await asyncio.wait_for(
                        self._request_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Calculate queue time
                queue_time = time.time() - request.priority.submitted_at
                self._stats['average_queue_time'] = (
                    self._stats['average_queue_time'] * 0.9 + queue_time * 0.1
                )
                
                # Process the request
                asyncio.create_task(self._execute_request(request))
                
            except Exception as e:
                self._logger.error(f"Error in queue processor: {e}")
                await asyncio.sleep(0.1)
    
    async def _execute_request(self, request: QueuedRequest) -> None:
        """Execute a single request with concurrency controls."""
        try:
            self._stats['concurrent_requests'] += 1
            
            # Acquire global semaphore
            async with self._global_semaphore:
                
                # Acquire operation-specific semaphore
                operation_semaphore = self._operation_semaphores.get(request.operation)
                if operation_semaphore:
                    async with operation_semaphore:
                        
                        # Acquire user-specific semaphore for fair allocation
                        user_id = request.metadata.get('user_id')
                        if user_id and self.config.enable_per_user_limits:
                            async with self._user_semaphores[user_id]:
                                result = await self._execute_with_lock(request)
                        else:
                            result = await self._execute_with_lock(request)
                else:
                    result = await self._execute_with_lock(request)
            
            # Set result
            if not request.future.done():
                request.future.set_result(result)
            
        except Exception as e:
            # Set exception
            if not request.future.done():
                request.future.set_exception(e)
            
            self._logger.error(f"Error executing request {request.request_id}: {e}")
        
        finally:
            self._stats['concurrent_requests'] -= 1
    
    async def _execute_with_lock(self, request: QueuedRequest) -> Any:
        """Execute request with distributed lock for cache stampede prevention."""
        
        # Generate lock key based on operation and parameters
        lock_key = f"{request.operation}_{hash(str(request.metadata))}"
        
        # Try to acquire distributed lock
        lock_acquired = await DistributedLock.acquire(
            lock_key,
            timeout=self.config.lock_timeout
        )
        
        try:
            if lock_acquired:
                # Execute the function
                result = await request.compute_func()
                return result
            else:
                # Could not acquire lock - this shouldn't happen often
                # but we'll execute anyway with a warning
                self._logger.warning(f"Could not acquire lock for {lock_key}, executing anyway")
                result = await request.compute_func()
                return result
        
        finally:
            if lock_acquired:
                DistributedLock.release(lock_key)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current concurrency statistics."""
        return {
            **self._stats,
            'queue_size': self._request_queue.qsize(),
            'active_requests': len(self._active_requests),
            'max_queue_size': self.config.max_queue_size,
            'global_concurrent_limit': self.config.max_concurrent_requests,
        }
    
    async def invalidate_user_cache(self, user_id: str) -> None:
        """Invalidate all cache entries for a specific user."""
        # Remove user from rate limiter cache to reset limits
        if user_id in self._user_rate_limiters:
            del self._user_rate_limiters[user_id]
        
        if user_id in self._user_semaphores:
            del self._user_semaphores[user_id]
        
        self._logger.info(f"Invalidated cache and limits for user: {user_id}")


# =============================
# ENHANCED PERFORMANCE MANAGER
# =============================

class EnhancedPerformanceManager(PerformanceManager):
    """
    Enhanced PerformanceManager with concurrent request handling, rate limiting, result streaming, 
    advanced memory monitoring, and comprehensive performance metrics collection with adaptive timeouts.
    
    Combines caching with intelligent concurrency management, streaming for large outputs, 
    comprehensive memory optimization, and performance-aware adaptive behavior.
    """
    
    def __init__(self, cache_config: CacheConfig, concurrency_config: ConcurrencyConfig, 
                 streaming_config: Optional[StreamingConfig] = None, 
                 memory_config: Optional[MemoryConfig] = None,
                 metrics_config: Optional[MetricsConfig] = None):
        super().__init__(cache_config)
        self._concurrency_config = concurrency_config
        self._concurrent_manager = ConcurrentRequestManager(concurrency_config)
        
        # Initialize streaming manager (will be created when classes are defined)
        self._streaming_config = streaming_config or StreamingConfig()
        self._streaming_manager = None  # Will be initialized in start()
        
        # Initialize memory monitor (will be created when classes are defined)
        self._memory_config = memory_config or MemoryConfig()
        self._memory_monitor = None  # Will be initialized in start()
        
        # Initialize performance metrics collector (will be created when classes are defined)
        self._metrics_config = metrics_config or MetricsConfig()
        self._metrics_collector = None  # Will be initialized in start()
        
        # Background tasks
        self._monitoring_tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        
    async def start(self) -> None:
        """Start all performance management subsystems."""
        # Note: Base class has no start() method, initializing directly
        
        # Initialize components that depend on classes defined later in the file
        if self._streaming_manager is None:
            from .performance import StreamingManager, set_streaming_manager
            self._streaming_manager = StreamingManager(self._streaming_config)
            set_streaming_manager(self._streaming_manager)
        
        if self._memory_monitor is None:
            from .performance import MemoryMonitor, set_memory_monitor
            self._memory_monitor = MemoryMonitor(self._memory_config)
            set_memory_monitor(self._memory_monitor)
        
        if self._metrics_collector is None:
            from .performance import PerformanceMetricsCollector, set_metrics_collector
            self._metrics_collector = PerformanceMetricsCollector(self._metrics_config)
            set_metrics_collector(self._metrics_collector)
        
        await self._memory_monitor.start()
        
        # Start system metrics monitoring task
        monitoring_task = asyncio.create_task(self._system_metrics_monitoring_loop())
        self._monitoring_tasks.append(monitoring_task)
        
        # Start metrics cleanup task
        cleanup_task = asyncio.create_task(self._metrics_cleanup_loop())
        self._monitoring_tasks.append(cleanup_task)
        
        logger.info("Enhanced performance manager started with all subsystems")
    
    async def shutdown(self) -> None:
        """Shutdown all performance management subsystems."""
        self._shutdown_event.set()
        
        # Cancel monitoring tasks
        for task in self._monitoring_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
        
        if self._memory_monitor:
            await self._memory_monitor.shutdown()
        await super().shutdown()
        
        logger.info("Enhanced performance manager shutdown complete")
    
    async def _system_metrics_monitoring_loop(self) -> None:
        """Background task to update system metrics for load-aware behavior."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Skip if components aren't initialized yet
                    if not self._memory_monitor or not self._metrics_collector:
                        await asyncio.sleep(30)
                        continue
                    
                    # Get system metrics
                    memory_snapshot = self._memory_monitor.get_current_usage()
                    cpu_usage = memory_snapshot.cpu_percent if hasattr(memory_snapshot, 'cpu_percent') else 0.0
                    memory_usage = memory_snapshot.memory_percent
                    
                    # Get active requests and queue length from concurrent manager
                    active_requests = len(self._concurrent_manager._active_requests) if hasattr(self._concurrent_manager, '_active_requests') else 0
                    queue_length = self._concurrent_manager._request_queue.qsize() if hasattr(self._concurrent_manager, '_request_queue') else 0
                    
                    # Update metrics collector with system metrics
                    self._metrics_collector.update_system_metrics(
                        cpu_usage=cpu_usage,
                        memory_usage=memory_usage,
                        active_requests=active_requests,
                        queue_length=queue_length
                    )
                    
                    # Sleep for monitoring interval
                    await asyncio.sleep(30)  # Update every 30 seconds
                    
                except Exception as e:
                    logger.error(f"Error in system metrics monitoring: {e}")
                    await asyncio.sleep(30)
                    
        except asyncio.CancelledError:
            logger.info("System metrics monitoring task cancelled")
    
    async def _metrics_cleanup_loop(self) -> None:
        """Background task to clean up old metrics data."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    if self._metrics_collector:
                        self._metrics_collector.cleanup_old_data()
                    await asyncio.sleep(300)  # Cleanup every 5 minutes
                except Exception as e:
                    logger.error(f"Error in metrics cleanup: {e}")
                    await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("Metrics cleanup task cancelled")
    
    async def get_or_compute_concurrent_with_metrics(
        self, 
        cache_key: str, 
        compute_func: Callable, 
        operation: str,
        ttl: Optional[int] = None,
        priority: int = 5,
        timeout: Optional[float] = None,
        user_context: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Enhanced version of get_or_compute_concurrent with comprehensive metrics collection and adaptive timeouts.
        
        This method combines caching, concurrency control, and performance metrics tracking.
        It uses adaptive timeouts based on historical performance data.
        """
        # Generate operation ID for tracking
        operation_id = f"{operation}_{int(time.time() * 1000)}_{id(cache_key)}"
        
        # Record operation start
        metrics_context = self._metrics_collector.record_operation_start(
            operation=operation,
            operation_id=operation_id,
            cache_key=cache_key,
            user_context=user_context,
            priority=priority
        )
        
        try:
            # Get adaptive timeout if not provided
            if timeout is None:
                timeout = self._metrics_collector.get_timeout_for_operation(operation)
            
            # Use the existing concurrent implementation with metrics context
            result = await self.get_or_compute_concurrent(
                cache_key=cache_key,
                compute_func=compute_func,
                ttl=ttl,
                priority=priority,
                timeout=timeout,
                user_context=user_context,
                **kwargs
            )
            
            # Record successful operation
            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=True,
                result_size=len(str(result)) if result is not None else 0,
                cache_hit=cache_key in self._cache._data if hasattr(self._cache, '_data') else False
            )
            
            return result
            
        except asyncio.TimeoutError as e:
            # Record timeout error
            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=False,
                error_type='timeout'
            )
            logger.warning(f"Operation {operation} timed out after {timeout}s: {e}")
            raise
            
        except Exception as e:
            # Record other errors
            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=False,
                error_type=type(e).__name__
            )
            logger.error(f"Operation {operation} failed: {e}")
            raise
    
    async def stream_large_results_concurrent_with_metrics(
        self,
        data_source: Any,
        operation: str,
        chunk_size: Optional[int] = None,
        user_context: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[Any]:
        """
        Enhanced streaming with performance metrics collection.
        
        Tracks streaming operations and adapts chunk sizes based on performance metrics.
        """
        operation_id = f"stream_{operation}_{int(time.time() * 1000)}"
        
        # Record streaming operation start
        metrics_context = self._metrics_collector.record_operation_start(
            operation=f"stream_{operation}",
            operation_id=operation_id,
            user_context=user_context
        )
        
        chunk_count = 0
        total_items = 0
        
        try:
            # Use adaptive chunk size based on system load if not provided
            if chunk_size is None:
                system_metrics = self._metrics_collector._system_metrics
                cpu_usage = system_metrics.get('cpu_usage', 0.0)
                memory_usage = system_metrics.get('memory_usage', 0.0)
                
                # Reduce chunk size under high load
                if cpu_usage > 80 or memory_usage > 80:
                    chunk_size = max(self._streaming_config.min_chunk_size, 
                                   self._streaming_config.default_chunk_size // 2)
                else:
                    chunk_size = self._streaming_config.default_chunk_size
            
            # Stream using the existing streaming infrastructure
            async for chunk in self.stream_large_results_concurrent(
                data_source=data_source,
                chunk_size=chunk_size,
                user_context=user_context,
                **kwargs
            ):
                chunk_count += 1
                total_items += len(chunk) if hasattr(chunk, '__len__') else 1
                yield chunk
            
            # Record successful streaming operation
            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=True,
                chunk_count=chunk_count,
                total_items=total_items,
                final_chunk_size=chunk_size
            )
            
        except Exception as e:
            # Record streaming error
            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=False,
                error_type=type(e).__name__,
                chunk_count=chunk_count,
                total_items=total_items
            )
            logger.error(f"Streaming operation {operation} failed: {e}")
            raise
    
    def get_metrics_collector(self) -> 'PerformanceMetricsCollector':
        """Get the performance metrics collector instance."""
        return self._metrics_collector
    
    def get_memory_monitor(self) -> 'MemoryMonitor':
        """Get the memory monitor instance."""
        return self._memory_monitor
    
    def get_streaming_manager(self) -> 'StreamingManager':
        """Get the streaming manager instance."""
        return self._streaming_manager
    
    def get_concurrent_manager(self) -> ConcurrentRequestManager:
        """Get the concurrent request manager instance."""
        return self._concurrent_manager
    
    async def get_comprehensive_performance_report(self) -> Dict[str, Any]:
        """
        Get a comprehensive performance report combining all subsystems.
        
        Returns detailed performance metrics, memory usage, cache statistics,
        streaming metrics, and system health indicators.
        """
        # Get metrics from all subsystems
        metrics_data = self._metrics_collector.get_all_metrics()
        memory_snapshot = self._memory_monitor.get_current_usage()
        cache_stats = self.get_cache_statistics()
        streaming_stats = self._streaming_manager.get_streaming_statistics()
        
        # Combine into comprehensive report
        return {
            'timestamp': time.time(),
            'performance_metrics': metrics_data,
            'memory_monitoring': {
                'current_snapshot': memory_snapshot.to_dict() if memory_snapshot else {},
                'monitoring_enabled': self._memory_config.enable_detailed_monitoring,
                'leak_detection_enabled': self._memory_config.enable_leak_detection
            },
            'cache_performance': cache_stats,
            'streaming_performance': streaming_stats,
            'concurrency_status': {
                'max_concurrent_requests': self._concurrency_config.max_concurrent_requests,
                'rate_limits': {
                    'global': self._concurrency_config.global_rate_limit,
                    'search': self._concurrency_config.search_rate_limit,
                    'scan': self._concurrency_config.scan_rate_limit
                }
            },
            'system_health': {
                'memory_pressure': memory_snapshot.memory_percent > 80 if memory_snapshot else False,
                'high_error_rate': metrics_data.get('global_metrics', {}).get('global_error_rate', 0) > 0.05,
                'high_timeout_rate': metrics_data.get('global_metrics', {}).get('global_timeout_rate', 0) > 0.02
            },
            'adaptive_behavior': {
                'adaptive_timeouts_enabled': self._metrics_config.enable_adaptive_timeouts,
                'load_aware_timeouts_enabled': self._metrics_config.enable_load_aware_timeouts,
                'current_adaptive_timeouts': {
                    op: self._metrics_collector.get_timeout_for_operation(op)
                    for op in ['ast_grep_search', 'ast_grep_scan', 'ast_grep_run']
                }
            }
        }
    
    async def get_performance_dashboard_summary(self) -> Dict[str, Any]:
        """Get a concise performance summary suitable for dashboards and monitoring."""
        return self._metrics_collector.get_performance_summary()
    
    async def force_comprehensive_cleanup(self) -> Dict[str, Any]:
        """Force comprehensive cleanup across all performance subsystems."""
        results = {}
        
        # Force memory cleanup
        try:
            memory_cleanup = await self.force_memory_cleanup()
            results['memory_cleanup'] = memory_cleanup
        except Exception as e:
            results['memory_cleanup'] = {'error': str(e)}
        
        # Force cache cleanup
        try:
            cache_cleanup = await self.force_cache_cleanup()
            results['cache_cleanup'] = cache_cleanup
        except Exception as e:
            results['cache_cleanup'] = {'error': str(e)}
        
        # Clean up metrics data
        try:
            self._metrics_collector.cleanup_old_data()
            results['metrics_cleanup'] = {'status': 'completed'}
        except Exception as e:
            results['metrics_cleanup'] = {'error': str(e)}
        
        # Force streaming cleanup
        try:
            streaming_cleanup = await self._streaming_manager.cleanup_resources()
            results['streaming_cleanup'] = streaming_cleanup
        except Exception as e:
            results['streaming_cleanup'] = {'error': str(e)}
        
        return {
            'timestamp': time.time(),
            'comprehensive_cleanup_results': results,
            'overall_status': 'completed' if all(
                'error' not in result for result in results.values()
            ) else 'partial_errors'
        }


@dataclass
class MemorySnapshot:
    """Snapshot of memory usage at a specific time."""
    
    timestamp: float
    rss_mb: float                    # Resident Set Size in MB
    vms_mb: float                    # Virtual Memory Size in MB
    percent: float                   # Memory usage percentage
    available_mb: float              # Available system memory in MB
    
    # Python-specific memory info
    python_objects: int              # Number of Python objects
    gc_counts: Tuple[int, int, int]  # GC generation counts
    
    # Process-specific info
    num_threads: int
    num_fds: int                     # Number of file descriptors
    
    # Memory growth indicators
    growth_rate_mb_per_min: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            'timestamp': self.timestamp,
            'rss_mb': self.rss_mb,
            'vms_mb': self.vms_mb,
            'percent': self.percent,
            'available_mb': self.available_mb,
            'python_objects': self.python_objects,
            'gc_counts': list(self.gc_counts),
            'num_threads': self.num_threads,
            'num_fds': self.num_fds,
            'growth_rate_mb_per_min': self.growth_rate_mb_per_min
        }


@dataclass
class MemoryAlert:
    """Memory usage alert information."""
    
    alert_type: str                  # warning, critical, leak_detected
    timestamp: float
    current_usage_mb: float
    threshold_mb: float
    message: str
    suggested_actions: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            'alert_type': self.alert_type,
            'timestamp': self.timestamp,
            'current_usage_mb': self.current_usage_mb,
            'threshold_mb': self.threshold_mb,
            'message': self.message,
            'suggested_actions': self.suggested_actions
        }


class MemoryMonitor:
    """
    Advanced memory monitoring system with leak detection and optimization.
    
    Features:
    - Real-time memory usage tracking
    - Memory leak detection using tracemalloc
    - Garbage collection optimization
    - Memory pressure alerts and adaptive behavior
    - Historical memory usage analysis
    """
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self._process = psutil.Process()
        self._snapshots: List[MemorySnapshot] = []
        self._alerts: List[MemoryAlert] = []
        self._last_alert_time: Dict[str, float] = {}
        
        # Monitoring tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._leak_detection_task: Optional[asyncio.Task] = None
        self._gc_optimization_task: Optional[asyncio.Task] = None
        
        # Memory tracking state
        self._baseline_memory: Optional[float] = None
        self._peak_memory: float = 0.0
        self._leak_candidates: Dict[str, int] = {}
        
        # Initialize tracemalloc if enabled
        if self.config.enable_tracemalloc and not tracemalloc.is_tracing():
            tracemalloc.start(self.config.tracemalloc_limit)
            logger.info("Memory tracing started with tracemalloc")
        
        logger.info(f"MemoryMonitor initialized with config: {config}")
    
    async def start(self) -> None:
        """Start memory monitoring tasks."""
        if self.config.enable_detailed_monitoring:
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        if self.config.enable_leak_detection:
            self._leak_detection_task = asyncio.create_task(self._leak_detection_loop())
        
        if self.config.gc_threshold_adjustment:
            self._gc_optimization_task = asyncio.create_task(self._gc_optimization_loop())
        
        # Take initial baseline measurement
        await self._take_snapshot()
        if self._snapshots:
            self._baseline_memory = self._snapshots[0].rss_mb
        
        logger.info("Memory monitoring started")
    
    async def stop(self) -> None:
        """Stop memory monitoring tasks."""
        tasks = [self._monitoring_task, self._leak_detection_task, self._gc_optimization_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        
        logger.info("Memory monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main memory monitoring loop."""
        while True:
            try:
                await asyncio.sleep(self.config.monitoring_interval)
                snapshot = await self._take_snapshot()
                await self._check_memory_thresholds(snapshot)
                await self._check_memory_growth(snapshot)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in memory monitoring loop: {e}")
                await asyncio.sleep(5)  # Short delay before retrying
    
    async def _leak_detection_loop(self) -> None:
        """Memory leak detection loop using tracemalloc."""
        while True:
            try:
                await asyncio.sleep(self.config.leak_check_interval)
                
                if tracemalloc.is_tracing():
                    await self._check_for_leaks()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in leak detection loop: {e}")
    
    async def _gc_optimization_loop(self) -> None:
        """Garbage collection optimization loop."""
        while True:
            try:
                await asyncio.sleep(self.config.gc_optimization_interval)
                await self._optimize_garbage_collection()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in GC optimization loop: {e}")
    
    async def _take_snapshot(self) -> MemorySnapshot:
        """Take a memory usage snapshot."""
        try:
            # Get process memory info
            memory_info = self._process.memory_info()
            memory_percent = self._process.memory_percent()
            
            # Get system memory info
            system_memory = psutil.virtual_memory()
            
            # Get process info
            num_threads = self._process.num_threads()
            try:
                num_fds = self._process.num_fds()
            except (psutil.AccessDenied, AttributeError):
                num_fds = 0  # Not available on all platforms
            
            # Get Python-specific info
            python_objects = len(gc.get_objects())
            gc_counts = gc.get_count()
            
            # Create snapshot
            snapshot = MemorySnapshot(
                timestamp=time.time(),
                rss_mb=memory_info.rss / 1024 / 1024,
                vms_mb=memory_info.vms / 1024 / 1024,
                percent=memory_percent,
                available_mb=system_memory.available / 1024 / 1024,
                python_objects=python_objects,
                gc_counts=gc_counts,
                num_threads=num_threads,
                num_fds=num_fds
            )
            
            # Calculate growth rate if we have previous snapshots
            if len(self._snapshots) > 0:
                prev_snapshot = self._snapshots[-1]
                time_diff = snapshot.timestamp - prev_snapshot.timestamp
                if time_diff > 0:
                    memory_diff = snapshot.rss_mb - prev_snapshot.rss_mb
                    snapshot.growth_rate_mb_per_min = (memory_diff / time_diff) * 60
            
            # Update peak memory
            self._peak_memory = max(self._peak_memory, snapshot.rss_mb)
            
            # Add to snapshots (keep last 100 snapshots)
            self._snapshots.append(snapshot)
            if len(self._snapshots) > 100:
                self._snapshots.pop(0)
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Error taking memory snapshot: {e}")
            # Return a basic snapshot with current time
            return MemorySnapshot(
                timestamp=time.time(),
                rss_mb=0.0, vms_mb=0.0, percent=0.0, available_mb=0.0,
                python_objects=0, gc_counts=(0, 0, 0),
                num_threads=0, num_fds=0
            )
    
    async def _check_memory_thresholds(self, snapshot: MemorySnapshot) -> None:
        """Check memory usage against configured thresholds."""
        current_time = time.time()
        
        # Check critical threshold
        if snapshot.rss_mb > self.config.critical_threshold_mb:
            if self._should_send_alert('critical', current_time):
                alert = MemoryAlert(
                    alert_type='critical',
                    timestamp=current_time,
                    current_usage_mb=snapshot.rss_mb,
                    threshold_mb=self.config.critical_threshold_mb,
                    message=f"Critical memory usage: {snapshot.rss_mb:.1f}MB (>{self.config.critical_threshold_mb}MB)",
                    suggested_actions=[
                        "Force garbage collection",
                        "Clear caches",
                        "Reduce concurrent operations",
                        "Consider restarting the application"
                    ]
                )
                await self._send_alert(alert)
                
                # Trigger emergency memory cleanup
                await self._emergency_memory_cleanup()
        
        # Check warning threshold
        elif snapshot.rss_mb > self.config.warning_threshold_mb:
            if self._should_send_alert('warning', current_time):
                alert = MemoryAlert(
                    alert_type='warning',
                    timestamp=current_time,
                    current_usage_mb=snapshot.rss_mb,
                    threshold_mb=self.config.warning_threshold_mb,
                    message=f"High memory usage: {snapshot.rss_mb:.1f}MB (>{self.config.warning_threshold_mb}MB)",
                    suggested_actions=[
                        "Monitor memory trends",
                        "Consider cache cleanup",
                        "Review recent operations"
                    ]
                )
                await self._send_alert(alert)
    
    async def _check_memory_growth(self, snapshot: MemorySnapshot) -> None:
        """Check for concerning memory growth patterns."""
        if snapshot.growth_rate_mb_per_min is None:
            return
        
        # Alert on rapid memory growth (>50MB/min)
        if snapshot.growth_rate_mb_per_min > 50:
            current_time = time.time()
            if self._should_send_alert('rapid_growth', current_time):
                alert = MemoryAlert(
                    alert_type='rapid_growth',
                    timestamp=current_time,
                    current_usage_mb=snapshot.rss_mb,
                    threshold_mb=50,  # MB/min threshold
                    message=f"Rapid memory growth: {snapshot.growth_rate_mb_per_min:.1f}MB/min",
                    suggested_actions=[
                        "Check for memory leaks",
                        "Review recent operations",
                        "Consider forcing garbage collection"
                    ]
                )
                await self._send_alert(alert)
    
    async def _check_for_leaks(self) -> None:
        """Check for potential memory leaks using tracemalloc."""
        if not tracemalloc.is_tracing():
            return
        
        try:
            # Get current tracemalloc snapshot
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            
            # Check for lines with significantly increased memory usage
            for stat in top_stats[:10]:  # Check top 10 memory allocations
                size_mb = stat.size / 1024 / 1024
                if size_mb > 10:  # Alert if any single allocation is >10MB
                    key = f"{stat.traceback.format()}"
                    
                    # Track this potential leak candidate
                    if key in self._leak_candidates:
                        self._leak_candidates[key] += 1
                    else:
                        self._leak_candidates[key] = 1
                    
                    # Alert if we've seen this allocation pattern multiple times
                    if self._leak_candidates[key] >= 3:
                        current_time = time.time()
                        if self._should_send_alert('leak_detected', current_time):
                            alert = MemoryAlert(
                                alert_type='leak_detected',
                                timestamp=current_time,
                                current_usage_mb=size_mb,
                                threshold_mb=10,
                                message=f"Potential memory leak detected: {size_mb:.1f}MB allocation",
                                suggested_actions=[
                                    "Review code at: " + stat.traceback.format()[-1],
                                    "Check for circular references",
                                    "Consider weak references",
                                    "Review object lifecycle management"
                                ]
                            )
                            await self._send_alert(alert)
                            
                            # Reset counter to avoid spam
                            self._leak_candidates[key] = 0
        
        except Exception as e:
            logger.error(f"Error checking for memory leaks: {e}")
    
    async def _optimize_garbage_collection(self) -> None:
        """Optimize garbage collection based on current memory usage."""
        try:
            # Get current memory snapshot
            if not self._snapshots:
                return
            
            current_snapshot = self._snapshots[-1]
            
            # Adjust GC thresholds based on memory pressure
            if current_snapshot.rss_mb > self.config.warning_threshold_mb:
                # Under memory pressure - more aggressive GC
                gc.set_threshold(500, 8, 8)  # More frequent GC
                if self.config.enable_aggressive_gc:
                    collected = gc.collect()
                    logger.debug(f"Aggressive GC collected {collected} objects")
            else:
                # Normal memory usage - standard GC
                gc.set_threshold(700, 10, 10)  # Standard GC frequency
            
            # Periodic full GC cycle
            if time.time() % 300 < self.config.gc_optimization_interval:  # Every 5 minutes
                collected = gc.collect()
                logger.debug(f"Periodic GC collected {collected} objects")
        
        except Exception as e:
            logger.error(f"Error optimizing garbage collection: {e}")
    
    async def _emergency_memory_cleanup(self) -> None:
        """Emergency memory cleanup when critical threshold is reached."""
        try:
            logger.warning("Executing emergency memory cleanup")
            
            # Force full garbage collection
            collected = gc.collect()
            logger.info(f"Emergency GC collected {collected} objects")
            
            # Clear any weak references that might be holding memory
            import weakref
            weakref.finalize(lambda: None, lambda: None)
            
            # Log memory usage after cleanup
            await asyncio.sleep(1)  # Give GC time to work
            post_cleanup_snapshot = await self._take_snapshot()
            logger.info(f"Memory after emergency cleanup: {post_cleanup_snapshot.rss_mb:.1f}MB")
            
        except Exception as e:
            logger.error(f"Error during emergency memory cleanup: {e}")
    
    def _should_send_alert(self, alert_type: str, current_time: float) -> bool:
        """Check if we should send an alert based on cooldown period."""
        if not self.config.enable_memory_alerts:
            return False
        
        last_alert = self._last_alert_time.get(alert_type, 0)
        if current_time - last_alert >= self.config.alert_cooldown:
            self._last_alert_time[alert_type] = current_time
            return True
        return False
    
    async def _send_alert(self, alert: MemoryAlert) -> None:
        """Send memory alert (log and store)."""
        self._alerts.append(alert)
        
        # Keep only last 50 alerts
        if len(self._alerts) > 50:
            self._alerts.pop(0)
        
        # Log the alert
        log_level = logging.WARNING if alert.alert_type == 'warning' else logging.CRITICAL
        logger.log(log_level, f"Memory Alert [{alert.alert_type}]: {alert.message}")
        
        for action in alert.suggested_actions:
            logger.log(log_level, f"  Suggested action: {action}")
    
    def get_current_usage(self) -> Optional[MemorySnapshot]:
        """Get the most recent memory usage snapshot."""
        return self._snapshots[-1] if self._snapshots else None
    
    def get_memory_history(self, limit: int = 20) -> List[MemorySnapshot]:
        """Get recent memory usage history."""
        return self._snapshots[-limit:] if self._snapshots else []
    
    def get_recent_alerts(self, limit: int = 10) -> List[MemoryAlert]:
        """Get recent memory alerts."""
        return self._alerts[-limit:] if self._alerts else []
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics."""
        if not self._snapshots:
            return {}
        
        current = self._snapshots[-1]
        
        # Calculate statistics
        recent_snapshots = self._snapshots[-10:] if len(self._snapshots) >= 10 else self._snapshots
        avg_memory = sum(s.rss_mb for s in recent_snapshots) / len(recent_snapshots)
        
        return {
            'current_usage_mb': current.rss_mb,
            'peak_usage_mb': self._peak_memory,
            'baseline_usage_mb': self._baseline_memory,
            'average_usage_mb': avg_memory,
            'memory_growth_rate_mb_per_min': current.growth_rate_mb_per_min,
            'python_objects': current.python_objects,
            'gc_counts': current.gc_counts,
            'num_threads': current.num_threads,
            'num_fds': current.num_fds,
            'alerts_count': len(self._alerts),
            'recent_alerts': [alert.to_dict() for alert in self._alerts[-5:]],
            'memory_pressure': 'critical' if current.rss_mb > self.config.critical_threshold_mb
                              else 'warning' if current.rss_mb > self.config.warning_threshold_mb
                              else 'normal'
        }
    
    async def force_cleanup(self) -> Dict[str, Any]:
        """Force memory cleanup and return cleanup results."""
        before_snapshot = await self._take_snapshot()
        
        # Force garbage collection
        collected = gc.collect()
        
        # Take after snapshot
        await asyncio.sleep(0.5)  # Give time for cleanup
        after_snapshot = await self._take_snapshot()
        
        cleanup_results = {
            'objects_collected': collected,
            'memory_before_mb': before_snapshot.rss_mb,
            'memory_after_mb': after_snapshot.rss_mb,
            'memory_freed_mb': before_snapshot.rss_mb - after_snapshot.rss_mb,
            'timestamp': time.time()
        }
        
        logger.info(f"Manual memory cleanup: {cleanup_results}")
        return cleanup_results


# Global memory monitor instance
_memory_monitor: Optional[MemoryMonitor] = None


def get_memory_monitor() -> Optional[MemoryMonitor]:
    """Get the global memory monitor instance."""
    return _memory_monitor


def set_memory_monitor(monitor: MemoryMonitor) -> None:
    """Set the global memory monitor instance."""
    global _memory_monitor
    _memory_monitor = monitor 


@dataclass 
class OperationMetrics:
    """Metrics for a specific operation type."""
    
    # Counters
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0
    
    # Latency tracking
    latency_measurements: deque = field(default_factory=lambda: deque(maxlen=1000))
    latency_buckets: Dict[float, int] = field(default_factory=dict)
    
    # Computed metrics
    current_percentiles: Dict[int, float] = field(default_factory=dict)
    current_timeout_ms: float = 10000
    average_latency_ms: float = 0.0
    
    # Throughput tracking
    request_timestamps: deque = field(default_factory=lambda: deque(maxlen=2000))
    current_throughput_rps: float = 0.0
    current_error_rate: float = 0.0
    
    # Timing
    last_percentile_calculation: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'timeout_requests': self.timeout_requests,
            'current_percentiles': self.current_percentiles,
            'current_timeout_ms': self.current_timeout_ms,
            'average_latency_ms': self.average_latency_ms,
            'current_throughput_rps': self.current_throughput_rps,
            'current_error_rate': self.current_error_rate,
            'latency_buckets': self.latency_buckets
        }


class PerformanceMetricsCollector:
    """
    Advanced performance metrics collector with adaptive timeout strategies.
    
    Features:
    - Latency tracking with percentile calculations
    - Throughput monitoring and error rate analysis  
    - Dynamic timeout adaptation based on historical performance
    - System load awareness for adaptive behavior
    - Per-operation metrics with histogram buckets
    """
    
    def __init__(self, config: MetricsConfig):
        self.config = config
        self._metrics: Dict[str, OperationMetrics] = {}
        self._lock = RLock()
        
        # System metrics
        self._system_metrics = {
            'cpu_usage': 0.0,
            'memory_usage': 0.0,
            'active_requests': 0,
            'queue_length': 0
        }
        
        # Global metrics
        self._global_start_time = time.time()
        self._last_cleanup_time = time.time()
        
        logger.info(f"PerformanceMetricsCollector initialized with config: {config}")
    
    def record_operation_start(self, operation: str, operation_id: str, **metadata) -> Dict[str, Any]:
        """Record the start of an operation and return context for tracking."""
        with self._lock:
            if operation not in self._metrics:
                self._metrics[operation] = OperationMetrics()
            
            metrics = self._metrics[operation]
            metrics.total_requests += 1
            
            # Add request timestamp for throughput calculation
            current_time = time.time()
            metrics.request_timestamps.append(current_time)
            
            # Return context for the operation
            return {
                'operation': operation,
                'operation_id': operation_id,
                'start_time': current_time,
                'metadata': metadata
            }
    
    def record_operation_end(self, context: Dict[str, Any], success: bool = True, 
                           error_type: Optional[str] = None, **result_metadata) -> None:
        """Record the completion of an operation."""
        operation = context['operation']
        start_time = context['start_time']
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        
        with self._lock:
            if operation not in self._metrics:
                return  # Operation not tracked
            
            metrics = self._metrics[operation]
            
            # Update counters
            if success:
                metrics.successful_requests += 1
            else:
                metrics.failed_requests += 1
                if error_type == 'timeout':
                    metrics.timeout_requests += 1
            
            # Record latency
            metrics.latency_measurements.append(duration_ms)
            
            # Update latency buckets
            for bucket in self.config.latency_buckets:
                if duration_ms <= bucket:
                    if bucket not in metrics.latency_buckets:
                        metrics.latency_buckets[bucket] = 0
                    metrics.latency_buckets[bucket] += 1
                    break
            
            # Update average latency
            if metrics.latency_measurements:
                metrics.average_latency_ms = statistics.mean(metrics.latency_measurements)
            
            # Periodically update computed metrics
            current_time = time.time()
            if (current_time - metrics.last_percentile_calculation) >= self.config.percentile_calculation_interval:
                self._update_computed_metrics(operation)
                metrics.last_percentile_calculation = current_time
    
    def _update_computed_metrics(self, operation: str) -> None:
        """Update computed metrics like percentiles, throughput, and timeouts."""
        metrics = self._metrics[operation]
        current_time = time.time()
        
        # Calculate percentiles
        if metrics.latency_measurements:
            sorted_latencies = sorted(metrics.latency_measurements)
            for percentile in self.config.track_percentiles:
                index = int((percentile / 100.0) * len(sorted_latencies))
                index = max(0, min(index - 1, len(sorted_latencies) - 1))
                metrics.current_percentiles[percentile] = sorted_latencies[index]
        
        # Calculate throughput (requests per second)
        throughput_window_start = current_time - self.config.throughput_window_seconds
        recent_requests = [ts for ts in metrics.request_timestamps if ts >= throughput_window_start]
        metrics.current_throughput_rps = len(recent_requests) / self.config.throughput_window_seconds
        
        # Calculate error rate
        error_window_start = current_time - self.config.error_rate_window_seconds
        recent_total = len([ts for ts in metrics.request_timestamps if ts >= error_window_start])
        recent_errors = metrics.failed_requests  # Simplified - could track per-window
        if recent_total > 0:
            metrics.current_error_rate = recent_errors / recent_total
        else:
            metrics.current_error_rate = 0.0
        
        # Update adaptive timeout
        if self.config.enable_adaptive_timeouts:
            metrics.current_timeout_ms = self._calculate_adaptive_timeout(operation)
    
    def _calculate_adaptive_timeout(self, operation: str) -> float:
        """Calculate adaptive timeout based on historical performance and system load."""
        metrics = self._metrics[operation]
        
        # Start with base timeout
        timeout_ms = self.config.base_timeout_ms
        
        # Use percentile-based calculation if we have enough data
        if (self.config.timeout_percentile in metrics.current_percentiles and 
            len(metrics.latency_measurements) >= 10):
            
            percentile_latency = metrics.current_percentiles[self.config.timeout_percentile]
            timeout_ms = percentile_latency * self.config.timeout_safety_factor
        
        # Adjust based on system load
        if self.config.enable_load_aware_timeouts:
            timeout_ms = self._adjust_timeout_for_load(timeout_ms)
        
        # Apply min/max bounds
        timeout_ms = max(self.config.min_timeout_ms, min(timeout_ms, self.config.max_timeout_ms))
        
        return timeout_ms
    
    def _adjust_timeout_for_load(self, base_timeout_ms: float) -> float:
        """Adjust timeout based on current system load."""
        cpu_usage = self._system_metrics.get('cpu_usage', 0.0)
        memory_usage = self._system_metrics.get('memory_usage', 0.0)
        
        # Under high load, reduce timeouts to fail fast
        if (cpu_usage > self.config.cpu_threshold_high or 
            memory_usage > self.config.memory_threshold_high):
            return base_timeout_ms * self.config.load_factor_high
        
        # Under low load, allow longer timeouts
        elif cpu_usage < 50.0 and memory_usage < 50.0:
            return base_timeout_ms * self.config.load_factor_low
        
        # Normal load, use base timeout
        return base_timeout_ms
    
    def update_system_metrics(self, cpu_usage: float, memory_usage: float, 
                            active_requests: int, queue_length: int) -> None:
        """Update system-level metrics for load-aware timeout adaptation."""
        with self._lock:
            self._system_metrics.update({
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'active_requests': active_requests,
                'queue_length': queue_length
            })
    
    def get_timeout_for_operation(self, operation: str) -> float:
        """Get the current adaptive timeout for an operation in seconds."""
        with self._lock:
            if operation in self._metrics:
                return self._metrics[operation].current_timeout_ms / 1000.0
            return self.config.base_timeout_ms / 1000.0
    
    def get_operation_metrics(self, operation: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive metrics for a specific operation."""
        with self._lock:
            if operation in self._metrics:
                return self._metrics[operation].to_dict()
            return None
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for all operations."""
        with self._lock:
            operations_metrics = {}
            for operation, metrics in self._metrics.items():
                operations_metrics[operation] = metrics.to_dict()
            
            # Calculate global metrics
            total_requests = sum(m.total_requests for m in self._metrics.values())
            total_successful = sum(m.successful_requests for m in self._metrics.values())
            total_failed = sum(m.failed_requests for m in self._metrics.values())
            total_timeouts = sum(m.timeout_requests for m in self._metrics.values())
            
            global_error_rate = total_failed / total_requests if total_requests > 0 else 0.0
            global_timeout_rate = total_timeouts / total_requests if total_requests > 0 else 0.0
            
            return {
                'timestamp': time.time(),
                'uptime_seconds': time.time() - self._global_start_time,
                'global_metrics': {
                    'total_requests': total_requests,
                    'successful_requests': total_successful,
                    'failed_requests': total_failed,
                    'timeout_requests': total_timeouts,
                    'global_error_rate': global_error_rate,
                    'global_timeout_rate': global_timeout_rate
                },
                'system_metrics': self._system_metrics.copy(),
                'operations': operations_metrics,
                'config': {
                    'adaptive_timeouts_enabled': self.config.enable_adaptive_timeouts,
                    'load_aware_timeouts_enabled': self.config.enable_load_aware_timeouts,
                    'base_timeout_ms': self.config.base_timeout_ms,
                    'timeout_percentile': self.config.timeout_percentile
                }
            }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a concise performance summary suitable for monitoring dashboards."""
        with self._lock:
            operations_summary = {}
            
            for operation, metrics in self._metrics.items():
                # Get key metrics
                p95_latency = metrics.current_percentiles.get(95, 0)
                p99_latency = metrics.current_percentiles.get(99, 0)
                
                operations_summary[operation] = {
                    'requests_per_second': metrics.current_throughput_rps,
                    'error_rate_percent': metrics.current_error_rate * 100,
                    'average_latency_ms': metrics.average_latency_ms,
                    'p95_latency_ms': p95_latency,
                    'p99_latency_ms': p99_latency,
                    'current_timeout_ms': metrics.current_timeout_ms,
                    'total_requests': metrics.total_requests
                }
            
            return {
                'timestamp': time.time(),
                'operations': operations_summary,
                'system_load': {
                    'cpu_usage_percent': self._system_metrics.get('cpu_usage', 0),
                    'memory_usage_percent': self._system_metrics.get('memory_usage', 0),
                    'active_requests': self._system_metrics.get('active_requests', 0),
                    'queue_length': self._system_metrics.get('queue_length', 0)
                }
            }
    
    def cleanup_old_data(self) -> None:
        """Clean up old metrics data to prevent memory bloat."""
        current_time = time.time()
        
        # Only cleanup every 5 minutes
        if current_time - self._last_cleanup_time < 300:
            return
        
        with self._lock:
            cutoff_time = current_time - (2 * self.config.throughput_window_seconds)
            
            for metrics in self._metrics.values():
                # Clean old timestamps
                while (metrics.request_timestamps and 
                       metrics.request_timestamps[0] < cutoff_time):
                    metrics.request_timestamps.popleft()
            
            self._last_cleanup_time = current_time
        
        logger.debug("Cleaned up old metrics data")


# Global metrics collector instance
_metrics_collector: Optional[PerformanceMetricsCollector] = None


def get_metrics_collector() -> Optional[PerformanceMetricsCollector]:
    """Get the global metrics collector instance."""
    return _metrics_collector


def set_metrics_collector(collector: PerformanceMetricsCollector) -> None:
    """Set the global metrics collector instance."""
    global _metrics_collector
    _metrics_collector = collector 


# Global streaming manager instance
_streaming_manager: Optional['StreamingManager'] = None

def get_streaming_manager() -> Optional['StreamingManager']:
    """Get the global streaming manager instance."""
    return _streaming_manager

def set_streaming_manager(manager: 'StreamingManager') -> None:
    """Set the global streaming manager instance."""
    global _streaming_manager
    _streaming_manager = manager


class StreamingManager:
    """Manages streaming of large result sets with chunking and backpressure control."""
    
    def __init__(self, config: StreamingConfig):
        self.config = config
        self._active_streams: Dict[str, asyncio.Task] = {}
        self._stream_stats: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
        
    async def stream_results(self, data_generator: AsyncIterator[Any], stream_id: str = None) -> AsyncIterator[List[Any]]:
        """Stream large result sets with chunking and backpressure control."""
        if stream_id is None:
            stream_id = f"stream_{int(time.time() * 1000)}"
            
        self._stream_stats[stream_id] = {
            "start_time": time.time(),
            "chunks_processed": 0,
            "items_processed": 0,
            "bytes_processed": 0
        }
        
        try:
            chunk = []
            async for item in data_generator:
                chunk.append(item)
                
                if len(chunk) >= self.config.default_chunk_size:
                    yield chunk
                    self._stream_stats[stream_id]["chunks_processed"] += 1
                    self._stream_stats[stream_id]["items_processed"] += len(chunk)
                    chunk = []
                    
                    # Add processing delay if configured
                    if self.config.chunk_processing_delay > 0:
                        await asyncio.sleep(self.config.chunk_processing_delay)
            
            # Yield remaining items
            if chunk:
                yield chunk
                self._stream_stats[stream_id]["chunks_processed"] += 1
                self._stream_stats[stream_id]["items_processed"] += len(chunk)
                
        except Exception as e:
            self.logger.error(f"Streaming error for {stream_id}: {e}")
            raise
        finally:
            self._stream_stats[stream_id]["end_time"] = time.time()

# Global performance manager instance
_performance_manager = None

def get_performance_manager():
    """Get the global performance manager instance."""
    global _performance_manager
    return _performance_manager
