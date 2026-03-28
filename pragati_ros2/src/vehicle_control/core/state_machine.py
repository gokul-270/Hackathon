"""
Vehicle State Machine
Manages vehicle operational states and transitions
"""
import logging
from enum import Enum, auto
from typing import Optional, Callable, Dict, Set
from dataclasses import dataclass
from threading import Lock
import time

try:
    from config.constants import VehicleState, ButtonState, PivotDirection
except ImportError:
    # Handle imports for direct execution
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config.constants import VehicleState, ButtonState, PivotDirection


class StateTransition(Enum):
    """State transition triggers"""
    MODE_SWITCH_AUTO = auto()
    MODE_SWITCH_MANUAL = auto()
    DIRECTION_LEFT = auto()
    DIRECTION_RIGHT = auto()
    DIRECTION_NEUTRAL = auto()
    STOP_REQUESTED = auto()
    ERROR_OCCURRED = auto()
    SYSTEM_RESET = auto()
    IDLE_TIMEOUT = auto()
    ACTIVITY_DETECTED = auto()


@dataclass
class StateContext:
    """Context information for state transitions"""
    timestamp: float
    previous_state: VehicleState
    trigger: StateTransition
    metadata: Optional[dict] = None


class VehicleStateMachine:
    """
    Thread-safe state machine for vehicle control
    Manages state transitions and validates operations
    """
    
    def __init__(self):
        self._current_state = VehicleState.UNKNOWN
        self._previous_state = VehicleState.UNKNOWN
        self._state_lock = Lock()
        self._logger = logging.getLogger(__name__)
        
        # State transition callbacks
        self._entry_callbacks: Dict[VehicleState, Callable] = {}
        self._exit_callbacks: Dict[VehicleState, Callable] = {}
        
        # Valid state transitions
        self._valid_transitions = self._build_transition_table()
        
        # State change listeners
        self._listeners: Set[Callable[[StateContext], None]] = set()
    
    def _build_transition_table(self) -> Dict[VehicleState, Set[VehicleState]]:
        """Build valid state transition table"""
        return {
            VehicleState.UNKNOWN: {
                VehicleState.MANUAL_MODE,
                VehicleState.AUTOMATIC_MODE,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.MANUAL_MODE: {
                VehicleState.AUTOMATIC_MODE,
                VehicleState.MANUAL_LEFT,
                VehicleState.MANUAL_RIGHT,
                VehicleState.NONBRAKE_MANUAL,
                VehicleState.STOP_REQUEST,
                VehicleState.ERROR,
                VehicleState.IDLING,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.AUTOMATIC_MODE: {
                VehicleState.MANUAL_MODE,
                VehicleState.STOP_REQUEST,
                VehicleState.ERROR,
                VehicleState.IDLING,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.MANUAL_LEFT: {
                VehicleState.MANUAL_MODE,
                VehicleState.MANUAL_RIGHT,
                VehicleState.NONBRAKE_MANUAL,
                VehicleState.STOP_REQUEST,
                VehicleState.ERROR,
                VehicleState.IDLING,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.MANUAL_RIGHT: {
                VehicleState.MANUAL_MODE,
                VehicleState.MANUAL_LEFT,
                VehicleState.NONBRAKE_MANUAL,
                VehicleState.STOP_REQUEST,
                VehicleState.ERROR,
                VehicleState.IDLING,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.NONBRAKE_MANUAL: {
                VehicleState.MANUAL_MODE,
                VehicleState.MANUAL_LEFT,
                VehicleState.MANUAL_RIGHT,
                VehicleState.STOP_REQUEST,
                VehicleState.ERROR,
                VehicleState.IDLING,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.IDLING: {
                VehicleState.MANUAL_MODE,
                VehicleState.AUTOMATIC_MODE,
                VehicleState.BUSY,
                VehicleState.STOP_REQUEST,
                VehicleState.ERROR,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.BUSY: {
                VehicleState.MANUAL_MODE,
                VehicleState.AUTOMATIC_MODE,
                VehicleState.IDLING,
                VehicleState.STOP_REQUEST,
                VehicleState.ERROR,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.ERROR: {
                VehicleState.MANUAL_MODE,
                VehicleState.AUTOMATIC_MODE,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.STOP_REQUEST: {
                VehicleState.MANUAL_MODE,
                VehicleState.AUTOMATIC_MODE,
                VehicleState.IDLING,
                VehicleState.ERROR,
                VehicleState.SYSTEM_RESET
            },
            VehicleState.SYSTEM_RESET: {
                VehicleState.UNKNOWN,
                VehicleState.MANUAL_MODE,
                VehicleState.AUTOMATIC_MODE
            }
        }
    
    @property
    def current_state(self) -> VehicleState:
        """Get current state (thread-safe)"""
        with self._state_lock:
            return self._current_state
    
    @property
    def previous_state(self) -> VehicleState:
        """Get previous state (thread-safe)"""
        with self._state_lock:
            return self._previous_state
    
    def transition_to(self, new_state: VehicleState, 
                     trigger: StateTransition,
                     metadata: Optional[dict] = None) -> bool:
        """
        Attempt to transition to new state
        Returns True if transition was successful
        """
        with self._state_lock:
            if not self._is_valid_transition(self._current_state, new_state):
                self._logger.warning(
                    f"Invalid transition from {self._current_state.name} "
                    f"to {new_state.name}"
                )
                return False
            
            # Call exit callback for current state
            if self._current_state in self._exit_callbacks:
                try:
                    self._exit_callbacks[self._current_state]()
                except Exception as e:
                    self._logger.error(
                        f"Error in exit callback for {self._current_state.name}: {e}"
                    )
                    return False
            
            # Update state
            old_state = self._current_state
            self._previous_state = self._current_state
            self._current_state = new_state
            
            # Create context
            context = StateContext(
                timestamp=time.time(),
                previous_state=old_state,
                trigger=trigger,
                metadata=metadata
            )
            
            self._logger.info(
                f"State transition: {old_state.name} -> {new_state.name} "
                f"(trigger: {trigger.name})"
            )
            
            # Call entry callback for new state
            if new_state in self._entry_callbacks:
                try:
                    self._entry_callbacks[new_state]()
                except Exception as e:
                    self._logger.error(
                        f"Error in entry callback for {new_state.name}: {e}"
                    )
                    # Could potentially roll back state here
            
            # Notify listeners
            self._notify_listeners(context)
            
            return True
    
    def _is_valid_transition(self, from_state: VehicleState, 
                           to_state: VehicleState) -> bool:
        """Check if state transition is valid"""
        if from_state not in self._valid_transitions:
            return False
        return to_state in self._valid_transitions[from_state]
    
    def register_entry_callback(self, state: VehicleState, 
                               callback: Callable[[], None]):
        """Register callback for state entry"""
        self._entry_callbacks[state] = callback
    
    def register_exit_callback(self, state: VehicleState,
                              callback: Callable[[], None]):
        """Register callback for state exit"""
        self._exit_callbacks[state] = callback
    
    def add_listener(self, callback: Callable[[StateContext], None]):
        """Add state change listener"""
        self._listeners.add(callback)
    
    def remove_listener(self, callback: Callable[[StateContext], None]):
        """Remove state change listener"""
        self._listeners.discard(callback)
    
    def _notify_listeners(self, context: StateContext):
        """Notify all listeners of state change"""
        for listener in self._listeners:
            try:
                listener(context)
            except Exception as e:
                self._logger.error(f"Error in state change listener: {e}")
    
    def is_in_state(self, *states: VehicleState) -> bool:
        """Check if current state matches any of the given states"""
        return self.current_state in states
    
    def reset(self):
        """Reset state machine to initial state"""
        with self._state_lock:
            self._previous_state = self._current_state
            self._current_state = VehicleState.UNKNOWN
            self._logger.info("State machine reset")
