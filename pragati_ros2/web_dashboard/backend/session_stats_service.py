#!/usr/bin/env python3
"""
Session Statistics Tracking Service
====================================

Tracks operational statistics per session:
- Cotton detection metrics (detected, picked, failed)
- Camera performance (images captured, FPS, drops)
- Motor health (temperature, current, errors)
- Vehicle stats (battery, distance, runtime)
"""

import time
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import threading


@dataclass
class SessionStats:
    """Statistics for a single operation session"""
    session_id: str
    start_time: float
    end_time: Optional[float] = None
    
    # Cotton detection
    images_captured: int = 0
    cottons_detected: int = 0
    cottons_picked: int = 0
    cottons_failed: int = 0
    detection_confidence_avg: float = 0.0
    
    # Camera stats
    camera_fps_avg: float = 0.0
    camera_frames_dropped: int = 0
    camera_exposure_avg: float = 0.0
    camera_errors: int = 0
    
    # Motor stats (aggregated)
    motor_temp_max: float = 0.0
    motor_temp_avg: float = 0.0
    motor_current_max: float = 0.0
    motor_errors_total: int = 0
    
    # Vehicle/Robot stats
    battery_start: float = 100.0
    battery_end: float = 100.0
    battery_consumed: float = 0.0
    distance_traveled: float = 0.0
    operation_time_sec: float = 0.0
    
    # Additional metrics
    cycle_count: int = 0
    avg_cycle_time: float = 0.0
    emergency_stops: int = 0
    warnings_count: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['duration_sec'] = self.get_duration()
        data['success_rate'] = self.get_success_rate()
        data['efficiency'] = self.get_efficiency()
        return data
    
    def get_duration(self) -> float:
        """Get session duration in seconds"""
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time
    
    def get_success_rate(self) -> float:
        """Calculate cotton picking success rate"""
        total = self.cottons_picked + self.cottons_failed
        if total == 0:
            return 0.0
        return (self.cottons_picked / total) * 100
    
    def get_efficiency(self) -> float:
        """Calculate picks per hour"""
        duration_hours = self.get_duration() / 3600
        if duration_hours == 0:
            return 0.0
        return self.cottons_picked / duration_hours


class SessionStatsService:
    """
    Service to track and manage operation session statistics
    """
    
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_session: Optional[SessionStats] = None
        self.session_history: List[SessionStats] = []
        self.lock = threading.RLock()
        
        # Load previous sessions
        self._load_sessions()
    
    # ========== Session Management ==========
    
    def start_session(self) -> SessionStats:
        """Start a new operation session"""
        with self.lock:
            if self.current_session and not self.current_session.end_time:
                # End previous session
                self.end_session()
            
            session_id = f"session_{int(time.time())}"
            self.current_session = SessionStats(
                session_id=session_id,
                start_time=time.time()
            )
            
            print(f"📊 Started new session: {session_id}")
            return self.current_session
    
    def end_session(self) -> Optional[SessionStats]:
        """End current session"""
        with self.lock:
            if not self.current_session:
                return None
            
            self.current_session.end_time = time.time()
            self.current_session.operation_time_sec = self.current_session.get_duration()
            
            # Save to history
            self.session_history.append(self.current_session)
            self._save_session(self.current_session)
            
            session = self.current_session
            self.current_session = None
            
            print(f"📊 Ended session: {session.session_id} (duration: {session.get_duration():.1f}s)")
            return session
    
    def get_current_session(self) -> Optional[SessionStats]:
        """Get current active session"""
        with self.lock:
            return self.current_session
    
    def get_session_history(self, limit: int = 10) -> List[Dict]:
        """Get recent session history"""
        with self.lock:
            recent = self.session_history[-limit:]
            return [s.to_dict() for s in reversed(recent)]
    
    # ========== Update Statistics ==========
    
    def update_detection_stats(self, detected: int = 0, picked: int = 0, failed: int = 0,
                               confidence: Optional[float] = None):
        """Update cotton detection statistics"""
        with self.lock:
            if not self.current_session:
                return
            
            self.current_session.cottons_detected += detected
            self.current_session.cottons_picked += picked
            self.current_session.cottons_failed += failed
            
            if confidence is not None:
                # Update average confidence
                total = self.current_session.cottons_detected
                if total > 0:
                    current_avg = self.current_session.detection_confidence_avg
                    self.current_session.detection_confidence_avg = (
                        (current_avg * (total - detected) + confidence * detected) / total
                    )
    
    def update_camera_stats(self, images: int = 0, fps: Optional[float] = None,
                           frames_dropped: int = 0, errors: int = 0):
        """Update camera statistics"""
        with self.lock:
            if not self.current_session:
                return
            
            self.current_session.images_captured += images
            self.current_session.camera_frames_dropped += frames_dropped
            self.current_session.camera_errors += errors
            
            if fps is not None:
                # Update average FPS
                count = self.current_session.images_captured
                if count > 0:
                    current_avg = self.current_session.camera_fps_avg
                    self.current_session.camera_fps_avg = (
                        (current_avg * (count - images) + fps * images) / count
                    )
    
    def update_motor_stats(self, temp: Optional[float] = None, current: Optional[float] = None,
                          errors: int = 0):
        """Update motor statistics"""
        with self.lock:
            if not self.current_session:
                return
            
            if temp is not None:
                self.current_session.motor_temp_max = max(
                    self.current_session.motor_temp_max, temp
                )
                # Simple moving average
                if self.current_session.motor_temp_avg == 0:
                    self.current_session.motor_temp_avg = temp
                else:
                    self.current_session.motor_temp_avg = (
                        self.current_session.motor_temp_avg * 0.9 + temp * 0.1
                    )
            
            if current is not None:
                self.current_session.motor_current_max = max(
                    self.current_session.motor_current_max, current
                )
            
            self.current_session.motor_errors_total += errors
    
    def update_vehicle_stats(self, battery: Optional[float] = None, 
                            distance_delta: float = 0.0):
        """Update vehicle/robot statistics"""
        with self.lock:
            if not self.current_session:
                return
            
            if battery is not None:
                self.current_session.battery_end = battery
                self.current_session.battery_consumed = (
                    self.current_session.battery_start - battery
                )
            
            self.current_session.distance_traveled += distance_delta
    
    def record_cycle(self, cycle_time: float):
        """Record a picking cycle"""
        with self.lock:
            if not self.current_session:
                return
            
            self.current_session.cycle_count += 1
            
            # Update average cycle time
            count = self.current_session.cycle_count
            current_avg = self.current_session.avg_cycle_time
            self.current_session.avg_cycle_time = (
                (current_avg * (count - 1) + cycle_time) / count
            )
    
    def record_event(self, event_type: str):
        """Record special events"""
        with self.lock:
            if not self.current_session:
                return
            
            if event_type == "emergency_stop":
                self.current_session.emergency_stops += 1
            elif event_type == "warning":
                self.current_session.warnings_count += 1
    
    # ========== Persistence ==========
    
    def _save_session(self, session: SessionStats):
        """Save session to disk"""
        try:
            session_file = self.data_dir / f"{session.session_id}.json"
            with open(session_file, 'w') as f:
                json.dump(session.to_dict(), f, indent=2)
        except Exception as e:
            print(f"Error saving session: {e}")
    
    def _load_sessions(self):
        """Load session history from disk"""
        try:
            session_files = sorted(self.data_dir.glob("session_*.json"))
            # Load last 50 sessions
            for session_file in session_files[-50:]:
                try:
                    with open(session_file, 'r') as f:
                        data = json.load(f)
                        # Reconstruct SessionStats (simplified)
                        session = SessionStats(
                            session_id=data['session_id'],
                            start_time=data['start_time'],
                            end_time=data.get('end_time')
                        )
                        # Copy all fields
                        for key, value in data.items():
                            if hasattr(session, key):
                                setattr(session, key, value)
                        
                        self.session_history.append(session)
                except Exception as e:
                    print(f"Error loading session {session_file}: {e}")
        except Exception as e:
            print(f"Error loading sessions: {e}")
    
    # ========== Summary & Reports ==========
    
    def get_summary(self) -> Dict:
        """Get summary of current session"""
        with self.lock:
            if not self.current_session:
                return {"active": False, "message": "No active session"}
            
            return {
                "active": True,
                "session_id": self.current_session.session_id,
                "duration_sec": self.current_session.get_duration(),
                "stats": self.current_session.to_dict()
            }
    
    def get_totals(self) -> Dict:
        """Get lifetime totals across all sessions"""
        with self.lock:
            totals = {
                "total_sessions": len(self.session_history),
                "total_images": sum(s.images_captured for s in self.session_history),
                "total_detected": sum(s.cottons_detected for s in self.session_history),
                "total_picked": sum(s.cottons_picked for s in self.session_history),
                "total_failed": sum(s.cottons_failed for s in self.session_history),
                "total_distance": sum(s.distance_traveled for s in self.session_history),
                "total_runtime": sum(s.get_duration() for s in self.session_history),
                "avg_success_rate": 0.0
            }
            
            # Calculate average success rate
            rates = [s.get_success_rate() for s in self.session_history if s.end_time]
            if rates:
                totals["avg_success_rate"] = sum(rates) / len(rates)
            
            return totals


# Singleton instance
_session_stats_service: Optional[SessionStatsService] = None


def get_session_stats_service() -> SessionStatsService:
    """Get or create session stats service singleton"""
    global _session_stats_service
    if _session_stats_service is None:
        _session_stats_service = SessionStatsService()
    return _session_stats_service


def initialize_session_stats() -> SessionStatsService:
    """Initialize session stats service"""
    return get_session_stats_service()
