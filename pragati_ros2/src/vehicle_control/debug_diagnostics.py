#!/usr/bin/env python3
"""
Debug diagnostics health history issue
"""

import asyncio
import sys
import time
import threading
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from vehicle_control.integration.system_diagnostics import (
    VehicleSystemDiagnostics,
    DiagnosticLevel,
)


async def main():
    print("=== DIAGNOSTICS DEBUG TEST ===")

    # Create diagnostics with no motor controller or GPIO
    print("1. Creating diagnostics (no motor controller)...")
    diagnostics = VehicleSystemDiagnostics(
        None, None, DiagnosticLevel.DETAILED  # No GPIO
    )

    print("2. Testing single health check...")
    report = await diagnostics.perform_system_health_check()
    print(f"   Report generated: {report is not None}")
    print(f"   Overall status: {report.overall_status}")
    print(f"   Subsystems: {list(report.subsystems.keys())}")

    print("3. Testing health history before continuous diagnostics...")
    history_before = diagnostics.get_health_history()
    print(f"   History length: {len(history_before)}")

    print("4. Starting continuous diagnostics...")
    diagnostics.start_continuous_diagnostics(interval=0.1)

    print("5. Checking if diagnostic thread is running...")
    print(f"   Running: {diagnostics._running}")
    print(
        f"   Thread alive: {diagnostics._diagnostic_thread.is_alive() if diagnostics._diagnostic_thread else False}"
    )

    print("6. Waiting 0.5 seconds for diagnostic cycles...")
    await asyncio.sleep(0.5)

    print("7. Checking health history during continuous diagnostics...")
    history_during = diagnostics.get_health_history()
    print(f"   History length: {len(history_during)}")

    if len(history_during) > 0:
        print(f"   Latest report timestamp: {history_during[-1].timestamp}")
        print(f"   Latest report status: {history_during[-1].overall_status}")

    print("8. Stopping continuous diagnostics...")
    diagnostics.stop_continuous_diagnostics()

    print("9. Final health history check...")
    history_final = diagnostics.get_health_history()
    print(f"    Final history length: {len(history_final)}")

    # Check internal state
    print("10. Checking internal diagnostics state...")
    print(f"    _health_history deque length: {len(diagnostics._health_history)}")
    print(f"    _running: {diagnostics._running}")
    print(f"    Thread object: {diagnostics._diagnostic_thread}")

    # Let's also check if there are any exceptions in the diagnostic loop
    print("11. Testing manual diagnostic loop execution...")
    try:
        # Simulate what happens in the diagnostic loop
        health_report = await diagnostics.perform_system_health_check()
        diagnostics._health_history.append(health_report)
        print(
            f"    Manual append successful, history length now: {len(diagnostics._health_history)}"
        )

        final_check = diagnostics.get_health_history()
        print(f"    get_health_history() returns length: {len(final_check)}")

    except Exception as e:
        print(f"    Error in manual diagnostic: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
