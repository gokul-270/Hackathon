"""ICMP ping monitor for per-entity network health."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from typing import Awaitable, Callable, Iterable

from .entity_model import Entity

logger = logging.getLogger(__name__)

_LATENCY_PATTERN = re.compile(rb"time=([0-9.]+)\s*ms")


class PingMonitor:
    """Track per-entity network reachability with async ping checks."""

    def __init__(
        self,
        interval_s: float = 3.0,
        timeout_s: float = 2.0,
        failure_threshold: int = 2,
        on_state_change: Callable[[Entity, str, str], Awaitable[None] | None] | None = None,
    ) -> None:
        self._interval_s = interval_s
        self._timeout_s = timeout_s
        self._failure_threshold = failure_threshold
        self._on_state_change = on_state_change
        self._tasks: dict[str, asyncio.Task] = {}
        self._entities: dict[str, Entity] = {}
        self._failure_counts: dict[str, int] = {}
        self._entity_hosts: dict[str, str | None] = {}
        self._warned_ping_unavailable = False
        self._running = False

    def start(self, entities: Iterable[Entity]) -> None:
        """Start background monitoring for the supplied entities."""
        self._running = True
        for entity in entities:
            self.add_entity(entity)

    async def stop(self) -> None:
        """Stop all monitoring tasks."""
        self._running = False
        task_ids = list(self._tasks.keys())
        for entity_id in task_ids:
            await self.remove_entity(entity_id)

    def add_entity(self, entity: Entity) -> None:
        """Start monitoring one entity if it is not already tracked."""
        self._entities[entity.id] = entity
        self._entity_hosts[entity.id] = self._target_host(entity)
        self._failure_counts.setdefault(entity.id, 0)
        if entity.id in self._tasks or not self._running:
            return
        self._tasks[entity.id] = asyncio.create_task(self._monitor_entity_loop(entity.id))

    async def remove_entity(self, entity_id: str) -> None:
        """Stop monitoring one entity and clean up state."""
        task = self._tasks.pop(entity_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._entities.pop(entity_id, None)
        self._failure_counts.pop(entity_id, None)
        self._entity_hosts.pop(entity_id, None)

    def update_entity(self, entity: Entity) -> None:
        """Refresh tracked metadata after an entity update."""
        previous_host = self._entity_hosts.get(entity.id)
        current_host = self._target_host(entity)
        self._entities[entity.id] = entity
        self._entity_hosts[entity.id] = current_host
        if previous_host != current_host:
            self._failure_counts[entity.id] = 0

    async def check_entity(self, entity: Entity) -> None:
        """Run one ping check and update entity network health."""
        previous_state = entity.health.get("network", "unknown")

        if entity.source == "local":
            entity.update_health(network="local", network_latency_ms=None)
            await self._notify_if_changed(entity, previous_state)
            return

        host = self._target_host(entity)
        if not host:
            entity.update_health(network="unknown", network_latency_ms=None)
            await self._notify_if_changed(entity, previous_state)
            return

        try:
            process = await asyncio.create_subprocess_exec(
                "ping",
                "-c",
                "1",
                "-W",
                str(int(self._timeout_s)),
                host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            entity.update_health(network="unknown", network_latency_ms=None)
            if not self._warned_ping_unavailable:
                self._warned_ping_unavailable = True
                logger.warning("Ping command unavailable; network health set to unknown")
            await self._notify_if_changed(entity, previous_state)
            return

        stdout, _stderr = await process.communicate()
        if process.returncode == 0:
            self._failure_counts[entity.id] = 0
            entity.update_health(
                network="reachable",
                network_latency_ms=self._parse_latency_ms(stdout),
            )
        else:
            failures = self._failure_counts.get(entity.id, 0) + 1
            self._failure_counts[entity.id] = failures
            entity.update_health(
                network=("unreachable" if failures >= self._failure_threshold else "degraded"),
                network_latency_ms=None,
            )

        self._entity_hosts[entity.id] = host
        await self._notify_if_changed(entity, previous_state)

    async def _monitor_entity_loop(self, entity_id: str) -> None:
        while self._running and entity_id in self._entities:
            await self.check_entity(self._entities[entity_id])
            await asyncio.sleep(self._interval_s)

    async def _notify_if_changed(self, entity: Entity, previous_state: str) -> None:
        current_state = entity.health.get("network", "unknown")
        if current_state == previous_state or self._on_state_change is None:
            return
        result = self._on_state_change(entity, previous_state, current_state)
        if asyncio.iscoroutine(result):
            await result

    @staticmethod
    def _target_host(entity: Entity) -> str | None:
        return entity.poll_host or entity.ip

    @staticmethod
    def _parse_latency_ms(stdout: bytes) -> float | None:
        match = _LATENCY_PATTERN.search(stdout)
        if match is None:
            return None
        return float(match.group(1))
