#!/usr/bin/env python3
"""
Alert Engine
============

Threshold-based monitoring and notification system.

Features:
- Configurable alert rules from YAML
- Threshold monitoring with duration requirements
- Multiple notification channels (WebSocket, webhook, log)
- Alert grouping to prevent spam
- Event-driven architecture for efficiency
"""

import time
import threading
import yaml
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging
import requests

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    """Alert rule definition"""
    name: str
    metric: str
    threshold: float
    comparison: str = "greater_than"  # greater_than, less_than, equal_to, rate_drop
    duration_sec: float = 0
    severity: str = "warning"
    actions: List[str] = field(default_factory=list)
    message: str = ""
    
    # State
    triggered_since: Optional[float] = None
    last_alert_time: float = 0
    alert_count: int = 0


@dataclass
class Alert:
    """Active alert instance"""
    alert_id: str
    rule_name: str
    severity: str
    message: str
    timestamp: float
    metric_value: Any
    context: Dict = field(default_factory=dict)
    acknowledged: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'alert_id': self.alert_id,
            'rule_name': self.rule_name,
            'severity': self.severity,
            'message': self.message,
            'timestamp': self.timestamp,
            'metric_value': self.metric_value,
            'context': self.context,
            'acknowledged': self.acknowledged
        }


class AlertEngine:
    """
    Alert monitoring engine
    
    Features:
    - Load rules from YAML configuration
    - Monitor metrics against thresholds
    - Execute actions (log, notify, webhook)
    - Alert grouping and cooldown
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.lock = threading.RLock()
        
        # Alert rules and state
        self.rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        
        # Alert grouping
        self.alert_counts = defaultdict(int)
        self.last_alert_time = defaultdict(float)
        
        # Configuration
        self.enabled = True
        self.webhook_url: Optional[str] = None
        self.cooldown_sec = 60  # Min time between repeat alerts
        self.group_window_sec = 60  # Window for alert grouping
        self.max_alerts_per_group = 5
        
        # Notification callbacks
        self.notification_callbacks: List[Callable] = []
        
        # Load configuration if provided
        if config_path:
            self.load_config(config_path)
        
        logger.info("Alert Engine initialized")
    
    def load_config(self, config_path: str):
        """Load alert configuration from YAML"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Load alert rules
            if 'alerts' in config:
                for rule_def in config['alerts']:
                    rule = AlertRule(
                        name=rule_def['name'],
                        metric=rule_def['metric'],
                        threshold=rule_def['threshold'],
                        comparison=rule_def.get('comparison', 'greater_than'),
                        duration_sec=rule_def.get('duration_sec', 0),
                        severity=rule_def.get('severity', 'warning'),
                        actions=rule_def.get('actions', []),
                        message=rule_def.get('message', '')
                    )
                    self.rules[rule.name] = rule
                
                logger.info(f"Loaded {len(self.rules)} alert rules")
            
            # Load action configuration
            if 'actions' in config:
                actions_config = config['actions']
                if 'webhook' in actions_config and actions_config['webhook'].get('enabled'):
                    self.webhook_url = actions_config['webhook'].get('url')
            
            # Load grouping configuration
            if 'grouping' in config:
                grouping_config = config['grouping']
                if grouping_config.get('enabled'):
                    self.group_window_sec = grouping_config.get('group_window_sec', 60)
                    self.max_alerts_per_group = grouping_config.get('max_alerts_per_group', 5)
            
        except Exception as e:
            logger.error(f"Error loading alert config: {e}", exc_info=True)
    
    def add_rule(self, rule: AlertRule):
        """Add or update an alert rule"""
        with self.lock:
            self.rules[rule.name] = rule
            logger.info(f"Added alert rule: {rule.name}")
    
    def remove_rule(self, rule_name: str):
        """Remove an alert rule"""
        with self.lock:
            if rule_name in self.rules:
                del self.rules[rule_name]
                logger.info(f"Removed alert rule: {rule_name}")
    
    def register_notification_callback(self, callback: Callable):
        """Register a callback for alert notifications"""
        self.notification_callbacks.append(callback)
    
    def check_metric(self, metric_name: str, value: Any, context: Optional[Dict] = None):
        """Check a metric value against all applicable rules"""
        if not self.enabled:
            return
        
        with self.lock:
            for rule in self.rules.values():
                if rule.metric == metric_name:
                    self._evaluate_rule(rule, value, context or {})
    
    def _evaluate_rule(self, rule: AlertRule, value: Any, context: Dict):
        """Evaluate a single rule against a metric value"""
        # Check if value meets threshold
        triggered = False
        
        if rule.comparison == "greater_than":
            triggered = value > rule.threshold
        elif rule.comparison == "less_than":
            triggered = value < rule.threshold
        elif rule.comparison == "equal_to":
            triggered = value == rule.threshold
        elif rule.comparison == "rate_drop":
            # Rate drop requires previous value in context
            if 'previous_value' in context:
                drop_ratio = (context['previous_value'] - value) / context['previous_value']
                triggered = drop_ratio > rule.threshold
        
        now = time.time()
        
        if triggered:
            # Check if we need to wait for duration
            if rule.duration_sec > 0:
                if rule.triggered_since is None:
                    rule.triggered_since = now
                elif (now - rule.triggered_since) >= rule.duration_sec:
                    # Duration requirement met, fire alert
                    self._fire_alert(rule, value, context)
            else:
                # No duration requirement, fire immediately
                self._fire_alert(rule, value, context)
        else:
            # Condition not met, reset trigger time
            rule.triggered_since = None
    
    def _fire_alert(self, rule: AlertRule, value: Any, context: Dict):
        """Fire an alert"""
        now = time.time()
        
        # Check cooldown
        if (now - rule.last_alert_time) < self.cooldown_sec:
            return
        
        # Check alert grouping
        group_key = f"{rule.name}_{rule.metric}"
        if (now - self.last_alert_time[group_key]) < self.group_window_sec:
            if self.alert_counts[group_key] >= self.max_alerts_per_group:
                logger.warning(f"Alert group limit reached for {rule.name}")
                return
            self.alert_counts[group_key] += 1
        else:
            # New group window
            self.alert_counts[group_key] = 1
            self.last_alert_time[group_key] = now
        
        # Create alert
        alert_id = f"{rule.name}_{int(now * 1000)}"
        
        # Format message
        message = rule.message
        if not message:
            message = f"{rule.name}: {rule.metric} = {value} (threshold: {rule.threshold})"
        
        # Replace template variables
        message = message.replace('{{value}}', str(value))
        message = message.replace('{{threshold}}', str(rule.threshold))
        message = message.replace('{{duration_sec}}', str(rule.duration_sec))
        for key, val in context.items():
            message = message.replace(f'{{{{{key}}}}}', str(val))
        
        alert = Alert(
            alert_id=alert_id,
            rule_name=rule.name,
            severity=rule.severity,
            message=message,
            timestamp=now,
            metric_value=value,
            context=context
        )
        
        # Store alert
        with self.lock:
            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert)
        
        # Update rule state
        rule.last_alert_time = now
        rule.alert_count += 1
        
        # Execute actions
        self._execute_actions(rule, alert)
        
        logger.warning(f"ALERT: {alert.message}")
    
    def _execute_actions(self, rule: AlertRule, alert: Alert):
        """Execute alert actions"""
        for action in rule.actions:
            try:
                if action == "log":
                    self._action_log(alert)
                elif action == "notify":
                    self._action_notify(alert)
                elif action == "webhook":
                    self._action_webhook(alert)
                elif action == "trigger_safety_stop":
                    self._action_safety_stop(alert)
            except Exception as e:
                logger.error(f"Error executing action {action}: {e}")
    
    def _action_log(self, alert: Alert):
        """Log action"""
        log_level = {
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }.get(alert.severity, logging.WARNING)
        
        logger.log(log_level, f"ALERT [{alert.severity.upper()}]: {alert.message}")
    
    def _action_notify(self, alert: Alert):
        """Notify action (via callbacks)"""
        for callback in self.notification_callbacks:
            try:
                callback(alert.to_dict())
            except Exception as e:
                logger.error(f"Error in notification callback: {e}")
    
    def _action_webhook(self, alert: Alert):
        """Webhook action"""
        if not self.webhook_url:
            logger.warning("Webhook URL not configured")
            return
        
        try:
            response = requests.post(
                self.webhook_url,
                json=alert.to_dict(),
                timeout=5
            )
            response.raise_for_status()
            logger.info(f"Webhook notification sent for {alert.alert_id}")
        except Exception as e:
            logger.error(f"Webhook error: {e}")
    
    def _action_safety_stop(self, alert: Alert):
        """Safety stop action (would call ROS2 service)"""
        logger.critical(f"SAFETY STOP TRIGGERED: {alert.message}")
        # In production, this would call the emergency stop service
        # For now, just log
    
    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert"""
        with self.lock:
            if alert_id in self.active_alerts:
                self.active_alerts[alert_id].acknowledged = True
                logger.info(f"Alert acknowledged: {alert_id}")
    
    def clear_alert(self, alert_id: str):
        """Clear an alert"""
        with self.lock:
            if alert_id in self.active_alerts:
                del self.active_alerts[alert_id]
                logger.info(f"Alert cleared: {alert_id}")
    
    def get_active_alerts(self) -> List[Dict]:
        """Get all active alerts"""
        with self.lock:
            return [a.to_dict() for a in self.active_alerts.values()]
    
    def get_alert_history(self, limit: int = 100) -> List[Dict]:
        """Get alert history"""
        with self.lock:
            history = list(self.alert_history)
            return [a.to_dict() for a in history[-limit:]]
    
    def get_alert_stats(self) -> Dict:
        """Get alert statistics"""
        with self.lock:
            total_rules = len(self.rules)
            active_count = len(self.active_alerts)
            
            by_severity = defaultdict(int)
            for alert in self.active_alerts.values():
                by_severity[alert.severity] += 1
            
            total_fired = sum(rule.alert_count for rule in self.rules.values())
            
            return {
                'total_rules': total_rules,
                'active_alerts': active_count,
                'by_severity': dict(by_severity),
                'total_fired': total_fired,
                'enabled': self.enabled
            }
    
    def enable(self):
        """Enable alert engine"""
        self.enabled = True
        logger.info("Alert engine enabled")
    
    def disable(self):
        """Disable alert engine"""
        self.enabled = False
        logger.info("Alert engine disabled")


# Singleton instance
_alert_engine: Optional[AlertEngine] = None


def get_alert_engine(config_path: Optional[str] = None) -> AlertEngine:
    """Get or create alert engine singleton"""
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine(config_path)
    return _alert_engine


def initialize_alert_engine(config_path: Optional[str] = None):
    """Initialize alert engine"""
    return get_alert_engine(config_path)
