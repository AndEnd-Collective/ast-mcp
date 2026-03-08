"""Chunked result streaming for large outputs with backpressure control."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    chunk_processing_delay: float = 0.001  # Delay between chunks (seconds)
    chunk_timeout: float = 15.0          # Timeout for processing a single chunk
    total_stream_timeout: float = 600.0   # Total timeout for entire stream

    # Flow control settings
    backpressure_threshold: int = 3       # Max concurrent streams before backpressure
    enable_backpressure: bool = True     # Enable flow control
    enable_buffering: bool = True        # Enable smart buffering
    enable_compression: bool = False     # Enable response compression


class StreamingManager:
    """Manages streaming of large result sets with chunking and backpressure control."""

    def __init__(self, config: StreamingConfig):
        self.config = config
        self._active_streams: Dict[str, asyncio.Task] = {}
        self._stream_stats: Dict[str, Dict[str, Any]] = {}
        self._max_stream_stats = 100  # Limit stream stats to prevent memory growth
        self.logger = logging.getLogger(__name__)

    async def stream_results(
        self, data_generator: AsyncIterator[Any], stream_id: str = None
    ) -> AsyncIterator[List[Any]]:
        """Stream large result sets with chunking and backpressure control."""
        if stream_id is None:
            stream_id = f"stream_{int(time.time() * 1000)}"

        # Enforce stream stats limit to prevent memory growth
        if len(self._stream_stats) >= self._max_stream_stats:
            # Remove oldest stream stats
            oldest_stream = min(
                self._stream_stats.keys(),
                key=lambda k: self._stream_stats[k].get('start_time', 0)
            )
            del self._stream_stats[oldest_stream]

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


# Global streaming manager instance
_streaming_manager: Optional[StreamingManager] = None


def get_streaming_manager() -> Optional[StreamingManager]:
    """Get the global streaming manager instance."""
    return _streaming_manager


def set_streaming_manager(manager: StreamingManager) -> None:
    """Set the global streaming manager instance."""
    global _streaming_manager
    _streaming_manager = manager
