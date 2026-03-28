// Copyright 2026 Pragati Robotics Team
// SPDX-License-Identifier: Apache-2.0
//
// Shared signal handler for Pragati ROS2 nodes.
// Provides a single point for SIGINT/SIGTERM handling with an atomic
// shutdown flag, plus an optional crash handler for SIGSEGV/SIGABRT.
//
// Usage:
//   #include <common_utils/signal_handler.hpp>
//
//   int main() {
//     pragati::install_signal_handlers();          // SIGINT + SIGTERM
//     pragati::install_signal_handlers(true);      // + SIGSEGV + SIGABRT crash log
//     while (!pragati::shutdown_requested()) { ... }
//   }

#ifndef COMMON_UTILS__SIGNAL_HANDLER_HPP_
#define COMMON_UTILS__SIGNAL_HANDLER_HPP_

namespace pragati
{

/// Install signal handlers for SIGINT and SIGTERM that set an atomic
/// shutdown flag.  When @p enable_crash_handler is true, additionally
/// install handlers for SIGSEGV and SIGABRT that log a crash message
/// to stderr and re-raise the signal (restoring the default action so
/// a core dump is still produced).
///
/// This function is idempotent: a second call is a no-op and logs a
/// warning to stderr.
///
/// @param enable_crash_handler  If true, register SIGSEGV/SIGABRT handlers.
void install_signal_handlers(bool enable_crash_handler = false);

/// Return true after SIGINT or SIGTERM has been received.
/// Thread-safe (backed by std::atomic<bool>).
bool shutdown_requested();

}  // namespace pragati

#endif  // COMMON_UTILS__SIGNAL_HANDLER_HPP_
