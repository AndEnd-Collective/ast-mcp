"""Memory monitoring, leak detection, and GC optimization."""

import asyncio
import gc
import logging
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger(__name__)


@dataclass
class MemoryConfig:
    """Configuration for memory monitoring and optimization."""

    # Memory monitoring settings
    enable_detailed_monitoring: bool = True
    enable_leak_detection: bool = True
    enable_tracemalloc: bool = False  # Disabled by default due to overhead
    tracemalloc_limit: int = 10  # Reduced from 25 to save memory

    # Memory thresholds (in MB)
    warning_threshold_mb: int = 512     # Warn when memory usage exceeds this
    critical_threshold_mb: int = 1024   # Critical memory usage threshold
    max_memory_mb: int = 2048           # Maximum allowed memory usage

    # Monitoring intervals (in seconds) - reduced frequency to save resources
    monitoring_interval: int = 60       # Increased from 30 to 60 seconds
    leak_check_interval: int = 600      # Increased from 300 to 600 seconds (10 min)
    gc_optimization_interval: int = 120 # Increased from 60 to 120 seconds

    # Memory optimization settings
    enable_aggressive_gc: bool = False   # Enable aggressive garbage collection
    gc_threshold_adjustment: bool = True # Adjust GC thresholds dynamically

    # Alert settings
    enable_memory_alerts: bool = True    # Enable memory usage alerts
    alert_cooldown: int = 300           # Cooldown between alerts (seconds)


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

        # Memory tracking state (reduced overhead)
        self._baseline_memory: Optional[float] = None
        self._peak_memory: float = 0.0
        self._leak_candidates: Dict[str, Dict[str, Any]] = {}
        self._max_leak_candidates: int = 20  # Reduced from 50 to save memory
        self._max_snapshots: int = 20  # Reduced from 50 to save memory
        self._max_alerts: int = 10  # Reduced from 25 to save memory

        # Initialize tracemalloc only if enabled and not already running
        if self.config.enable_tracemalloc and not tracemalloc.is_tracing():
            tracemalloc.start(self.config.tracemalloc_limit)
            logger.info(f"Memory tracing started with tracemalloc (limit: {self.config.tracemalloc_limit})")
        elif self.config.enable_tracemalloc:
            logger.info("Tracemalloc already running, skipping initialization")
        else:
            logger.info("Tracemalloc disabled to reduce memory overhead")

        logger.info("MemoryMonitor initialized with reduced overhead config")

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

            # Get system memory info (only available memory to reduce overhead)
            system_memory = psutil.virtual_memory()

            # Get process info (reduced data collection)
            num_threads = self._process.num_threads()
            try:
                num_fds = self._process.num_fds()
            except (psutil.AccessDenied, AttributeError):
                num_fds = 0  # Not available on all platforms

            # Get Python-specific info (only if detailed monitoring enabled)
            if self.config.enable_detailed_monitoring:
                python_objects = len(gc.get_objects())
                gc_counts = gc.get_count()
            else:
                python_objects = 0
                gc_counts = (0, 0, 0)

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

            # Add to snapshots with enforced limit
            self._snapshots.append(snapshot)
            if len(self._snapshots) > self._max_snapshots:
                # Remove oldest snapshots
                excess = len(self._snapshots) - self._max_snapshots
                self._snapshots = self._snapshots[excess:]

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
            current_time = time.time()

            # Clean up old leak candidates first
            self._cleanup_leak_candidates(current_time)

            # Check for lines with significantly increased memory usage
            for stat in top_stats[:10]:  # Check top 10 memory allocations
                size_mb = stat.size / 1024 / 1024
                if size_mb > 10:  # Alert if any single allocation is >10MB
                    # Use shorter key instead of full stack trace to save memory
                    key = self._generate_compact_key(stat)

                    # Track this potential leak candidate with metadata
                    if key in self._leak_candidates:
                        self._leak_candidates[key]['count'] += 1
                        self._leak_candidates[key]['last_seen'] = current_time
                        self._leak_candidates[key]['size_mb'] = size_mb
                    else:
                        # Enforce size limit
                        if len(self._leak_candidates) >= self._max_leak_candidates:
                            self._evict_oldest_leak_candidate()

                        self._leak_candidates[key] = {
                            'count': 1,
                            'last_seen': current_time,
                            'size_mb': size_mb,
                            'traceback': stat.traceback.format()[-1]  # Only keep last line
                        }

                    # Alert if we've seen this allocation pattern multiple times
                    if self._leak_candidates[key]['count'] >= 3:
                        if self._should_send_alert('leak_detected', current_time):
                            alert = MemoryAlert(
                                alert_type='leak_detected',
                                timestamp=current_time,
                                current_usage_mb=size_mb,
                                threshold_mb=10,
                                message=f"Potential memory leak detected: {size_mb:.1f}MB allocation",
                                suggested_actions=[
                                    "Review code at: " + self._leak_candidates[key]['traceback'],
                                    "Check for circular references",
                                    "Consider weak references",
                                    "Review object lifecycle management"
                                ]
                            )
                            await self._send_alert(alert)

                            # Reset counter to avoid spam
                            self._leak_candidates[key]['count'] = 0

        except Exception as e:
            logger.error(f"Error checking for memory leaks: {e}")

    def _generate_compact_key(self, stat) -> str:
        """Generate a compact key for leak detection instead of full stack trace."""
        try:
            # Use file:line instead of full traceback to save memory
            frame = stat.traceback._frames[0]  # Get top frame
            return f"{frame.filename}:{frame.lineno}"
        except (IndexError, AttributeError):
            # Fallback to hash of traceback
            return str(hash(str(stat.traceback)))

    def _cleanup_leak_candidates(self, current_time: float) -> None:
        """Remove leak candidates older than 1 hour."""
        cutoff_time = current_time - 3600  # 1 hour
        keys_to_remove = [
            key for key, data in self._leak_candidates.items()
            if data['last_seen'] < cutoff_time
        ]
        for key in keys_to_remove:
            del self._leak_candidates[key]

    def _evict_oldest_leak_candidate(self) -> None:
        """Remove the oldest leak candidate when max size is reached."""
        if not self._leak_candidates:
            return

        # Find the oldest entry
        oldest_key = min(
            self._leak_candidates.keys(),
            key=lambda k: self._leak_candidates[k]['last_seen']
        )
        del self._leak_candidates[oldest_key]

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

        # Keep only last 25 alerts (reduced from 50 to save memory)
        if len(self._alerts) > 25:
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

    def _check_memory_alerts(self, snapshot: MemorySnapshot) -> None:
        """Check for memory alerts and manage alert storage."""
        current_time = time.time()

        alerts_to_add = []

        # Check memory usage thresholds
        if snapshot.rss_mb > self.config.critical_threshold_mb:
            alert_type = 'critical_memory'
            if self._should_send_alert(alert_type, current_time):
                alerts_to_add.append(MemoryAlert(
                    alert_type=alert_type,
                    timestamp=current_time,
                    current_usage_mb=snapshot.rss_mb,
                    threshold_mb=self.config.critical_threshold_mb,
                    message=f"Critical memory usage: {snapshot.rss_mb:.1f}MB (threshold: {self.config.critical_threshold_mb}MB)",
                    suggested_actions=[
                        "Force garbage collection",
                        "Clear caches",
                        "Reduce concurrent operations",
                        "Consider restarting the application"
                    ]
                ))

        elif snapshot.rss_mb > self.config.warning_threshold_mb:
            alert_type = 'high_memory'
            if self._should_send_alert(alert_type, current_time):
                alerts_to_add.append(MemoryAlert(
                    alert_type=alert_type,
                    timestamp=current_time,
                    current_usage_mb=snapshot.rss_mb,
                    threshold_mb=self.config.warning_threshold_mb,
                    message=f"High memory usage: {snapshot.rss_mb:.1f}MB (threshold: {self.config.warning_threshold_mb}MB)",
                    suggested_actions=[
                        "Monitor memory trends",
                        "Consider cache cleanup",
                        "Review recent operations"
                    ]
                ))

        # Check for rapid memory growth (but with higher threshold to reduce false positives)
        if (hasattr(snapshot, 'growth_rate_mb_per_min') and
            snapshot.growth_rate_mb_per_min and
            snapshot.growth_rate_mb_per_min > 100):  # Increased from 50 to 100 MB/min
            alert_type = 'rapid_growth'
            if self._should_send_alert(alert_type, current_time):
                alerts_to_add.append(MemoryAlert(
                    alert_type=alert_type,
                    timestamp=current_time,
                    current_usage_mb=snapshot.rss_mb,
                    threshold_mb=100,
                    message=f"Rapid memory growth: {snapshot.growth_rate_mb_per_min:.1f}MB/min",
                    suggested_actions=[
                        "Check for memory leaks",
                        "Review recent operations",
                        "Consider forcing garbage collection"
                    ]
                ))

        # Add new alerts and enforce limit
        for alert in alerts_to_add:
            self._alerts.append(alert)
            logger.warning(f"Memory Alert: {alert.message}")

        # Enforce alert limit - keep only the most recent alerts
        if len(self._alerts) > self._max_alerts:
            excess = len(self._alerts) - self._max_alerts
            self._alerts = self._alerts[excess:]


# Global memory monitor instance
_memory_monitor: Optional[MemoryMonitor] = None


def get_memory_monitor() -> Optional[MemoryMonitor]:
    """Get the global memory monitor instance."""
    return _memory_monitor


def set_memory_monitor(monitor: MemoryMonitor) -> None:
    """Set the global memory monitor instance."""
    global _memory_monitor
    _memory_monitor = monitor
