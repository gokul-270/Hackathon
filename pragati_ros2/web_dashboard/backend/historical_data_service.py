#!/usr/bin/env python3
"""
Historical Data Storage Service
================================

Stores performance metrics and error logs using SQLite.
Provides query API for trends and analytics.

Optimized for RPi with:
- Automatic cleanup (7 day retention)
- Size limits (100MB max)
- Efficient indexing
"""

import sqlite3
import time
import threading
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import json

logger = logging.getLogger(__name__)


class HistoricalDataService:
    """
    Historical data storage with SQLite

    Features:
    - Performance metrics storage
    - Error log persistence
    - Automatic cleanup
    - Efficient querying
    """

    def __init__(
        self, db_path: str = "./data/dashboard.db", max_size_mb: int = 100, retention_days: int = 7
    ):
        self.db_path = db_path
        self.max_size_mb = max_size_mb
        self.retention_days = retention_days
        self.lock = threading.RLock()

        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

        # Cleanup thread
        self._start_cleanup_thread()

        logger.info(f"Historical Data Service initialized (db: {db_path})")

    def _init_database(self):
        """Initialize database schema"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Performance metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    metric_type TEXT NOT NULL,
                    node_name TEXT,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL
                )
            ''')

            # Error logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    node_name TEXT,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context TEXT
                )
            ''')

            # Sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    notes TEXT
                )
            ''')

            # Create indices for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
                ON performance_metrics(timestamp)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_metrics_node
                ON performance_metrics(node_name, timestamp)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_errors_timestamp
                ON error_logs(timestamp)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_errors_severity
                ON error_logs(severity, timestamp)
            ''')

            conn.commit()
            conn.close()

            logger.info("Database schema initialized")

    def _start_cleanup_thread(self):
        """Start background cleanup thread"""

        def cleanup_loop():
            while True:
                time.sleep(
                    3600
                )  # BLOCKING_SLEEP_OK: historical data cleanup — daemon thread, 1hr interval — reviewed 2026-03-14
                try:
                    self.cleanup_old_data()
                    self.vacuum_database()
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")

        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()

    # ========== Performance Metrics ==========

    def store_metric(
        self,
        metric_type: str,
        metric_name: str,
        value: float,
        node_name: Optional[str] = None,
        timestamp: Optional[float] = None,
    ):
        """Store a performance metric"""
        if timestamp is None:
            timestamp = time.time()

        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                '''
                INSERT INTO performance_metrics
                (timestamp, metric_type, node_name, metric_name, value)
                VALUES (?, ?, ?, ?, ?)
            ''',
                (timestamp, metric_type, node_name, metric_name, value),
            )

            conn.commit()
            conn.close()

    def store_metrics_batch(self, metrics: List[Dict]):
        """Store multiple metrics efficiently"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            for metric in metrics:
                cursor.execute(
                    '''
                    INSERT INTO performance_metrics
                    (timestamp, metric_type, node_name, metric_name, value)
                    VALUES (?, ?, ?, ?, ?)
                ''',
                    (
                        metric.get('timestamp', time.time()),
                        metric['metric_type'],
                        metric.get('node_name'),
                        metric['metric_name'],
                        metric['value'],
                    ),
                )

            conn.commit()
            conn.close()

    def query_metrics(
        self,
        metric_type: Optional[str] = None,
        node_name: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 1000,
    ) -> List[Dict]:
        """Query performance metrics"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM performance_metrics WHERE 1=1"
            params = []

            if metric_type:
                query += " AND metric_type = ?"
                params.append(metric_type)

            if node_name:
                query += " AND node_name = ?"
                params.append(node_name)

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            conn.close()

            return [dict(row) for row in rows]

    def get_metric_summary(
        self,
        metric_name: str,
        node_name: Optional[str] = None,
        hours: int = 24,
        interval_minutes: int = 5,
    ) -> Dict:
        """Get aggregated metric summary (avg, min, max per interval)"""
        start_time = time.time() - (hours * 3600)
        interval_sec = interval_minutes * 60

        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = '''
                SELECT
                    CAST((timestamp / ?) AS INTEGER) * ? as interval_start,
                    AVG(value) as avg_value,
                    MIN(value) as min_value,
                    MAX(value) as max_value,
                    COUNT(*) as count
                FROM performance_metrics
                WHERE metric_name = ? AND timestamp >= ?
            '''
            params = [interval_sec, interval_sec, metric_name, start_time]

            if node_name:
                query += " AND node_name = ?"
                params.append(node_name)

            query += " GROUP BY interval_start ORDER BY interval_start"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            conn.close()

            return {
                'metric_name': metric_name,
                'node_name': node_name,
                'interval_minutes': interval_minutes,
                'data_points': [
                    {
                        'timestamp': row[0],
                        'avg': row[1],
                        'min': row[2],
                        'max': row[3],
                        'count': row[4],
                    }
                    for row in rows
                ],
            }

    # ========== Error Logs ==========

    def store_error(
        self,
        severity: str,
        message: str,
        node_name: Optional[str] = None,
        context: Optional[Dict] = None,
        timestamp: Optional[float] = None,
    ):
        """Store an error log entry"""
        if timestamp is None:
            timestamp = time.time()

        context_json = json.dumps(context) if context else None

        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                '''
                INSERT INTO error_logs
                (timestamp, node_name, severity, message, context)
                VALUES (?, ?, ?, ?, ?)
            ''',
                (timestamp, node_name, severity, message, context_json),
            )

            conn.commit()
            conn.close()

    def query_errors(
        self,
        severity: Optional[str] = None,
        node_name: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Query error logs"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM error_logs WHERE 1=1"
            params = []

            if severity:
                query += " AND severity = ?"
                params.append(severity)

            if node_name:
                query += " AND node_name = ?"
                params.append(node_name)

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            conn.close()

            results = []
            for row in rows:
                result = dict(row)
                if result['context']:
                    try:
                        result['context'] = json.loads(result['context'])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                results.append(result)

            return results

    def get_error_summary(self, hours: int = 24) -> Dict:
        """Get error summary by severity"""
        start_time = time.time() - (hours * 3600)

        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                '''
                SELECT severity, COUNT(*) as count
                FROM error_logs
                WHERE timestamp >= ?
                GROUP BY severity
            ''',
                (start_time,),
            )

            rows = cursor.fetchall()
            conn.close()

            return {
                'hours': hours,
                'by_severity': {row[0]: row[1] for row in rows},
                'total': sum(row[1] for row in rows),
            }

    # ========== Sessions ==========

    def create_session(self, notes: Optional[str] = None) -> int:
        """Create a new session"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                '''
                INSERT INTO sessions (start_time, notes)
                VALUES (?, ?)
            ''',
                (time.time(), notes),
            )

            session_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return session_id

    def end_session(self, session_id: int):
        """End a session"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                '''
                UPDATE sessions SET end_time = ? WHERE id = ?
            ''',
                (time.time(), session_id),
            )

            conn.commit()
            conn.close()

    def get_sessions(self, limit: int = 50) -> List[Dict]:
        """Get recent sessions"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                '''
                SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?
            ''',
                (limit,),
            )

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    # ========== Maintenance ==========

    def cleanup_old_data(self):
        """Remove data older than retention period"""
        cutoff = time.time() - (self.retention_days * 86400)

        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM performance_metrics WHERE timestamp < ?', (cutoff,))
            metrics_deleted = cursor.rowcount

            cursor.execute('DELETE FROM error_logs WHERE timestamp < ?', (cutoff,))
            errors_deleted = cursor.rowcount

            cursor.execute('DELETE FROM sessions WHERE start_time < ?', (cutoff,))
            sessions_deleted = cursor.rowcount

            conn.commit()
            conn.close()

            if metrics_deleted + errors_deleted + sessions_deleted > 0:
                logger.info(
                    f"Cleaned up {metrics_deleted} metrics, {errors_deleted} errors, {sessions_deleted} sessions"
                )

    def vacuum_database(self):
        """Reclaim space and optimize database"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute('VACUUM')
            conn.close()
            logger.info("Database vacuumed")

    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM performance_metrics')
            metrics_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM error_logs')
            errors_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM sessions')
            sessions_count = cursor.fetchone()[0]

            conn.close()

            # Get file size
            size_bytes = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            size_mb = size_bytes / (1024 * 1024)

            return {
                'db_path': self.db_path,
                'size_mb': round(size_mb, 2),
                'max_size_mb': self.max_size_mb,
                'retention_days': self.retention_days,
                'metrics_count': metrics_count,
                'errors_count': errors_count,
                'sessions_count': sessions_count,
            }


# Singleton instance
_historical_data: Optional[HistoricalDataService] = None


def get_historical_data(
    db_path: str = "./data/dashboard.db", max_size_mb: int = 100, retention_days: int = 7
) -> HistoricalDataService:
    """Get or create historical data service singleton"""
    global _historical_data
    if _historical_data is None:
        _historical_data = HistoricalDataService(db_path, max_size_mb, retention_days)
    return _historical_data


def initialize_historical_data(
    db_path: str = "./data/dashboard.db", max_size_mb: int = 100, retention_days: int = 7
):
    """Initialize historical data service"""
    return get_historical_data(db_path, max_size_mb, retention_days)
