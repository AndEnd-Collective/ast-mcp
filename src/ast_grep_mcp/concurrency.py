"""Concurrent request handling, rate limiting, and distributed locks.

Extracted from performance.py to provide focused concurrency management.
Uses TokenBucket from security.py as the canonical rate limiter instead
of the duplicate TokenBucketRateLimit that was in performance.py.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from .security import TokenBucket

logger = logging.getLogger(__name__)


def _create_token_bucket(capacity: int, refill_rate: float) -> TokenBucket:
    """Create a TokenBucket with sensible defaults for rate limiting.

    This helper bridges the gap between the old TokenBucketRateLimit
    (which auto-initialised tokens and last_refill) and the canonical
    TokenBucket from security.py which requires all fields explicitly.
    """
    return TokenBucket(
        capacity=capacity,
        tokens=float(capacity),
        refill_rate=refill_rate,
        last_refill=time.time(),
    )


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
class RequestPriority:
    """Request priority information for queue ordering."""

    level: int  # Lower numbers = higher priority
    cache_hit: bool = False
    user_id: Optional[str] = None
    submitted_at: float = field(default_factory=time.time)

    def __lt__(self, other: "RequestPriority") -> bool:
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
    """Distributed lock implementation for preventing cache stampede.

    Uses in-memory locks for single-process deployment.
    Can be extended to use Redis for multi-process deployment.
    """

    _locks: Dict[str, asyncio.Lock] = {}
    _lock_creation_lock = asyncio.Lock()

    @classmethod
    async def acquire(cls, key: str, timeout: float = 30.0) -> bool:
        """Acquire a distributed lock for the given key.

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

    @classmethod
    async def __aenter__(cls):
        """Not supported on class-level lock. Use acquire/release directly."""
        raise NotImplementedError(
            "DistributedLock uses class methods. "
            "Use await DistributedLock.acquire(key) / DistributedLock.release(key)."
        )

    @classmethod
    async def __aexit__(cls, exc_type, exc_val, exc_tb):  # noqa: ANN001
        raise NotImplementedError(
            "DistributedLock uses class methods. "
            "Use await DistributedLock.acquire(key) / DistributedLock.release(key)."
        )

    @classmethod
    def reset(cls) -> None:
        """Reset all locks. Intended for test cleanup only."""
        cls._locks.clear()


class ConcurrentRequestManager:
    """Manages concurrent request handling, rate limiting, and fair resource allocation.

    Integrates with PerformanceManager for cache-aware concurrency optimisation.
    Uses TokenBucket from security.py for rate limiting.
    """

    def __init__(self, config: ConcurrencyConfig):
        self.config = config
        self._logger = logging.getLogger(__name__)

        # Semaphores for concurrency control
        self._global_semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self._operation_semaphores = {
            "search": asyncio.Semaphore(config.max_concurrent_search),
            "scan": asyncio.Semaphore(config.max_concurrent_scan),
            "run": asyncio.Semaphore(config.max_concurrent_run),
            "call_graph": asyncio.Semaphore(config.max_concurrent_call_graph),
        }

        # Rate limiters using TokenBucket from security.py
        self._global_rate_limiter = _create_token_bucket(
            capacity=config.global_rate_limit,
            refill_rate=config.global_rate_limit / 60.0,
        )

        self._operation_rate_limiters = {
            "search": _create_token_bucket(
                capacity=config.search_rate_limit,
                refill_rate=config.search_rate_limit / 60.0,
            ),
            "scan": _create_token_bucket(
                capacity=config.scan_rate_limit,
                refill_rate=config.scan_rate_limit / 60.0,
            ),
            "run": _create_token_bucket(
                capacity=config.run_rate_limit,
                refill_rate=config.run_rate_limit / 60.0,
            ),
            "call_graph": _create_token_bucket(
                capacity=config.call_graph_rate_limit,
                refill_rate=config.call_graph_rate_limit / 60.0,
            ),
        }

        # Per-user and per-IP rate limiters
        self._user_rate_limiters: Dict[str, TokenBucket] = defaultdict(
            lambda: _create_token_bucket(
                capacity=config.per_user_rate_limit,
                refill_rate=config.per_user_rate_limit / 60.0,
            )
        )

        self._ip_rate_limiters: Dict[str, TokenBucket] = defaultdict(
            lambda: _create_token_bucket(
                capacity=config.per_ip_rate_limit,
                refill_rate=config.per_ip_rate_limit / 60.0,
            )
        )

        # Per-user semaphores for fair resource allocation
        self._user_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(max(1, config.max_concurrent_requests // 10))
        )

        # Request queue with priority support
        self._request_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=config.max_queue_size
        )
        self._active_requests: Dict[str, QueuedRequest] = {}
        self._request_counter = 0

        # Statistics
        self._stats: Dict[str, Any] = {
            "requests_queued": 0,
            "requests_processed": 0,
            "requests_failed": 0,
            "requests_rate_limited": 0,
            "requests_timeout": 0,
            "average_queue_time": 0.0,
            "concurrent_requests": 0,
            "cache_hit_requests": 0,
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
        **metadata: Any,
    ) -> Any:
        """Execute a function with full concurrency control.

        Includes rate limiting, queue management, and fair resource allocation.

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
        if not self._check_rate_limits(operation, user_id, ip_address):
            self._stats["requests_rate_limited"] += 1
            raise ValueError(f"Rate limit exceeded for operation: {operation}")

        # Apply priority boost for cache hits
        effective_priority = priority
        if cache_hit and self.config.priority_boost_cache_hits:
            effective_priority = max(1, priority - self.config.cache_hit_priority_boost)

        # Create request priority
        request_priority = RequestPriority(
            level=effective_priority,
            cache_hit=cache_hit,
            user_id=user_id,
        )

        # Create future for result
        result_future: asyncio.Future = asyncio.get_event_loop().create_future()

        # Create queued request
        queued_request = QueuedRequest(
            priority=request_priority,
            operation=operation,
            compute_func=compute_func,
            future=result_future,
            request_id=request_id,
            metadata={
                "user_id": user_id,
                "ip_address": ip_address,
                "timeout": timeout,
                **metadata,
            },
        )

        # Add to queue
        try:
            self._request_queue.put_nowait((request_priority, queued_request))
            self._active_requests[request_id] = queued_request
            self._stats["requests_queued"] += 1

            self._logger.debug(
                "Queued request %s with priority %s",
                request_id,
                effective_priority,
            )

        except asyncio.QueueFull:
            raise ValueError("Request queue is full")

        # Wait for result
        try:
            if timeout:
                result = await asyncio.wait_for(result_future, timeout=timeout)
            else:
                result = await result_future

            self._stats["requests_processed"] += 1
            if cache_hit:
                self._stats["cache_hit_requests"] += 1

            return result

        except asyncio.TimeoutError:
            self._stats["requests_timeout"] += 1
            # Clean up
            if request_id in self._active_requests:
                del self._active_requests[request_id]
            raise

        except Exception:
            self._stats["requests_failed"] += 1
            raise

        finally:
            # Clean up
            if request_id in self._active_requests:
                del self._active_requests[request_id]

    def _check_rate_limits(
        self,
        operation: str,
        user_id: Optional[str],
        ip_address: Optional[str],
    ) -> bool:
        """Check if request is within rate limits.

        Uses TokenBucket.consume() which is synchronous (refills and
        attempts to consume in one call).
        """
        # Check global rate limit
        if not self._global_rate_limiter.consume():
            return False

        # Check operation-specific rate limit
        if operation in self._operation_rate_limiters:
            if not self._operation_rate_limiters[operation].consume():
                return False

        # Check per-user rate limit
        if user_id and self.config.enable_per_user_limits:
            if not self._user_rate_limiters[user_id].consume():
                return False

        # Check per-IP rate limit
        if ip_address:
            if not self._ip_rate_limiters[ip_address].consume():
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
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                # Calculate queue time
                queue_time = time.time() - request.priority.submitted_at
                self._stats["average_queue_time"] = (
                    self._stats["average_queue_time"] * 0.9 + queue_time * 0.1
                )

                # Process the request
                asyncio.create_task(self._execute_request(request))

            except Exception as exc:
                self._logger.error("Error in queue processor: %s", exc)
                await asyncio.sleep(0.1)

    async def _execute_request(self, request: QueuedRequest) -> None:
        """Execute a single request with concurrency controls."""
        try:
            self._stats["concurrent_requests"] += 1

            # Acquire global semaphore
            async with self._global_semaphore:
                # Acquire operation-specific semaphore
                operation_semaphore = self._operation_semaphores.get(
                    request.operation
                )
                if operation_semaphore:
                    async with operation_semaphore:
                        # Acquire user-specific semaphore for fair allocation
                        user_id = request.metadata.get("user_id")
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

        except Exception as exc:
            # Set exception
            if not request.future.done():
                request.future.set_exception(exc)

            self._logger.error(
                "Error executing request %s: %s", request.request_id, exc
            )

        finally:
            self._stats["concurrent_requests"] -= 1

    async def _execute_with_lock(self, request: QueuedRequest) -> Any:
        """Execute request with distributed lock for cache stampede prevention."""
        # Generate lock key based on operation and parameters
        lock_key = f"{request.operation}_{hash(str(request.metadata))}"

        # Try to acquire distributed lock
        lock_acquired = await DistributedLock.acquire(
            lock_key,
            timeout=self.config.lock_timeout,
        )

        try:
            if lock_acquired:
                result = await request.compute_func()
                return result
            else:
                # Could not acquire lock - execute anyway with a warning
                self._logger.warning(
                    "Could not acquire lock for %s, executing anyway", lock_key
                )
                result = await request.compute_func()
                return result

        finally:
            if lock_acquired:
                DistributedLock.release(lock_key)

    def get_stats(self) -> Dict[str, Any]:
        """Get current concurrency statistics."""
        return {
            **self._stats,
            "queue_size": self._request_queue.qsize(),
            "active_requests": len(self._active_requests),
            "max_queue_size": self.config.max_queue_size,
            "global_concurrent_limit": self.config.max_concurrent_requests,
        }

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue-specific statistics.

        Returns a dict with keys: queue_size, active_requests,
        max_queue_size, requests_queued, requests_processed.
        """
        return {
            "queue_size": self._request_queue.qsize(),
            "active_requests": len(self._active_requests),
            "max_queue_size": self.config.max_queue_size,
            "requests_queued": self._stats["requests_queued"],
            "requests_processed": self._stats["requests_processed"],
        }

    async def invalidate_user_cache(self, user_id: str) -> None:
        """Invalidate all cache entries for a specific user."""
        # Remove user from rate limiter cache to reset limits
        if user_id in self._user_rate_limiters:
            del self._user_rate_limiters[user_id]

        if user_id in self._user_semaphores:
            del self._user_semaphores[user_id]

        self._logger.info("Invalidated cache and limits for user: %s", user_id)
