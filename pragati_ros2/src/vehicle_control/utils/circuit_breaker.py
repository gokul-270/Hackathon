#!/usr/bin/env python3
"""
Circuit Breaker Pattern Implementation
Provides fault tolerance and prevents cascade failures
"""

import time
import asyncio
import logging
from enum import Enum
from typing import Callable, Any, Optional, Type, Union
from functools import wraps
from dataclasses import dataclass


class CircuitBreakerState(Enum):
    """Circuit breaker states"""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Blocking calls due to failures
    HALF_OPEN = "HALF_OPEN"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: Type[Exception] = Exception
    success_threshold: int = 2  # Required successes in HALF_OPEN to close


class CircuitBreakerError(Exception):
    """Circuit breaker is open"""

    pass


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting against cascade failures
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
        success_threshold: int = 2,
    ):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before trying again (seconds)
            expected_exception: Exception type that triggers circuit breaker
            success_threshold: Successes needed in HALF_OPEN to close circuit
        """
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception,
            success_threshold=success_threshold,
        )

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.logger = logging.getLogger(__name__)

    def __call__(self, func: Callable) -> Callable:
        """Decorator for protecting functions"""
        if asyncio.iscoroutinefunction(func):
            return self._async_wrapper(func)
        else:
            return self._sync_wrapper(func)

    def _sync_wrapper(self, func: Callable) -> Callable:
        """Synchronous function wrapper"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            return self._execute_call(func, *args, **kwargs)

        return wrapper

    def _async_wrapper(self, func: Callable) -> Callable:
        """Asynchronous function wrapper"""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self._execute_async_call(func, *args, **kwargs)

        return wrapper

    def _execute_call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute synchronous call with circuit breaker protection"""
        if not self._allow_request():
            raise CircuitBreakerError(f"Circuit breaker is {self.state.value}")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            # Check if this exception type should trigger circuit breaker
            if isinstance(e, self.config.expected_exception):
                self._on_failure()
            raise e

    async def _execute_async_call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute asynchronous call with circuit breaker protection"""
        if not self._allow_request():
            raise CircuitBreakerError(f"Circuit breaker is {self.state.value}")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            # Check if this exception type should trigger circuit breaker
            if isinstance(e, self.config.expected_exception):
                self._on_failure()
            raise e

    def _allow_request(self) -> bool:
        """Check if request should be allowed"""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            return self._should_attempt_reset()
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True
        return False

    def _should_attempt_reset(self) -> bool:
        """Check if we should try to reset the circuit breaker"""
        if self.last_failure_time is None:
            return True

        time_since_failure = time.time() - self.last_failure_time
        if time_since_failure >= self.config.recovery_timeout:
            self.logger.debug("Circuit breaker attempting reset after timeout")
            self.state = CircuitBreakerState.HALF_OPEN
            self.success_count = 0
            return True
        return False

    def _on_success(self):
        """Handle successful call"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.logger.debug("Circuit breaker closing after successful recovery")
                self._reset()
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0  # Reset failure count on success

    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.logger.debug("Circuit breaker opening after failure during recovery")
            self.state = CircuitBreakerState.OPEN
        elif (
            self.state == CircuitBreakerState.CLOSED
            and self.failure_count >= self.config.failure_threshold
        ):
            self.logger.debug(f"Circuit breaker opening after {self.failure_count} failures")
            self.state = CircuitBreakerState.OPEN

    def _reset(self):
        """Reset circuit breaker to closed state"""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    def get_stats(self) -> dict:
        """Get circuit breaker statistics"""
        return {
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure_time': self.last_failure_time,
            'time_since_failure': (
                time.time() - self.last_failure_time if self.last_failure_time else None
            ),
        }

    def force_open(self):
        """Manually open circuit breaker"""
        self.logger.debug("Circuit breaker manually opened")
        self.state = CircuitBreakerState.OPEN
        self.last_failure_time = time.time()

    def force_close(self):
        """Manually close circuit breaker"""
        self.logger.debug("Circuit breaker manually closed")
        self._reset()


class RetryPolicy:
    """
    Retry policy decorator with exponential backoff
    """

    def __init__(
        self,
        max_attempts: int = 3,
        backoff_factor: float = 1.5,
        max_delay: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        """
        Initialize retry policy

        Args:
            max_attempts: Maximum number of retry attempts
            backoff_factor: Exponential backoff multiplier
            max_delay: Maximum delay between retries
            expected_exception: Exception type that triggers retry
        """
        self.max_attempts = max_attempts
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.expected_exception = expected_exception
        self.logger = logging.getLogger(__name__)

    def __call__(self, func: Callable) -> Callable:
        """Decorator for adding retry logic"""
        if asyncio.iscoroutinefunction(func):
            return self._async_wrapper(func)
        else:
            return self._sync_wrapper(func)

    def _sync_wrapper(self, func: Callable) -> Callable:
        """Synchronous function wrapper"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            return self._execute_with_retry(func, *args, **kwargs)

        return wrapper

    def _async_wrapper(self, func: Callable) -> Callable:
        """Asynchronous function wrapper"""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self._execute_async_with_retry(func, *args, **kwargs)

        return wrapper

    def _execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute synchronous function with retry logic"""
        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)
            except self.expected_exception as e:
                last_exception = e
                if attempt < self.max_attempts - 1:  # Don't sleep on last attempt
                    delay = min(self.backoff_factor**attempt, self.max_delay)
                    self.logger.debug(
                        f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(
                        delay
                    )  # BLOCKING_SLEEP_OK: circuit breaker backoff — runs in caller thread context — reviewed 2026-03-14
                else:
                    self.logger.debug(f"All {self.max_attempts} attempts failed")

        # Re-raise the last exception
        if last_exception:
            raise last_exception

    async def _execute_async_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute asynchronous function with retry logic"""
        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except self.expected_exception as e:
                last_exception = e
                if attempt < self.max_attempts - 1:  # Don't sleep on last attempt
                    delay = min(self.backoff_factor**attempt, self.max_delay)
                    self.logger.debug(
                        f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.debug(f"All {self.max_attempts} attempts failed")

        # Re-raise the last exception
        if last_exception:
            raise last_exception
