#!/usr/bin/env python3
"""
Topic Echo Service for Pragati ROS2 Dashboard
Provides real-time topic message monitoring with statistics tracking.

Includes both the service class and FastAPI router with REST/WebSocket
endpoints for topic echo functionality.
"""

import asyncio
import json
import time
import threading
import uuid
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any, Deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import traceback

from fastapi import APIRouter, HTTPException, WebSocket

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict


@dataclass
class TopicMessage:
    """Represents a single topic message with metadata"""

    timestamp: str
    timestamp_ns: int
    data: dict
    size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TopicStats:
    """Statistics for a topic subscription"""

    rate_hz: float = 0.0
    jitter_ms: float = 0.0
    avg_size_bytes: int = 0
    total_messages: int = 0
    bandwidth_bps: float = 0.0
    last_update: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class TopicSubscription:
    """Manages subscription to a single topic with statistics"""

    def __init__(
        self,
        topic_name: str,
        topic_type: str,
        node: Node,
        max_hz: float = 10.0,
        qos_profile: QoSProfile = None,
    ):
        self.topic_name = topic_name
        self.topic_type = topic_type
        self.node = node
        self.max_hz = max_hz
        self.qos_profile = qos_profile or QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=10,
        )

        # Message storage and statistics
        self.messages: Deque[TopicMessage] = deque(maxlen=1000)  # Keep last 1000 messages
        self.stats = TopicStats()

        # Rate limiting
        self.last_callback_time = 0.0
        self.min_interval = 1.0 / max_hz if max_hz > 0 else 0.0

        # Statistics tracking
        self.message_times: Deque[float] = deque(maxlen=100)  # For rate calculation
        self.message_sizes: List[int] = []

        # ROS2 subscription
        self.subscription = None
        self.message_class = None
        self._setup_subscription()

    def _setup_subscription(self):
        """Initialize the ROS2 subscription"""
        try:
            # Get message class from type string
            self.message_class = get_message(self.topic_type)

            # Create subscription
            self.subscription = self.node.create_subscription(
                self.message_class, self.topic_name, self._message_callback, self.qos_profile
            )

            self.node.get_logger().info(
                f"Created subscription for {self.topic_name} ({self.topic_type})"
            )

        except Exception as e:
            self.node.get_logger().error(
                f"Failed to create subscription for {self.topic_name}: {e}"
            )
            raise

    def _message_callback(self, msg):
        """Handle incoming messages with rate limiting"""
        current_time = time.time()

        # Rate limiting
        if current_time - self.last_callback_time < self.min_interval:
            return

        self.last_callback_time = current_time

        try:
            # Convert message to dictionary
            msg_dict = message_to_ordereddict(msg)

            # Calculate message size (approximate)
            msg_json = json.dumps(msg_dict, default=str)
            size_bytes = len(msg_json.encode('utf-8'))

            # Create topic message
            timestamp = datetime.now(timezone.utc)
            topic_message = TopicMessage(
                timestamp=timestamp.isoformat(),
                timestamp_ns=int(timestamp.timestamp() * 1e9),
                data=msg_dict,
                size_bytes=size_bytes,
            )

            # Store message
            self.messages.append(topic_message)

            # Update statistics
            self._update_statistics(current_time, size_bytes)

        except Exception as e:
            self.node.get_logger().error(f"Error processing message for {self.topic_name}: {e}")

    def _update_statistics(self, current_time: float, size_bytes: int):
        """Update topic statistics"""
        self.message_times.append(current_time)
        self.message_sizes.append(size_bytes)
        self.stats.total_messages += 1

        # Calculate rate (messages per second)
        if len(self.message_times) >= 2:
            time_window = self.message_times[-1] - self.message_times[0]
            if time_window > 0:
                self.stats.rate_hz = (len(self.message_times) - 1) / time_window

        # Calculate jitter (standard deviation of intervals)
        if len(self.message_times) >= 3:
            intervals = [
                self.message_times[i] - self.message_times[i - 1]
                for i in range(1, len(self.message_times))
            ]
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
                self.stats.jitter_ms = (variance**0.5) * 1000  # Convert to milliseconds

        # Calculate average message size and bandwidth
        if self.message_sizes:
            self.stats.avg_size_bytes = sum(self.message_sizes) / len(self.message_sizes)
            self.stats.bandwidth_bps = self.stats.rate_hz * self.stats.avg_size_bytes

        self.stats.last_update = current_time

        # Cleanup old size data
        if len(self.message_sizes) > 1000:
            self.message_sizes = self.message_sizes[-100:]

    def get_recent_messages(self, limit: int = 50) -> List[dict]:
        """Get recent messages"""
        messages = list(self.messages)[-limit:]
        return [msg.to_dict() for msg in messages]

    def get_statistics(self) -> dict:
        """Get current statistics"""
        return self.stats.to_dict()

    def destroy(self):
        """Clean up subscription"""
        if self.subscription:
            self.node.destroy_subscription(self.subscription)
            self.subscription = None


class TopicEchoService:
    """Service for managing multiple topic subscriptions"""

    def __init__(self):
        self.node: Optional[Node] = None
        self.subscriptions: Dict[str, TopicSubscription] = {}
        self.client_topics: Dict[str, set] = defaultdict(set)  # client_id -> topic_names
        self.executor = None
        self.executor_thread = None
        self.running = False

    async def initialize(self):
        """Initialize the ROS2 node and executor"""
        try:
            if not rclpy.ok():
                rclpy.init()

            self.node = Node('web_dashboard_topic_echo')
            self.executor = rclpy.executors.MultiThreadedExecutor(num_threads=2)
            self.executor.add_node(self.node)

            # Start executor in separate thread
            self.executor_thread = threading.Thread(target=self._run_executor, daemon=True)
            self.running = True
            self.executor_thread.start()

            self.node.get_logger().info("Topic Echo Service initialized")

        except Exception as e:
            self.node.get_logger().error(f"Failed to initialize Topic Echo Service: {e}")
            raise

    def _run_executor(self):
        """Run ROS2 executor in separate thread"""
        try:
            while self.running and rclpy.ok():
                self.executor.spin_once(timeout_sec=1.0)
        except Exception as e:
            if self.node:
                self.node.get_logger().error(f"Executor error: {e}")

    async def start_echo(
        self, topic_name: str, client_id: str, max_hz: float = 10.0, qos: dict = None
    ) -> dict:
        """Start echoing a topic for a client"""
        try:
            if not self.node:
                return {"success": False, "error": "Service not initialized"}

            # Get topic type
            topic_info = await self._get_topic_info(topic_name)
            if not topic_info:
                return {"success": False, "error": f"Topic {topic_name} not found"}

            topic_type = topic_info['type']
            subscription_key = f"{topic_name}_{client_id}"

            # Check if already subscribed
            if subscription_key in self.subscriptions:
                return {
                    "success": False,
                    "error": f"Already echoing {topic_name} for client {client_id}",
                }

            # Create QoS profile
            qos_profile = QoSProfile(
                reliability=(
                    ReliabilityPolicy.BEST_EFFORT
                    if qos and qos.get('reliability') == 'best_effort'
                    else ReliabilityPolicy.RELIABLE
                ),
                durability=DurabilityPolicy.VOLATILE,
                depth=10,
            )

            # Create subscription
            subscription = TopicSubscription(
                topic_name=topic_name,
                topic_type=topic_type,
                node=self.node,
                max_hz=max_hz,
                qos_profile=qos_profile,
            )

            self.subscriptions[subscription_key] = subscription
            self.client_topics[client_id].add(topic_name)

            self.node.get_logger().info(
                f"Started echoing {topic_name} for client {client_id} at {max_hz} Hz"
            )

            return {
                "success": True,
                "topic": topic_name,
                "type": topic_type,
                "max_hz": max_hz,
                "client_id": client_id,
            }

        except Exception as e:
            error_msg = f"Failed to start echo for {topic_name}: {e}"
            if self.node:
                self.node.get_logger().error(error_msg)
            return {"success": False, "error": error_msg}

    async def stop_echo(self, topic_name: str, client_id: str) -> dict:
        """Stop echoing a topic for a client"""
        try:
            subscription_key = f"{topic_name}_{client_id}"

            if subscription_key not in self.subscriptions:
                return {
                    "success": False,
                    "error": f"Not echoing {topic_name} for client {client_id}",
                }

            # Destroy subscription
            subscription = self.subscriptions[subscription_key]
            subscription.destroy()

            # Remove from tracking
            del self.subscriptions[subscription_key]
            self.client_topics[client_id].discard(topic_name)

            if self.node:
                self.node.get_logger().info(f"Stopped echoing {topic_name} for client {client_id}")

            return {"success": True, "topic": topic_name, "client_id": client_id}

        except Exception as e:
            error_msg = f"Failed to stop echo for {topic_name}: {e}"
            if self.node:
                self.node.get_logger().error(error_msg)
            return {"success": False, "error": error_msg}

    async def get_topic_messages(self, topic_name: str, limit: int = 50) -> dict:
        """Get recent messages for a topic"""
        try:
            # Find subscription for this topic (from any client)
            subscription = None
            for key, sub in self.subscriptions.items():
                if sub.topic_name == topic_name:
                    subscription = sub
                    break

            if not subscription:
                return {"messages": [], "topic": topic_name}

            messages = subscription.get_recent_messages(limit)

            return {"messages": messages, "topic": topic_name, "count": len(messages)}

        except Exception as e:
            error_msg = f"Failed to get messages for {topic_name}: {e}"
            if self.node:
                self.node.get_logger().error(error_msg)
            return {"messages": [], "topic": topic_name, "error": error_msg}

    async def get_topic_stats(self, topic_name: str) -> dict:
        """Get statistics for a topic"""
        try:
            # Find subscription for this topic (from any client)
            subscription = None
            for key, sub in self.subscriptions.items():
                if sub.topic_name == topic_name:
                    subscription = sub
                    break

            if not subscription:
                return {"stats": TopicStats().to_dict(), "topic": topic_name}

            stats = subscription.get_statistics()

            return {"stats": stats, "topic": topic_name}

        except Exception as e:
            error_msg = f"Failed to get stats for {topic_name}: {e}"
            if self.node:
                self.node.get_logger().error(error_msg)
            return {"stats": TopicStats().to_dict(), "topic": topic_name, "error": error_msg}

    async def _get_topic_info(self, topic_name: str) -> Optional[dict]:
        """Get topic information including type"""
        try:
            if not self.node:
                return None

            # Get topic types and names
            topic_names_and_types = self.node.get_topic_names_and_types()

            for name, types in topic_names_and_types:
                if name == topic_name and types:
                    return {"name": name, "type": types[0]}

            return None

        except Exception as e:
            if self.node:
                self.node.get_logger().error(f"Failed to get topic info for {topic_name}: {e}")
            return None

    async def cleanup_client(self, client_id: str):
        """Clean up all subscriptions for a client"""
        try:
            if client_id not in self.client_topics:
                return

            topics_to_cleanup = list(self.client_topics[client_id])

            for topic_name in topics_to_cleanup:
                await self.stop_echo(topic_name, client_id)

            # Remove client tracking
            if client_id in self.client_topics:
                del self.client_topics[client_id]

            if self.node:
                self.node.get_logger().info(f"Cleaned up all subscriptions for client {client_id}")

        except Exception as e:
            if self.node:
                self.node.get_logger().error(f"Error cleaning up client {client_id}: {e}")

    async def shutdown(self):
        """Shutdown the service"""
        try:
            self.running = False

            # Stop all subscriptions
            for subscription in list(self.subscriptions.values()):
                subscription.destroy()

            self.subscriptions.clear()
            self.client_topics.clear()

            # Shutdown executor
            if self.executor:
                self.executor.shutdown(wait_for=False)

            if self.executor_thread and self.executor_thread.is_alive():
                self.executor_thread.join(timeout=2.0)

            # Destroy node
            if self.node:
                self.node.destroy_node()
                self.node = None

            # Shutdown rclpy if we initialized it
            if rclpy.ok():
                rclpy.shutdown()

        except Exception as e:
            print(f"Error during shutdown: {e}")


# Global service instance
topic_echo_service = TopicEchoService()


async def get_topic_echo_service() -> TopicEchoService:
    """Get the global topic echo service instance"""
    if not topic_echo_service.node:
        await topic_echo_service.initialize()
    return topic_echo_service


# ===================================================================
# FastAPI Router — REST and WebSocket endpoints for topic echo
# ===================================================================

topic_echo_router = APIRouter()

# WebSocket connection tracking: client_ip -> set of connection_ids
_topic_echo_connections: Dict[str, set] = {}
_TOPIC_ECHO_MAX_CONNECTIONS_PER_IP = 3
_TOPIC_ECHO_MAX_RATE_HZ = 10.0
_TOPIC_ECHO_MAX_MESSAGE_BYTES = 10 * 1024


@topic_echo_router.post("/api/topics/echo/start")
async def start_topic_echo(request: dict):
    """Start echoing a topic."""
    try:
        svc = await get_topic_echo_service()
        topic_name = request.get("topic")
        client_id = request.get("client_id", str(uuid.uuid4()))
        qos_options = request.get("qos", {})
        max_hz = request.get("max_hz", 10.0)
        if not topic_name:
            raise HTTPException(
                status_code=400,
                detail="Topic name required",
            )
        result = await svc.start_echo(topic_name, client_id, max_hz, qos_options)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(f"Error starting topic echo: {str(e)}"),
        )


@topic_echo_router.post("/api/topics/echo/stop")
async def stop_topic_echo(request: dict):
    """Stop echoing a topic."""
    try:
        svc = await get_topic_echo_service()
        topic_name = request.get("topic")
        client_id = request.get("client_id")
        if not topic_name or not client_id:
            raise HTTPException(
                status_code=400,
                detail=("Topic name and client_id required"),
            )
        result = await svc.stop_echo(topic_name, client_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(f"Error stopping topic echo: {str(e)}"),
        )


@topic_echo_router.get("/api/topics/{topic_name}/messages")
async def get_topic_messages_endpoint(topic_name: str, limit: int = 50):
    """Get recent messages for a topic."""
    try:
        svc = await get_topic_echo_service()
        result = await svc.get_topic_messages(topic_name, limit)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=("Error getting topic messages: " f"{str(e)}"),
        )


@topic_echo_router.get("/api/topics/{topic_name}/stats")
async def get_topic_stats_endpoint(topic_name: str):
    """Get statistics for a topic."""
    try:
        svc = await get_topic_echo_service()
        result = await svc.get_topic_stats(topic_name)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(f"Error getting topic stats: {str(e)}"),
        )


@topic_echo_router.get("/api/topics/stats/all")
async def get_all_topic_stats():
    """Get statistics for all active echo topics."""
    try:
        svc = await get_topic_echo_service()
        all_stats = {}
        for key, sub in svc.subscriptions.items():
            topic_name = sub.topic_name
            if topic_name not in all_stats:
                all_stats[topic_name] = sub.get_statistics()
        return {"stats": all_stats}
    except Exception as e:
        return {"stats": {}, "error": str(e)}


@topic_echo_router.websocket("/ws/topic_echo/{topic_name}")
async def topic_echo_websocket(websocket: WebSocket, topic_name: str):
    """Stream topic messages over WebSocket."""
    client_ip = "testclient"
    if websocket.client:
        client_ip = websocket.client.host or "unknown"

    connection_id = str(uuid.uuid4())
    ip_conns = _topic_echo_connections.get(client_ip, set())
    if len(ip_conns) >= _TOPIC_ECHO_MAX_CONNECTIONS_PER_IP:
        await websocket.accept()
        await websocket.close(
            code=4001,
            reason="Max echo connections exceeded",
        )
        return

    await websocket.accept()
    if client_ip not in _topic_echo_connections:
        _topic_echo_connections[client_ip] = set()
    _topic_echo_connections[client_ip].add(connection_id)

    client_id = f"ws_echo_{connection_id}"
    min_interval = 1.0 / _TOPIC_ECHO_MAX_RATE_HZ

    try:
        svc = await get_topic_echo_service()
        await svc.start_echo(topic_name, client_id)

        while True:
            send_start = time.time()
            payload: Dict[str, Any] = await svc.get_topic_messages(topic_name)

            raw = json.dumps(payload, default=str)
            if len(raw.encode("utf-8")) > _TOPIC_ECHO_MAX_MESSAGE_BYTES:
                payload = {
                    "topic": topic_name,
                    "messages": [],
                    "_truncated": True,
                    "error": ("Message exceeds " f"{_TOPIC_ECHO_MAX_MESSAGE_BYTES}" " byte limit"),
                }

            await websocket.send_json(payload)
            elapsed = time.time() - send_start
            sleep_time = max(0.0, min_interval - elapsed)
            await asyncio.sleep(sleep_time)
    except Exception:
        pass
    finally:
        if client_ip in _topic_echo_connections:
            _topic_echo_connections[client_ip].discard(connection_id)
            if not _topic_echo_connections[client_ip]:
                del _topic_echo_connections[client_ip]
        try:
            svc = await get_topic_echo_service()
            await svc.stop_echo(topic_name, client_id)
            await svc.cleanup_client(client_id)
        except Exception:
            pass
