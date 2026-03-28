"""Unit tests for ping-based network health monitoring."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from backend.entity_model import Entity


class _FakePingProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.fixture
def remote_entity() -> Entity:
    return Entity(
        id="arm1",
        name="Arm 1",
        entity_type="arm",
        source="remote",
        ip="10.42.0.20",
    )


@pytest.fixture
def local_entity() -> Entity:
    return Entity(
        id="local",
        name="Local Machine",
        entity_type="dev",
        source="local",
        ip="127.0.0.1",
    )


class TestPingMonitorChecks:
    @pytest.mark.asyncio
    async def test_ping_success_sets_network_reachable_and_latency(self, remote_entity):
        from backend.ping_monitor import PingMonitor

        monitor = PingMonitor()
        process = _FakePingProcess(
            returncode=0,
            stdout=b"64 bytes from 10.42.0.20: icmp_seq=1 ttl=64 time=2.34 ms\n",
        )

        with patch(
            "backend.ping_monitor.asyncio.create_subprocess_exec",
            return_value=process,
        ) as mock_exec:
            await monitor.check_entity(remote_entity)

        assert remote_entity.health["network"] == "reachable"
        assert remote_entity.health["network_latency_ms"] == pytest.approx(2.34)
        assert monitor._failure_counts[remote_entity.id] == 0
        assert mock_exec.call_args.args[-1] == "10.42.0.20"

    @pytest.mark.asyncio
    async def test_single_ping_failure_sets_network_degraded(self, remote_entity):
        from backend.ping_monitor import PingMonitor

        monitor = PingMonitor(failure_threshold=2)
        process = _FakePingProcess(returncode=1, stdout=b"", stderr=b"")

        with patch(
            "backend.ping_monitor.asyncio.create_subprocess_exec",
            return_value=process,
        ):
            await monitor.check_entity(remote_entity)

        assert remote_entity.health["network"] == "degraded"
        assert remote_entity.health["network_latency_ms"] is None
        assert monitor._failure_counts[remote_entity.id] == 1

    @pytest.mark.asyncio
    async def test_two_consecutive_failures_set_network_unreachable(self, remote_entity):
        from backend.ping_monitor import PingMonitor

        monitor = PingMonitor(failure_threshold=2)
        process = _FakePingProcess(returncode=1, stdout=b"", stderr=b"")

        with patch(
            "backend.ping_monitor.asyncio.create_subprocess_exec",
            return_value=process,
        ):
            await monitor.check_entity(remote_entity)
            await monitor.check_entity(remote_entity)

        assert remote_entity.health["network"] == "unreachable"
        assert remote_entity.health["network_latency_ms"] is None
        assert monitor._failure_counts[remote_entity.id] == 2

    @pytest.mark.asyncio
    async def test_local_entity_is_skipped_and_marked_local(self, local_entity):
        from backend.ping_monitor import PingMonitor

        monitor = PingMonitor()

        with patch("backend.ping_monitor.asyncio.create_subprocess_exec") as mock_exec:
            await monitor.check_entity(local_entity)

        assert local_entity.health["network"] == "local"
        assert local_entity.health["network_latency_ms"] is None
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_ping_subprocess_failure_sets_unknown_and_logs_once(self, remote_entity):
        from backend.ping_monitor import PingMonitor

        monitor = PingMonitor()

        with patch(
            "backend.ping_monitor.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("ping not found"),
        ), patch("backend.ping_monitor.logger.warning") as mock_warning:
            await monitor.check_entity(remote_entity)
            await monitor.check_entity(remote_entity)

        assert remote_entity.health["network"] == "unknown"
        assert mock_warning.call_count == 1

    @pytest.mark.asyncio
    async def test_entity_ip_change_uses_new_ip_and_resets_failure_counter(self, remote_entity):
        from backend.ping_monitor import PingMonitor

        monitor = PingMonitor(failure_threshold=2)
        fail_process = _FakePingProcess(returncode=1, stdout=b"", stderr=b"")
        ok_process = _FakePingProcess(
            returncode=0,
            stdout=b"64 bytes from 10.42.0.25: icmp_seq=1 ttl=64 time=1.25 ms\n",
        )

        with patch(
            "backend.ping_monitor.asyncio.create_subprocess_exec",
            return_value=fail_process,
        ):
            await monitor.check_entity(remote_entity)

        assert monitor._failure_counts[remote_entity.id] == 1

        remote_entity.ip = "10.42.0.25"
        monitor.update_entity(remote_entity)

        with patch(
            "backend.ping_monitor.asyncio.create_subprocess_exec",
            return_value=ok_process,
        ) as mock_exec:
            await monitor.check_entity(remote_entity)

        assert monitor._failure_counts[remote_entity.id] == 0
        assert remote_entity.health["network"] == "reachable"
        assert mock_exec.call_args.args[-1] == "10.42.0.25"


class TestPingMonitorLifecycle:
    @pytest.mark.asyncio
    async def test_add_and_remove_entity_start_and_stop_tasks_dynamically(self, remote_entity):
        from backend.ping_monitor import PingMonitor

        second = Entity(
            id="arm2",
            name="Arm 2",
            entity_type="arm",
            source="remote",
            ip="10.42.0.21",
        )
        monitor = PingMonitor(interval_s=30.0)

        run_event = asyncio.Event()

        async def fake_loop(entity_id: str):
            run_event.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise

        with patch.object(monitor, "_monitor_entity_loop", side_effect=fake_loop):
            monitor.start([remote_entity])
            await asyncio.wait_for(run_event.wait(), timeout=1.0)
            assert remote_entity.id in monitor._tasks

            monitor.add_entity(second)
            await asyncio.sleep(0)
            assert second.id in monitor._tasks

            await monitor.remove_entity(remote_entity.id)
            assert remote_entity.id not in monitor._tasks

            await monitor.stop()
            assert not monitor._tasks
