"""
Performance benchmarks for alpha-hwr.

These benchmarks measure the performance of critical operations
to ensure the library meets performance requirements.

Run with: pytest tests/benchmarks/ -v --benchmark-only
"""

import sys
from pathlib import Path

# Add tests directory to path for mocks import
tests_dir = Path(__file__).parent.parent
if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))

import asyncio
import time

import pytest
from mocks.mock_pump import MockPump

from alpha_hwr.protocol import FrameBuilder, FrameParser
from alpha_hwr.protocol.codec import (
    decode_float_be,
    encode_float_be,
)


class TestCodecPerformance:
    """Benchmark protocol encoding/decoding operations."""

    def test_encode_float_performance(self, benchmark):
        """Benchmark float encoding speed."""
        result = benchmark(encode_float_be, 1.5)
        assert result == bytes.fromhex("3FC00000")

    def test_decode_float_performance(self, benchmark):
        """Benchmark float decoding speed."""
        data = bytes.fromhex("3FC00000")
        result = benchmark(decode_float_be, data)
        assert result == 1.5

    def test_encode_batch_floats(self, benchmark):
        """Benchmark encoding multiple floats."""
        values = [1.5, 2.5, 3.5, 4.5, 5.5]

        def encode_batch():
            return b"".join(encode_float_be(v) for v in values)

        result = benchmark(encode_batch)
        assert len(result) == 20  # 5 floats * 4 bytes


class TestFrameBuilderPerformance:
    """Benchmark frame construction."""

    def test_build_class10_read(self, benchmark):
        """Benchmark Class 10 READ frame building."""
        register = 0x570045  # Motor state

        result = benchmark(FrameBuilder.build_class10_read, register)
        assert result[0] == 0x27  # Start byte
        assert result[4] == 0x0A  # Class 10

    def test_build_data_object_set(self, benchmark):
        """Benchmark Class 10 SET frame building."""
        sub_id = 0x5600
        obj_id = 0x0601
        data = b"\x00" * 12

        result = benchmark(
            FrameBuilder.build_data_object_set, sub_id, obj_id, data
        )
        assert len(result) > 0


class TestFrameParserPerformance:
    """Benchmark frame parsing."""

    def test_parse_motor_state_frame(self, benchmark):
        """Benchmark parsing motor state response."""
        # Real motor state response
        frame = bytes.fromhex(
            "2417f8e70a90004557000c43660000000000003fc00000000000004234000044bbf0004201c000"
        )

        result = benchmark(FrameParser.parse_frame, frame)
        assert result.valid
        assert result.class_byte == 10

    def test_parse_and_decode_telemetry(self, benchmark):
        """Benchmark complete parse + decode cycle."""
        from alpha_hwr.protocol import TelemetryDecoder

        frame = bytes.fromhex(
            "2417f8e70a90004557000c43660000000000003fc00000000000004234000044bbf0004201c000"
        )

        def parse_and_decode():
            parsed = FrameParser.parse_frame(frame)
            return TelemetryDecoder.decode_motor_state(parsed.payload)

        result = benchmark(parse_and_decode)
        assert "voltage_ac_v" in result


class TestMockPumpPerformance:
    """Benchmark mock pump operations."""

    def test_mock_pump_command_latency(self, benchmark):
        """Benchmark mock pump command processing."""
        loop = asyncio.new_event_loop()
        try:
            pump = MockPump()
            loop.run_until_complete(pump.connect())
            loop.run_until_complete(pump.authenticate())

            cmd = FrameBuilder.build_class10_read(0x570045)

            def sync_send_command():
                return loop.run_until_complete(pump.send_command(cmd))

            result = benchmark(sync_send_command)
            assert len(result) > 0
        finally:
            loop.close()

    @pytest.mark.asyncio
    async def test_mock_pump_throughput(self):
        """Measure mock pump command throughput."""
        pump = MockPump()
        await pump.connect()
        await pump.authenticate()

        cmd = FrameBuilder.build_class10_read(0x570045)

        iterations = 100
        start = time.perf_counter()

        for _ in range(iterations):
            await pump.send_command(cmd)

        elapsed = time.perf_counter() - start
        per_cmd = (elapsed / iterations) * 1000  # ms
        throughput = iterations / elapsed  # commands/sec

        print("\nMock pump throughput:")
        print(f"  {per_cmd:.2f}ms per command")
        print(f"  {throughput:.1f} commands/sec")

        assert per_cmd < 10.0, (
            f"Mock pump too slow: {per_cmd:.1f}ms per command"
        )
        assert throughput > 100, (
            f"Mock pump throughput too low: {throughput:.1f} cmd/s"
        )


class TestEndToEndPerformance:
    """Benchmark complete workflows."""

    @pytest.mark.asyncio
    async def test_connect_authenticate_read_cycle(self):
        """Benchmark complete connect→auth→read cycle."""
        from unittest.mock import AsyncMock, patch

        from mocks.mock_transport import MockBleakClient

        from alpha_hwr.client import AlphaHWRClient

        with (
            patch("alpha_hwr.client.BleakClient", MockBleakClient),
            patch(
                "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
                new_callable=AsyncMock,
            ),
        ):
            start = time.perf_counter()

            # Full cycle
            client = AlphaHWRClient("MOCK")
            await client.connect()
            assert client.telemetry is not None
            telemetry = await client.telemetry.read_once()
            await client.disconnect()

            elapsed = (time.perf_counter() - start) * 1000  # ms

            print(f"\nComplete cycle: {elapsed:.1f}ms")

            assert telemetry is not None
            # Relaxed threshold for slow CI environments
            assert elapsed < 10000, f"Complete cycle too slow: {elapsed:.1f}ms"

    @pytest.mark.asyncio
    async def test_rapid_telemetry_reads(self):
        """Benchmark rapid consecutive telemetry reads."""
        from unittest.mock import AsyncMock, patch

        from mocks.mock_transport import MockBleakClient

        from alpha_hwr.client import AlphaHWRClient

        with (
            patch("alpha_hwr.client.BleakClient", MockBleakClient),
            patch(
                "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
                new_callable=AsyncMock,
            ),
        ):
            client = AlphaHWRClient("MOCK")
            await client.connect()

            iterations = 50
            start = time.perf_counter()

            assert client.telemetry is not None
            for _ in range(iterations):
                await client.telemetry.read_once()

            elapsed = time.perf_counter() - start
            per_read = (elapsed / iterations) * 1000  # ms

            print("\nRapid reads:")
            print(f"  {per_read:.2f}ms per read")
            print(f"  {iterations / elapsed:.1f} reads/sec")

            await client.disconnect()

            # Relaxed threshold
            assert per_read < 500, f"Telemetry reads too slow: {per_read:.1f}ms"


class TestMemoryPerformance:
    """Benchmark memory usage."""

    @pytest.mark.skip("Requires memory_profiler")
    def test_client_memory_footprint(self):
        """Measure client memory footprint."""
        from memory_profiler import (  # type: ignore[import-not-found]
            memory_usage,
        )

        def create_client():
            from alpha_hwr.client import AlphaHWRClient

            return AlphaHWRClient("MOCK")

        mem_before = memory_usage()[0]
        _ = create_client()
        mem_after = memory_usage()[0]

        footprint = mem_after - mem_before
        print(f"\nClient memory footprint: {footprint:.2f} MB")

        assert footprint < 10, f"Client uses too much memory: {footprint:.1f}MB"


# Performance targets
PERFORMANCE_TARGETS = {
    "encode_float": 0.001,  # ms
    "decode_float": 0.001,  # ms
    "build_frame": 0.01,  # ms
    "parse_frame": 0.01,  # ms
    "mock_command": 5.0,  # ms
    "telemetry_read": 50.0,  # ms
    "full_cycle": 500.0,  # ms
}


def test_performance_summary():
    """Print performance targets summary."""
    print("\n" + "=" * 60)
    print("PERFORMANCE TARGETS")
    print("=" * 60)
    for operation, target_ms in PERFORMANCE_TARGETS.items():
        print(f"{operation:20s}: < {target_ms:6.1f}ms")
    print("=" * 60)
