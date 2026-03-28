#!/usr/bin/env python3
"""
Comprehensive System Validation Script
Tests actual functionality beyond what pytest might miss
"""

import asyncio
import sys
import time
import traceback
import logging
from typing import List, Tuple, Any
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

# Import components to test
from vehicle_control.utils.circuit_breaker import CircuitBreaker, CircuitBreakerError
from vehicle_control.utils.configuration_manager import ConfigurationManager


class ValidationResult:
    def __init__(
        self,
        name: str,
        passed: bool = True,
        details: str = "",
        duration: float = 0.0,
        warnings: List[str] = None,
    ):
        self.name = name
        self.passed = passed
        self.details = details
        self.duration = duration
        self.warnings = warnings or []


class SystemValidator:
    def __init__(self):
        self.results: List[ValidationResult] = []
        self.logger = self._setup_logger()

    def _setup_logger(self):
        logger = logging.getLogger("SystemValidator")
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(levelname)s: %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def run_all_validations(self) -> bool:
        """Run all validation tests and return overall success"""
        self.logger.info("🔍 Starting comprehensive system validation...")

        validations = [
            self._validate_circuit_breaker_real_usage,
            self._validate_configuration_management,
            self._validate_error_handling,
        ]

        total_passed = 0
        total_warnings = 0

        for validation in validations:
            try:
                start_time = time.time()
                result = validation()
                duration = time.time() - start_time
                result.duration = duration

                self.results.append(result)

                status = "✅ PASS" if result.passed else "❌ FAIL"
                self.logger.info(f"{status} {result.name} ({duration:.2f}s)")

                if result.details:
                    self.logger.info(f"   Details: {result.details}")

                if result.warnings:
                    for warning in result.warnings:
                        self.logger.warning(f"   Warning: {warning}")
                        total_warnings += 1

                if result.passed:
                    total_passed += 1

            except Exception as e:
                duration = time.time() - start_time
                error_result = ValidationResult(
                    validation.__name__, False, f"Exception: {str(e)}", duration
                )
                self.results.append(error_result)
                self.logger.error(
                    f"❌ FAIL {validation.__name__} - Exception: {str(e)}"
                )
                self.logger.debug(traceback.format_exc())

        self._print_summary(total_passed, len(validations), total_warnings)
        return total_passed == len(validations) and total_warnings == 0

    def _validate_circuit_breaker_real_usage(self) -> ValidationResult:
        """Test circuit breaker with real-world scenarios"""
        warnings = []

        # Test with real async function
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        @cb
        async def real_async_operation(should_fail=False):
            await asyncio.sleep(0.01)  # Simulate real async work
            if should_fail:
                raise ConnectionError("Simulated connection failure")
            return "success"

        async def test_sequence():
            # Should work initially
            result = await real_async_operation(False)
            if result != "success":
                return False, "Initial operation failed"

            # Trigger failures
            failure_count = 0
            for _ in range(3):
                try:
                    await real_async_operation(True)
                except ConnectionError:
                    failure_count += 1
                except CircuitBreakerError:
                    break

            # Should be open now
            try:
                await real_async_operation(False)
                return False, "Circuit breaker should be open"
            except CircuitBreakerError:
                pass

            # Test recovery
            await asyncio.sleep(0.15)  # Wait for recovery timeout
            result = await real_async_operation(False)
            return result == "success", "Recovery test"

        try:
            success, details = asyncio.run(test_sequence())
            return ValidationResult(
                "Circuit Breaker Real Usage", success, details, warnings=warnings
            )
        except Exception as e:
            return ValidationResult(
                "Circuit Breaker Real Usage",
                False,
                f"Exception: {str(e)}",
                warnings=warnings,
            )

    def _validate_configuration_management(self) -> ValidationResult:
        """Test configuration management thoroughly"""
        warnings = []

        try:
            config_manager = ConfigurationManager()

            # Test default configuration
            defaults = config_manager.get_default_configuration()
            if not isinstance(defaults, dict):
                return ValidationResult(
                    "Configuration Management", False, "Default config not a dict"
                )

            # Validate defaults
            validation_result = config_manager.validate_configuration(defaults)
            if not validation_result.is_valid:
                warnings.append(f"Default config invalid: {validation_result.errors}")

            # Test parameter access
            config_manager._config = defaults

            joint_names = config_manager.get_parameter("joint_names")
            if not isinstance(joint_names, list):
                warnings.append("joint_names not a list")

            # Test setting valid parameter
            if not config_manager.set_parameter("control_frequency", 75.0):
                warnings.append("Failed to set valid control_frequency")

            # Test setting invalid parameter (should fail)
            # Temporarily suppress logging to avoid excessive error output during validation
            original_level = config_manager.logger.level
            config_manager.logger.setLevel(logging.CRITICAL + 1)  # Suppress all logging
            try:
                invalid_result = config_manager.set_parameter(
                    "control_frequency", -10.0
                )
                if invalid_result:
                    warnings.append("Allowed setting invalid control_frequency")
            finally:
                config_manager.logger.setLevel(
                    original_level
                )  # Restore original logging

            success = len(warnings) == 0
            details = f"Configuration tests completed, {len(warnings)} warnings"

            return ValidationResult(
                "Configuration Management", success, details, warnings=warnings
            )

        except Exception as e:
            return ValidationResult(
                "Configuration Management", False, f"Exception: {str(e)}"
            )

    def _validate_error_handling(self) -> ValidationResult:
        """Test error handling and edge cases"""
        warnings = []

        try:
            # Test circuit breaker with exception types
            cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

            @cb
            def failing_function():
                raise ValueError("Test error")

            # Should raise ValueError first time
            try:
                failing_function()
                warnings.append("Exception not propagated")
            except ValueError:
                pass
            except Exception as e:
                warnings.append(f"Wrong exception type: {type(e)}")

            # Should raise CircuitBreakerError second time
            try:
                failing_function()
                warnings.append("Circuit breaker not triggered")
            except CircuitBreakerError:
                pass
            except Exception as e:
                warnings.append(f"Wrong circuit breaker exception: {type(e)}")

            success = len(warnings) == 0
            details = f"Error handling tests completed, {len(warnings)} issues"

            return ValidationResult(
                "Error Handling", success, details, warnings=warnings
            )

        except Exception as e:
            return ValidationResult("Error Handling", False, f"Exception: {str(e)}")

    def _print_summary(self, passed: int, total: int, warnings: int):
        """Print validation summary"""
        print(f"\n{'='*60}")
        print(f"SYSTEM VALIDATION SUMMARY")
        print(f"{'='*60}")
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Warnings: {warnings}")
        print(f"Success Rate: {(passed/total*100):.1f}%")

        if warnings > 0:
            print(f"\n⚠️  {warnings} warnings detected - system may have issues")

        if passed == total and warnings == 0:
            print(f"\n🎉 All validations passed with no warnings!")
            print(f"System appears to be fully functional.")
        elif passed == total:
            print(f"\n✅ All validations passed but with {warnings} warnings")
            print(f"System functional but may need attention.")
        else:
            print(f"\n❌ {total - passed} validation(s) failed")
            print(f"System has significant issues that need to be addressed.")

        print(f"\nDetailed Results:")
        for result in self.results:
            status = "✅" if result.passed else "❌"
            print(f"{status} {result.name}: {result.details}")
            for warning in result.warnings:
                print(f"   ⚠️  {warning}")


def main():
    """Run comprehensive system validation"""
    validator = SystemValidator()
    success = validator.run_all_validations()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
