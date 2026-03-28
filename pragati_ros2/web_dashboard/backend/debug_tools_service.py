#!/usr/bin/env python3
"""
Debug Tools Service
===================

Provides interactive debugging capabilities for ROS2 system:
- Live topic echo with message inspection
- Service testing and call history
- Parameter management (get/set/monitor)

Optimized for RPi with lazy subscriptions and limited concurrency.
"""

import time
import json
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
import logging

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
    from rclpy.parameter import Parameter
    import rosidl_runtime_py
    from rosidl_runtime_py import message_to_ordereddict
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    Node = object

logger = logging.getLogger(__name__)


@dataclass
class TopicEchoSession:
    """Active topic echo session"""
    session_id: str
    topic_name: str
    message_type: str
    start_time: float
    message_buffer: deque = field(default_factory=lambda: deque(maxlen=100))
    subscription: Any = None
    message_count: int = 0
    active: bool = True
    
    def add_message(self, msg: Any):
        """Add message to buffer"""
        try:
            # Convert ROS message to dictionary
            msg_dict = message_to_ordereddict(msg) if ROS2_AVAILABLE else str(msg)
            self.message_buffer.append({
                'timestamp': time.time(),
                'data': msg_dict,
                'sequence': self.message_count
            })
            self.message_count += 1
        except Exception as e:
            logger.error(f"Error converting message: {e}")
    
    def get_messages(self, limit: Optional[int] = None) -> List[Dict]:
        """Get messages from buffer"""
        messages = list(self.message_buffer)
        if limit:
            messages = messages[-limit:]
        return messages
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'session_id': self.session_id,
            'topic_name': self.topic_name,
            'message_type': self.message_type,
            'start_time': self.start_time,
            'message_count': self.message_count,
            'active': self.active,
            'duration': time.time() - self.start_time
        }


@dataclass
class ServiceCallRecord:
    """Record of a service call"""
    call_id: str
    service_name: str
    service_type: str
    request: Dict
    response: Optional[Dict] = None
    success: bool = False
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class DebugToolsService:
    """
    Debug tools service for ROS2 system
    
    Features:
    - Topic echo with lazy subscription
    - Service call testing with history
    - Parameter management
    - Limited concurrency for RPi
    """
    
    def __init__(self, node: Optional[Node] = None, max_echo_sessions: int = 3):
        self.node = node
        self.max_echo_sessions = max_echo_sessions
        
        # Topic echo sessions
        self.echo_sessions: Dict[str, TopicEchoSession] = {}
        self.lock = threading.RLock()
        
        # Service call history
        self.service_history: deque = deque(maxlen=100)
        
        # Parameter cache
        self.parameter_cache: Dict[str, Dict] = {}
        self.parameter_cache_time: Dict[str, float] = {}
        self.cache_ttl = 5.0  # seconds
        
        logger.info(f"Debug Tools Service initialized (max echo sessions: {max_echo_sessions})")
    
    # ========== Topic Echo ==========
    
    def start_topic_echo(self, topic_name: str, duration: Optional[float] = None) -> Dict:
        """
        Start echoing a topic
        
        Args:
            topic_name: Topic to echo
            duration: Auto-stop after duration (seconds), None = infinite
        
        Returns:
            Session info dict or error
        """
        if not ROS2_AVAILABLE or not self.node:
            return {'error': 'ROS2 not available'}
        
        with self.lock:
            # Check session limit
            active_sessions = sum(1 for s in self.echo_sessions.values() if s.active)
            if active_sessions >= self.max_echo_sessions:
                return {
                    'error': f'Maximum echo sessions ({self.max_echo_sessions}) reached',
                    'active_sessions': active_sessions
                }
            
            # Check if already echoing this topic
            for session in self.echo_sessions.values():
                if session.topic_name == topic_name and session.active:
                    return {
                        'error': 'Topic already being echoed',
                        'session_id': session.session_id
                    }
            
            try:
                # Get topic type
                topic_type = self._get_topic_type(topic_name)
                if not topic_type:
                    return {'error': f'Topic {topic_name} not found or type unavailable'}
                
                # Create session
                session_id = f"echo_{int(time.time() * 1000)}"
                session = TopicEchoSession(
                    session_id=session_id,
                    topic_name=topic_name,
                    message_type=topic_type,
                    start_time=time.time()
                )
                
                # Create subscription
                msg_class = self._get_message_class(topic_type)
                if not msg_class:
                    return {'error': f'Could not load message type: {topic_type}'}
                
                subscription = self.node.create_subscription(
                    msg_class,
                    topic_name,
                    lambda msg: session.add_message(msg),
                    10
                )
                
                session.subscription = subscription
                self.echo_sessions[session_id] = session
                
                # Auto-stop timer
                if duration:
                    threading.Timer(duration, lambda: self.stop_topic_echo(session_id)).start()
                
                logger.info(f"Started echo session {session_id} for {topic_name}")
                return {
                    'success': True,
                    'session': session.to_dict()
                }
            
            except Exception as e:
                logger.error(f"Error starting topic echo: {e}", exc_info=True)
                return {'error': str(e)}
    
    def stop_topic_echo(self, session_id: str) -> Dict:
        """Stop a topic echo session"""
        with self.lock:
            if session_id not in self.echo_sessions:
                return {'error': 'Session not found'}
            
            session = self.echo_sessions[session_id]
            
            if session.subscription and self.node:
                try:
                    self.node.destroy_subscription(session.subscription)
                except Exception as e:
                    logger.warning(f"Error destroying subscription: {e}")
            
            session.active = False
            
            logger.info(f"Stopped echo session {session_id}")
            return {
                'success': True,
                'session': session.to_dict()
            }
    
    def get_echo_messages(self, session_id: str, limit: Optional[int] = 50) -> Dict:
        """Get messages from an echo session"""
        with self.lock:
            if session_id not in self.echo_sessions:
                return {'error': 'Session not found'}
            
            session = self.echo_sessions[session_id]
            return {
                'session': session.to_dict(),
                'messages': session.get_messages(limit)
            }
    
    def list_echo_sessions(self) -> List[Dict]:
        """List all echo sessions"""
        with self.lock:
            return [s.to_dict() for s in self.echo_sessions.values()]
    
    def cleanup_echo_sessions(self, max_age_sec: float = 300):
        """Clean up old inactive sessions"""
        with self.lock:
            now = time.time()
            to_remove = []
            
            for session_id, session in self.echo_sessions.items():
                if not session.active and (now - session.start_time) > max_age_sec:
                    to_remove.append(session_id)
            
            for session_id in to_remove:
                del self.echo_sessions[session_id]
                logger.info(f"Cleaned up old echo session {session_id}")
    
    # ========== Service Tester ==========
    
    def call_service(self, service_name: str, request_data: Dict, timeout_sec: float = 5.0) -> Dict:
        """
        Call a ROS2 service
        
        Args:
            service_name: Service to call
            request_data: Request parameters as dict
            timeout_sec: Timeout for service call
        
        Returns:
            Call record dict
        """
        if not ROS2_AVAILABLE or not self.node:
            return {'error': 'ROS2 not available'}
        
        call_id = f"call_{int(time.time() * 1000)}"
        start_time = time.time()
        
        try:
            # Get service type
            service_type = self._get_service_type(service_name)
            if not service_type:
                return {'error': f'Service {service_name} not found'}
            
            # Get service class
            srv_class = self._get_service_class(service_type)
            if not srv_class:
                return {'error': f'Could not load service type: {service_type}'}
            
            # Create client
            client = self.node.create_client(srv_class, service_name)
            
            # Wait for service
            if not client.wait_for_service(timeout_sec=2.0):
                record = ServiceCallRecord(
                    call_id=call_id,
                    service_name=service_name,
                    service_type=service_type,
                    request=request_data,
                    success=False,
                    error='Service not available'
                )
                self.service_history.append(record)
                return record.to_dict()
            
            # Build request
            request = srv_class.Request()
            for key, value in request_data.items():
                if hasattr(request, key):
                    setattr(request, key, value)
            
            # Call service
            future = client.call_async(request)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout_sec)
            
            duration_ms = (time.time() - start_time) * 1000
            
            if future.result() is not None:
                # Success
                response_dict = message_to_ordereddict(future.result()) if ROS2_AVAILABLE else {}
                record = ServiceCallRecord(
                    call_id=call_id,
                    service_name=service_name,
                    service_type=service_type,
                    request=request_data,
                    response=response_dict,
                    success=True,
                    duration_ms=duration_ms
                )
            else:
                # Timeout or error
                record = ServiceCallRecord(
                    call_id=call_id,
                    service_name=service_name,
                    service_type=service_type,
                    request=request_data,
                    success=False,
                    error='Call timeout or future exception',
                    duration_ms=duration_ms
                )
            
            # Cleanup client
            self.node.destroy_client(client)
            
            # Add to history
            self.service_history.append(record)
            
            return record.to_dict()
        
        except Exception as e:
            logger.error(f"Error calling service: {e}", exc_info=True)
            record = ServiceCallRecord(
                call_id=call_id,
                service_name=service_name,
                service_type='unknown',
                request=request_data,
                success=False,
                error=str(e)
            )
            self.service_history.append(record)
            return record.to_dict()
    
    def get_service_history(self, limit: int = 50) -> List[Dict]:
        """Get service call history"""
        history = list(self.service_history)
        return [r.to_dict() for r in history[-limit:]]
    
    # ========== Parameter Management ==========
    
    def get_node_parameters(self, node_name: str, use_cache: bool = True) -> Dict:
        """Get all parameters for a node"""
        if not ROS2_AVAILABLE or not self.node:
            return {'error': 'ROS2 not available'}
        
        # Check cache
        if use_cache and node_name in self.parameter_cache:
            cache_age = time.time() - self.parameter_cache_time.get(node_name, 0)
            if cache_age < self.cache_ttl:
                return {
                    'node_name': node_name,
                    'parameters': self.parameter_cache[node_name],
                    'cached': True,
                    'cache_age': cache_age
                }
        
        try:
            # List parameters
            client = self.node.create_client(
                rosidl_runtime_py.get_service('rcl_interfaces/srv/ListParameters'),
                f'{node_name}/list_parameters'
            )
            
            if not client.wait_for_service(timeout_sec=1.0):
                return {'error': f'Node {node_name} parameter service not available'}
            
            # Get parameter names
            request = client.get_service_request_type()()
            future = client.call_async(request)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=2.0)
            
            if future.result():
                param_names = future.result().result.names
                
                # Get parameter values
                params = {}
                for param_name in param_names:
                    try:
                        value = self._get_parameter_value(node_name, param_name)
                        params[param_name] = value
                    except Exception as e:
                        params[param_name] = {'error': str(e)}
                
                # Update cache
                self.parameter_cache[node_name] = params
                self.parameter_cache_time[node_name] = time.time()
                
                self.node.destroy_client(client)
                
                return {
                    'node_name': node_name,
                    'parameters': params,
                    'cached': False
                }
            else:
                return {'error': 'Failed to list parameters'}
        
        except Exception as e:
            logger.error(f"Error getting node parameters: {e}", exc_info=True)
            return {'error': str(e)}
    
    def set_parameter(self, node_name: str, param_name: str, param_value: Any, param_type: str) -> Dict:
        """Set a parameter value"""
        if not ROS2_AVAILABLE or not self.node:
            return {'error': 'ROS2 not available'}
        
        try:
            # Create parameter
            if param_type == 'int':
                param = Parameter(param_name, Parameter.Type.INTEGER, int(param_value))
            elif param_type == 'float':
                param = Parameter(param_name, Parameter.Type.DOUBLE, float(param_value))
            elif param_type == 'bool':
                param = Parameter(param_name, Parameter.Type.BOOL, bool(param_value))
            elif param_type == 'string':
                param = Parameter(param_name, Parameter.Type.STRING, str(param_value))
            else:
                return {'error': f'Unsupported parameter type: {param_type}'}
            
            # Set parameter via service
            client = self.node.create_client(
                rosidl_runtime_py.get_service('rcl_interfaces/srv/SetParameters'),
                f'{node_name}/set_parameters'
            )
            
            if not client.wait_for_service(timeout_sec=1.0):
                return {'error': f'Node {node_name} set_parameters service not available'}
            
            request = client.get_service_request_type()()
            request.parameters = [param.to_parameter_msg()]
            
            future = client.call_async(request)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=2.0)
            
            self.node.destroy_client(client)
            
            if future.result():
                results = future.result().results
                if results and results[0].successful:
                    # Invalidate cache
                    if node_name in self.parameter_cache:
                        del self.parameter_cache[node_name]
                    
                    return {
                        'success': True,
                        'node_name': node_name,
                        'param_name': param_name,
                        'param_value': param_value
                    }
                else:
                    reason = results[0].reason if results else 'Unknown error'
                    return {'error': f'Failed to set parameter: {reason}'}
            else:
                return {'error': 'Set parameter call failed'}
        
        except Exception as e:
            logger.error(f"Error setting parameter: {e}", exc_info=True)
            return {'error': str(e)}
    
    # ========== Helper Methods ==========
    
    def _get_topic_type(self, topic_name: str) -> Optional[str]:
        """Get message type for a topic"""
        if not self.node:
            return None
        
        topic_list = self.node.get_topic_names_and_types()
        for name, types in topic_list:
            if name == topic_name:
                return types[0] if types else None
        return None
    
    def _get_service_type(self, service_name: str) -> Optional[str]:
        """Get service type"""
        if not self.node:
            return None
        
        service_list = self.node.get_service_names_and_types()
        for name, types in service_list:
            if name == service_name:
                return types[0] if types else None
        return None
    
    def _get_message_class(self, message_type: str):
        """Get message class from type string"""
        try:
            module_name, class_name = message_type.rsplit('/', 1)
            module_name = module_name.replace('/', '.')
            module = __import__(module_name + '.msg', fromlist=[class_name])
            return getattr(module, class_name)
        except Exception as e:
            logger.error(f"Error loading message class {message_type}: {e}")
            return None
    
    def _get_service_class(self, service_type: str):
        """Get service class from type string"""
        try:
            module_name, class_name = service_type.rsplit('/', 1)
            module_name = module_name.replace('/', '.')
            module = __import__(module_name + '.srv', fromlist=[class_name])
            return getattr(module, class_name)
        except Exception as e:
            logger.error(f"Error loading service class {service_type}: {e}")
            return None
    
    def _get_parameter_value(self, node_name: str, param_name: str) -> Any:
        """Get single parameter value"""
        # This is a simplified version - full implementation would use GetParameters service
        return {'value': None, 'type': 'unknown'}


# Singleton instance
_debug_tools_service: Optional[DebugToolsService] = None


def get_debug_tools_service(node: Optional[Node] = None, max_echo_sessions: int = 3) -> DebugToolsService:
    """Get or create debug tools service singleton"""
    global _debug_tools_service
    if _debug_tools_service is None:
        _debug_tools_service = DebugToolsService(node, max_echo_sessions)
    return _debug_tools_service


def initialize_debug_tools(node: Optional[Node] = None, max_echo_sessions: int = 3):
    """Initialize debug tools service"""
    return get_debug_tools_service(node, max_echo_sessions)
