#!/usr/bin/env python3
"""
Advanced Log Aggregation System
================================

LazyROS-style log aggregation with /rosout monitoring, history, filtering, and export.
"""

import asyncio
import json
import time
import threading
from collections import deque
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import re
import csv
import io

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from rcl_interfaces.msg import Log

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False

from .capabilities import get_capabilities_manager


class LogLevel(Enum):
    """ROS2 log levels"""

    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    FATAL = 50


@dataclass
class LogEntry:
    """Structured log entry with metadata"""

    timestamp: str
    timestamp_ns: int
    level: str
    level_num: int
    logger_name: str
    node_name: str
    message: str
    file_name: str
    function_name: str
    line: int

    def to_dict(self) -> dict:
        return asdict(self)

    def matches_filter(self, filters: Dict[str, Any]) -> bool:
        """Check if log entry matches filter criteria"""
        # Level filter
        if 'levels' in filters and self.level not in filters['levels']:
            return False

        # Node name filter
        if 'nodes' in filters:
            if not any(pattern in self.node_name for pattern in filters['nodes']):
                return False

        # Message content filter (regex support)
        if 'message_pattern' in filters and filters['message_pattern']:
            try:
                pattern = re.compile(filters['message_pattern'], re.IGNORECASE)
                if not pattern.search(self.message):
                    return False
            except re.error:
                # If regex is invalid, fall back to simple string matching
                if filters['message_pattern'].lower() not in self.message.lower():
                    return False

        # Time range filter
        if 'start_time' in filters:
            if self.timestamp_ns < filters['start_time']:
                return False

        if 'end_time' in filters:
            if self.timestamp_ns > filters['end_time']:
                return False

        # Exclude patterns
        if 'exclude_patterns' in filters:
            for pattern in filters['exclude_patterns']:
                if pattern in self.message or pattern in self.node_name:
                    return False

        return True


class LogAggregator(Node):
    """ROS2 node for aggregating and managing logs"""

    def __init__(self):
        super().__init__('web_dashboard_log_aggregator')
        self.capabilities_manager = get_capabilities_manager()

        # Log storage
        self.max_entries = self.capabilities_manager.get_server_config('max_log_entries', 50000)
        self.log_buffer = deque(maxlen=self.max_entries)
        self._buffer_lock = threading.Lock()

        # Statistics
        self.stats = {
            'total_received': 0,
            'by_level': {level.name: 0 for level in LogLevel},
            'by_node': {},
            'start_time': None,
            'last_message_time': None,
        }

        # Create /rosout subscription
        self.rosout_subscription = self.create_subscription(
            Log,
            '/rosout',
            self.rosout_callback,
            QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
                depth=1000,
            ),
        )

        self.get_logger().info("Log aggregator initialized")

    def rosout_callback(self, msg: Log):
        """Handle incoming /rosout messages"""
        try:
            # Convert ROS log level to string
            level_map = {
                Log.DEBUG: 'DEBUG',
                Log.INFO: 'INFO',
                Log.WARN: 'WARN',
                Log.ERROR: 'ERROR',
                Log.FATAL: 'FATAL',
            }

            level_str = level_map.get(msg.level, 'UNKNOWN')

            # Create log entry
            timestamp = datetime.now()
            log_entry = LogEntry(
                timestamp=timestamp.isoformat(),
                timestamp_ns=int(timestamp.timestamp() * 1e9),
                level=level_str,
                level_num=msg.level,
                logger_name=msg.name,
                node_name=self._extract_node_name(msg.name),
                message=msg.msg,
                file_name=msg.file,
                function_name=msg.function,
                line=msg.line,
            )

            # Add to buffer (thread-safe)
            with self._buffer_lock:
                self.log_buffer.append(log_entry)

            # Update statistics
            self._update_stats(log_entry)

        except Exception as e:
            self.get_logger().error(f"Error processing rosout message: {e}")

    def _extract_node_name(self, logger_name: str) -> str:
        """Extract node name from logger name"""
        # Logger names often follow patterns like:
        # - "node_name"
        # - "node_name.component"
        # - "/node_name"

        # Remove leading slash
        if logger_name.startswith('/'):
            logger_name = logger_name[1:]

        # Take first component before dot
        parts = logger_name.split('.')
        return parts[0] if parts else logger_name

    def _update_stats(self, log_entry: LogEntry):
        """Update aggregation statistics"""
        self.stats['total_received'] += 1

        # Level statistics
        if log_entry.level in self.stats['by_level']:
            self.stats['by_level'][log_entry.level] += 1

        # Node statistics
        if log_entry.node_name not in self.stats['by_node']:
            self.stats['by_node'][log_entry.node_name] = 0
        self.stats['by_node'][log_entry.node_name] += 1

        # Time tracking
        if self.stats['start_time'] is None:
            self.stats['start_time'] = log_entry.timestamp_ns
        self.stats['last_message_time'] = log_entry.timestamp_ns

    def get_logs(
        self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get filtered logs"""
        # Convert buffer to list for manipulation (thread-safe)
        with self._buffer_lock:
            logs = list(self.log_buffer)

        # Apply filters
        if filters:
            logs = [log for log in logs if log.matches_filter(filters)]

        # Sort by timestamp (newest first)
        logs.sort(key=lambda x: x.timestamp_ns, reverse=True)

        # Apply pagination
        if offset > 0:
            logs = logs[offset:]

        if limit and limit > 0:
            logs = logs[:limit]

        return [log.to_dict() for log in logs]

    def get_statistics(self) -> Dict[str, Any]:
        """Get aggregation statistics"""
        # Calculate rates
        stats = self.stats.copy()

        if stats['start_time'] and stats['last_message_time']:
            time_span_sec = (stats['last_message_time'] - stats['start_time']) / 1e9
            if time_span_sec > 0:
                stats['avg_rate_per_sec'] = stats['total_received'] / time_span_sec
            else:
                stats['avg_rate_per_sec'] = 0.0
        else:
            stats['avg_rate_per_sec'] = 0.0

        # Buffer information
        stats['buffer_size'] = len(self.log_buffer)
        stats['buffer_max_size'] = self.max_entries
        stats['buffer_usage_percent'] = (len(self.log_buffer) / self.max_entries) * 100

        # Top nodes by message count
        sorted_nodes = sorted(stats['by_node'].items(), key=lambda x: x[1], reverse=True)
        stats['top_nodes'] = dict(sorted_nodes[:10])  # Top 10 nodes

        return stats

    def export_logs(self, format: str = 'json', filters: Optional[Dict[str, Any]] = None) -> str:
        """Export logs in specified format"""
        logs = self.get_logs(filters)

        if format.lower() == 'json':
            return json.dumps(logs, indent=2, default=str)

        elif format.lower() == 'csv':
            if not logs:
                return ""

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=logs[0].keys())
            writer.writeheader()
            writer.writerows(logs)
            return output.getvalue()

        elif format.lower() == 'txt':
            lines = []
            for log in logs:
                timestamp = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00'))
                formatted_time = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                line = f"[{formatted_time}] [{log['level']}] [{log['node_name']}] {log['message']}"
                lines.append(line)
            return '\n'.join(lines)

        else:
            raise ValueError(f"Unsupported export format: {format}")

    def clear_logs(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Clear logs matching filters, return number cleared"""
        if not filters:
            # Clear all logs
            count = len(self.log_buffer)
            self.log_buffer.clear()

            # Reset statistics
            self.stats = {
                'total_received': 0,
                'by_level': {level.name: 0 for level in LogLevel},
                'by_node': {},
                'start_time': None,
                'last_message_time': None,
            }

            return count
        else:
            # Remove logs matching filters
            original_logs = list(self.log_buffer)
            filtered_logs = [log for log in original_logs if not log.matches_filter(filters)]

            count = len(original_logs) - len(filtered_logs)

            # Replace buffer contents
            self.log_buffer.clear()
            self.log_buffer.extend(filtered_logs)

            return count

    def get_log_levels(self) -> List[str]:
        """Get available log levels"""
        return [level.name for level in LogLevel]

    def get_active_nodes(self) -> List[str]:
        """Get list of nodes that have logged messages"""
        return list(self.stats['by_node'].keys())


class LogAggregationService:
    """Service for managing log aggregation"""

    def __init__(self):
        self.node: Optional[LogAggregator] = None
        self.executor = None
        self.executor_thread = None
        self.running = False

    async def initialize(self):
        """Initialize the log aggregation service"""
        if not ROS2_AVAILABLE:
            raise RuntimeError("ROS2 not available")

        capabilities_manager = get_capabilities_manager()
        if not capabilities_manager.is_enabled('logs_history'):
            raise RuntimeError("Advanced logging not enabled")

        try:

            def log_thread():
                try:
                    try:
                        rclpy.init()
                    except RuntimeError:
                        pass  # Already initialized

                    self.node = LogAggregator()
                    self.executor = rclpy.executors.MultiThreadedExecutor(num_threads=2)
                    self.executor.add_node(self.node)

                    self.running = True
                    self.executor.spin()

                except Exception as e:
                    if self.node:
                        self.node.get_logger().error(f"Log aggregation error: {e}")
                finally:
                    if self.node:
                        self.node.destroy_node()

            self.executor_thread = threading.Thread(target=log_thread, daemon=True)
            self.executor_thread.start()

            # Wait a moment for initialization
            await asyncio.sleep(0.5)

            if self.node:
                self.node.get_logger().info("Log aggregation service initialized")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize log aggregation: {e}")

    async def get_logs(
        self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None, offset: int = 0
    ) -> Dict[str, Any]:
        """Get logs with optional filtering"""
        if not self.node:
            return {"logs": [], "total": 0, "error": "Service not initialized"}

        try:
            logs = self.node.get_logs(filters, limit, offset)
            return {"logs": logs, "total": len(logs), "filters": filters or {}}
        except Exception as e:
            return {"logs": [], "total": 0, "error": str(e)}

    async def get_statistics(self) -> Dict[str, Any]:
        """Get aggregation statistics"""
        if not self.node:
            return {"error": "Service not initialized"}

        try:
            return self.node.get_statistics()
        except Exception as e:
            return {"error": str(e)}

    async def export_logs(
        self, format: str = 'json', filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Export logs in specified format"""
        if not self.node:
            return {"success": False, "error": "Service not initialized"}

        try:
            data = self.node.export_logs(format, filters)
            return {
                "success": True,
                "format": format,
                "data": data,
                "size_bytes": len(data.encode('utf-8')),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def clear_logs(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Clear logs matching filters"""
        if not self.node:
            return {"success": False, "error": "Service not initialized"}

        try:
            count = self.node.clear_logs(filters)
            return {"success": True, "cleared_count": count, "filters": filters or {}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_metadata(self) -> Dict[str, Any]:
        """Get available log levels and nodes"""
        if not self.node:
            return {"levels": [], "nodes": [], "error": "Service not initialized"}

        try:
            return {
                "levels": self.node.get_log_levels(),
                "nodes": self.node.get_active_nodes(),
                "export_formats": ["json", "csv", "txt"],
            }
        except Exception as e:
            return {"levels": [], "nodes": [], "error": str(e)}

    async def shutdown(self):
        """Shutdown the service"""
        try:
            self.running = False

            if self.executor:
                self.executor.shutdown(wait_for=False)

            if self.executor_thread and self.executor_thread.is_alive():
                self.executor_thread.join(timeout=2.0)

            if self.node:
                self.node.destroy_node()
                self.node = None

        except Exception as e:
            print(f"Error during log service shutdown: {e}")


# Global service instance
log_aggregation_service = LogAggregationService()


async def get_log_aggregation_service() -> LogAggregationService:
    """Get the global log aggregation service instance"""
    if not log_aggregation_service.node:
        await log_aggregation_service.initialize()
    return log_aggregation_service
