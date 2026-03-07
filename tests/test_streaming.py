"""Tests for the streaming module - chunked result streaming with backpressure control."""

import asyncio
import time

import pytest

from ast_grep_mcp.streaming import (
    StreamingConfig,
    StreamingManager,
    get_streaming_manager,
    set_streaming_manager,
)


# ---------------------------------------------------------------------------
# Helper: async generator that yields individual items
# ---------------------------------------------------------------------------

async def async_range(n: int):
    """Simple async generator yielding integers 0..n-1."""
    for i in range(n):
        yield i


async def collect_chunks(stream_manager: StreamingManager, generator, stream_id=None):
    """Collect all chunks from stream_results into a list of lists."""
    chunks = []
    async for chunk in stream_manager.stream_results(generator, stream_id=stream_id):
        chunks.append(chunk)
    return chunks


# ===========================================================================
# StreamingConfig tests
# ===========================================================================

class TestStreamingConfig:
    """Tests for StreamingConfig dataclass."""

    def test_defaults(self):
        config = StreamingConfig()
        assert config.default_chunk_size == 1000
        assert config.max_chunk_size == 5000
        assert config.min_chunk_size == 100
        assert config.max_buffer_size_mb == 100
        assert config.memory_check_interval == 50
        assert config.chunk_processing_delay == 0.001
        assert config.chunk_timeout == 15.0
        assert config.total_stream_timeout == 600.0
        assert config.backpressure_threshold == 3
        assert config.enable_backpressure is True
        assert config.enable_buffering is True
        assert config.enable_compression is False

    def test_custom_values(self):
        config = StreamingConfig(
            default_chunk_size=500,
            max_chunk_size=2000,
            min_chunk_size=50,
            max_buffer_size_mb=256,
            memory_check_interval=10,
            chunk_processing_delay=0.05,
            chunk_timeout=30.0,
            total_stream_timeout=120.0,
            backpressure_threshold=5,
            enable_backpressure=False,
            enable_buffering=False,
            enable_compression=True,
        )
        assert config.default_chunk_size == 500
        assert config.max_chunk_size == 2000
        assert config.min_chunk_size == 50
        assert config.max_buffer_size_mb == 256
        assert config.memory_check_interval == 10
        assert config.chunk_processing_delay == 0.05
        assert config.chunk_timeout == 30.0
        assert config.total_stream_timeout == 120.0
        assert config.backpressure_threshold == 5
        assert config.enable_backpressure is False
        assert config.enable_buffering is False
        assert config.enable_compression is True

    def test_partial_override(self):
        config = StreamingConfig(default_chunk_size=42, enable_compression=True)
        assert config.default_chunk_size == 42
        assert config.enable_compression is True
        # Other fields should retain defaults
        assert config.max_chunk_size == 5000
        assert config.enable_backpressure is True


# ===========================================================================
# StreamingManager tests
# ===========================================================================

class TestStreamingManager:
    """Tests for StreamingManager."""

    @pytest.mark.asyncio
    async def test_stream_results_chunks_data_correctly(self):
        """Items should be yielded in chunks of default_chunk_size."""
        config = StreamingConfig(default_chunk_size=3, chunk_processing_delay=0)
        manager = StreamingManager(config)

        # 9 items -> 3 full chunks of size 3
        chunks = await collect_chunks(manager, async_range(9), stream_id="test_exact")
        assert len(chunks) == 3
        for chunk in chunks:
            assert len(chunk) == 3
        # Verify all items present
        all_items = [item for chunk in chunks for item in chunk]
        assert all_items == list(range(9))

    @pytest.mark.asyncio
    async def test_stream_results_yields_remaining_items(self):
        """A final partial chunk should be yielded for leftover items."""
        config = StreamingConfig(default_chunk_size=4, chunk_processing_delay=0)
        manager = StreamingManager(config)

        # 10 items -> 2 full chunks of 4, then 1 partial chunk of 2
        chunks = await collect_chunks(manager, async_range(10), stream_id="test_remainder")
        assert len(chunks) == 3
        assert len(chunks[0]) == 4
        assert len(chunks[1]) == 4
        assert len(chunks[2]) == 2
        all_items = [item for chunk in chunks for item in chunk]
        assert all_items == list(range(10))

    @pytest.mark.asyncio
    async def test_stream_results_single_chunk(self):
        """Fewer items than chunk_size should result in a single chunk."""
        config = StreamingConfig(default_chunk_size=100, chunk_processing_delay=0)
        manager = StreamingManager(config)

        chunks = await collect_chunks(manager, async_range(5), stream_id="test_single")
        assert len(chunks) == 1
        assert chunks[0] == list(range(5))

    @pytest.mark.asyncio
    async def test_stream_results_empty_generator(self):
        """An empty generator should produce no chunks."""
        config = StreamingConfig(default_chunk_size=10, chunk_processing_delay=0)
        manager = StreamingManager(config)

        chunks = await collect_chunks(manager, async_range(0), stream_id="test_empty")
        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Stream stats should track chunks_processed and items_processed."""
        config = StreamingConfig(default_chunk_size=5, chunk_processing_delay=0)
        manager = StreamingManager(config)

        # 13 items -> 2 full chunks of 5, 1 partial of 3 = 3 chunks, 13 items
        await collect_chunks(manager, async_range(13), stream_id="stats_test")

        stats = manager._stream_stats["stats_test"]
        assert stats["chunks_processed"] == 3
        assert stats["items_processed"] == 13
        assert "start_time" in stats
        assert "end_time" in stats
        assert stats["end_time"] >= stats["start_time"]

    @pytest.mark.asyncio
    async def test_stats_tracking_empty_stream(self):
        """An empty stream should still record start/end time and zero counts."""
        config = StreamingConfig(default_chunk_size=10, chunk_processing_delay=0)
        manager = StreamingManager(config)

        await collect_chunks(manager, async_range(0), stream_id="empty_stats")

        stats = manager._stream_stats["empty_stats"]
        assert stats["chunks_processed"] == 0
        assert stats["items_processed"] == 0
        assert "end_time" in stats

    @pytest.mark.asyncio
    async def test_stream_stats_limit_enforcement(self):
        """When stats exceed _max_stream_stats, the oldest entry should be evicted."""
        config = StreamingConfig(default_chunk_size=10, chunk_processing_delay=0)
        manager = StreamingManager(config)
        manager._max_stream_stats = 5  # Lower the limit for testing

        # Create 5 streams to fill the stats
        for i in range(5):
            await collect_chunks(manager, async_range(1), stream_id=f"s_{i}")

        assert len(manager._stream_stats) == 5
        assert "s_0" in manager._stream_stats

        # Creating a 6th stream should evict the oldest (s_0)
        await collect_chunks(manager, async_range(1), stream_id="s_5")

        assert len(manager._stream_stats) == 5
        assert "s_0" not in manager._stream_stats
        assert "s_5" in manager._stream_stats

    @pytest.mark.asyncio
    async def test_processing_delay_applied(self):
        """When chunk_processing_delay > 0, there should be a measurable delay."""
        delay = 0.05
        config = StreamingConfig(default_chunk_size=2, chunk_processing_delay=delay)
        manager = StreamingManager(config)

        # 6 items -> 3 chunks, 2 delays between chunks (delay after chunk 1 and chunk 2)
        start = time.monotonic()
        await collect_chunks(manager, async_range(6), stream_id="delay_test")
        elapsed = time.monotonic() - start

        # Should have at least 2 delays (after the first two full chunks)
        assert elapsed >= delay * 2 * 0.8  # Allow 20% tolerance

    @pytest.mark.asyncio
    async def test_no_processing_delay_when_zero(self):
        """When chunk_processing_delay is 0, streaming should be fast."""
        config = StreamingConfig(default_chunk_size=2, chunk_processing_delay=0)
        manager = StreamingManager(config)

        start = time.monotonic()
        await collect_chunks(manager, async_range(100), stream_id="nodelay_test")
        elapsed = time.monotonic() - start

        # Should complete very quickly with no artificial delay
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_auto_generated_stream_id(self):
        """When no stream_id is provided, one should be auto-generated."""
        config = StreamingConfig(default_chunk_size=10, chunk_processing_delay=0)
        manager = StreamingManager(config)

        await collect_chunks(manager, async_range(5))

        # Should have exactly one stats entry with auto-generated key
        assert len(manager._stream_stats) == 1
        auto_id = list(manager._stream_stats.keys())[0]
        assert auto_id.startswith("stream_")

    @pytest.mark.asyncio
    async def test_multiple_streams_tracked_independently(self):
        """Multiple streams should each have their own stats."""
        config = StreamingConfig(default_chunk_size=5, chunk_processing_delay=0)
        manager = StreamingManager(config)

        await collect_chunks(manager, async_range(10), stream_id="alpha")
        await collect_chunks(manager, async_range(3), stream_id="beta")

        assert manager._stream_stats["alpha"]["items_processed"] == 10
        assert manager._stream_stats["alpha"]["chunks_processed"] == 2

        assert manager._stream_stats["beta"]["items_processed"] == 3
        assert manager._stream_stats["beta"]["chunks_processed"] == 1

    @pytest.mark.asyncio
    async def test_error_in_generator_propagates(self):
        """If the async generator raises, the error should propagate."""
        async def failing_generator():
            yield 1
            yield 2
            raise ValueError("generator failure")

        config = StreamingConfig(default_chunk_size=10, chunk_processing_delay=0)
        manager = StreamingManager(config)

        with pytest.raises(ValueError, match="generator failure"):
            await collect_chunks(manager, failing_generator(), stream_id="error_test")

        # End time should still be recorded in the finally block
        assert "end_time" in manager._stream_stats["error_test"]

    @pytest.mark.asyncio
    async def test_bytes_processed_initialized_to_zero(self):
        """bytes_processed should be initialized to zero in stats."""
        config = StreamingConfig(default_chunk_size=10, chunk_processing_delay=0)
        manager = StreamingManager(config)

        await collect_chunks(manager, async_range(1), stream_id="bytes_check")

        assert manager._stream_stats["bytes_check"]["bytes_processed"] == 0


# ===========================================================================
# Global accessor tests
# ===========================================================================

class TestGlobalAccessors:
    """Tests for get_streaming_manager / set_streaming_manager."""

    def setup_method(self):
        """Reset global state before each test."""
        import ast_grep_mcp.streaming as mod
        mod._streaming_manager = None

    def teardown_method(self):
        """Clean up global state after each test."""
        import ast_grep_mcp.streaming as mod
        mod._streaming_manager = None

    def test_initial_value_is_none(self):
        assert get_streaming_manager() is None

    def test_set_and_get_round_trip(self):
        config = StreamingConfig()
        manager = StreamingManager(config)
        set_streaming_manager(manager)
        assert get_streaming_manager() is manager

    def test_set_replaces_previous(self):
        config = StreamingConfig()
        manager1 = StreamingManager(config)
        manager2 = StreamingManager(config)

        set_streaming_manager(manager1)
        assert get_streaming_manager() is manager1

        set_streaming_manager(manager2)
        assert get_streaming_manager() is manager2

    def test_set_to_none_explicitly(self):
        config = StreamingConfig()
        manager = StreamingManager(config)
        set_streaming_manager(manager)
        assert get_streaming_manager() is not None

        set_streaming_manager(None)
        assert get_streaming_manager() is None
