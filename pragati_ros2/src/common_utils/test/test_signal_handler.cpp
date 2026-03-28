// Copyright 2026 Pragati Robotics Team
// SPDX-License-Identifier: Apache-2.0
//
// Tests for pragati::install_signal_handlers() / shutdown_requested().
//
// Signal handler tests require process isolation because:
// (a) Signals are process-global — one test's handler registration affects others.
// (b) SIGSEGV/SIGABRT terminate the process, so crash handler tests must fork().
//
// We use fork()+waitpid() for tests that send real signals.  The parent
// asserts on the child's exit status / output.

#include "common_utils/signal_handler.hpp"

#include <gtest/gtest.h>

#include <sys/wait.h>
#include <unistd.h>

#include <atomic>
#include <cstring>
#include <thread>
#include <vector>

// ---------------------------------------------------------------------------
// Helper: run a function in a forked child, return exit status.
// ---------------------------------------------------------------------------
static int run_in_child(std::function<void()> fn)
{
  pid_t pid = fork();
  if (pid == 0) {
    // Child
    fn();
    _exit(0);  // success
  }
  // Parent
  int status = 0;
  waitpid(pid, &status, 0);
  return status;
}

// ---------------------------------------------------------------------------
// Helper: run a function in a forked child, capture stderr, return status.
// ---------------------------------------------------------------------------
struct ChildResult
{
  int status;
  std::string stderr_output;
};

static ChildResult run_in_child_capture_stderr(std::function<void()> fn)
{
  int pipe_fds[2];
  EXPECT_EQ(pipe(pipe_fds), 0);

  pid_t pid = fork();
  if (pid == 0) {
    // Child: redirect stderr to pipe
    close(pipe_fds[0]);
    dup2(pipe_fds[1], STDERR_FILENO);
    close(pipe_fds[1]);
    fn();
    _exit(0);
  }

  // Parent: read from pipe
  close(pipe_fds[1]);
  std::string output;
  char buf[256];
  ssize_t n;
  while ((n = read(pipe_fds[0], buf, sizeof(buf))) > 0) {
    output.append(buf, static_cast<size_t>(n));
  }
  close(pipe_fds[0]);

  int status = 0;
  waitpid(pid, &status, 0);
  return {status, output};
}

// ===========================================================================
// Task 4.6: shutdown_requested() is false before any signal
// ===========================================================================
TEST(SignalHandler, ShutdownRequestedFalseBeforeAnySignal)
{
  int status = run_in_child([]() {
    pragati::install_signal_handlers();
    if (pragati::shutdown_requested()) {
      _exit(1);  // FAIL — should be false
    }
    _exit(0);  // PASS
  });
  EXPECT_TRUE(WIFEXITED(status));
  EXPECT_EQ(WEXITSTATUS(status), 0) << "shutdown_requested() should be false before any signal";
}

// ===========================================================================
// Task 4.4: SIGINT triggers shutdown flag
// ===========================================================================
TEST(SignalHandler, SIGINTSetsShutdownFlag)
{
  int status = run_in_child([]() {
    pragati::install_signal_handlers();

    // Send SIGINT to self
    raise(SIGINT);

    // After returning from handler, check flag
    if (!pragati::shutdown_requested()) {
      _exit(1);  // FAIL
    }
    _exit(0);  // PASS
  });
  EXPECT_TRUE(WIFEXITED(status));
  EXPECT_EQ(WEXITSTATUS(status), 0) << "SIGINT should set shutdown flag";
}

// ===========================================================================
// Task 4.5: SIGTERM triggers shutdown flag
// ===========================================================================
TEST(SignalHandler, SIGTERMSetsShutdownFlag)
{
  int status = run_in_child([]() {
    pragati::install_signal_handlers();

    raise(SIGTERM);

    if (!pragati::shutdown_requested()) {
      _exit(1);
    }
    _exit(0);
  });
  EXPECT_TRUE(WIFEXITED(status));
  EXPECT_EQ(WEXITSTATUS(status), 0) << "SIGTERM should set shutdown flag";
}

// ===========================================================================
// Task 4.7: Crash handler logs on SIGSEGV when enabled
// ===========================================================================
TEST(SignalHandler, CrashHandlerLogsOnSIGSEGV)
{
  auto result = run_in_child_capture_stderr([]() {
    pragati::install_signal_handlers(true);  // enable crash handler
    raise(SIGSEGV);
    // Should not reach here — SIGSEGV re-raised with default handler
    _exit(99);
  });

  // Child should have been killed by SIGSEGV (default handler after re-raise)
  EXPECT_TRUE(WIFSIGNALED(result.status))
    << "Child should be killed by SIGSEGV after crash handler re-raises";
  EXPECT_EQ(WTERMSIG(result.status), SIGSEGV);

  // Crash message should appear in stderr
  EXPECT_NE(result.stderr_output.find("[CRASH]"), std::string::npos)
    << "Crash handler should log [CRASH] to stderr. Got: " << result.stderr_output;
}

// ===========================================================================
// Task 4.8: Crash handler not active when disabled (default)
// ===========================================================================
TEST(SignalHandler, CrashHandlerDisabledByDefault)
{
  auto result = run_in_child_capture_stderr([]() {
    pragati::install_signal_handlers();  // default — no crash handler
    raise(SIGSEGV);
    _exit(99);
  });

  // Child should still be killed by SIGSEGV (default OS handler)
  EXPECT_TRUE(WIFSIGNALED(result.status));
  EXPECT_EQ(WTERMSIG(result.status), SIGSEGV);

  // No [CRASH] message — our handler was not registered
  EXPECT_EQ(result.stderr_output.find("[CRASH]"), std::string::npos)
    << "Crash handler should NOT be active when disabled. Got: " << result.stderr_output;
}

// ===========================================================================
// Task 4.9: Concurrent reads from multiple threads
// ===========================================================================
TEST(SignalHandler, ConcurrentReadsAreThreadSafe)
{
  int status = run_in_child([]() {
    pragati::install_signal_handlers();

    constexpr int kNumThreads = 8;
    constexpr int kReadsPerThread = 10000;
    std::atomic<int> false_count{0};
    std::atomic<int> true_count{0};

    // Phase 1: all threads read before signal — should all see false
    std::vector<std::thread> threads;
    threads.reserve(kNumThreads);
    for (int i = 0; i < kNumThreads; ++i) {
      threads.emplace_back([&]() {
        for (int j = 0; j < kReadsPerThread; ++j) {
          if (pragati::shutdown_requested()) {
            true_count.fetch_add(1, std::memory_order_relaxed);
          } else {
            false_count.fetch_add(1, std::memory_order_relaxed);
          }
        }
      });
    }
    for (auto & t : threads) {
      t.join();
    }

    if (true_count.load() != 0) {
      _exit(1);  // saw true before signal — FAIL
    }

    // Phase 2: send signal, then read from multiple threads
    raise(SIGINT);

    std::atomic<int> post_true_count{0};
    std::vector<std::thread> threads2;
    threads2.reserve(kNumThreads);
    for (int i = 0; i < kNumThreads; ++i) {
      threads2.emplace_back([&]() {
        for (int j = 0; j < kReadsPerThread; ++j) {
          if (pragati::shutdown_requested()) {
            post_true_count.fetch_add(1, std::memory_order_relaxed);
          }
        }
      });
    }
    for (auto & t : threads2) {
      t.join();
    }

    // After signal, all reads should see true
    if (post_true_count.load() != kNumThreads * kReadsPerThread) {
      _exit(2);  // not all reads saw true — FAIL
    }

    _exit(0);
  });

  EXPECT_TRUE(WIFEXITED(status));
  EXPECT_EQ(WEXITSTATUS(status), 0) << "Concurrent reads should be safe and consistent";
}

// ===========================================================================
// Task 4.10: Double-init is idempotent (no-op with warning)
// ===========================================================================
TEST(SignalHandler, DoubleInitIsIdempotent)
{
  auto result = run_in_child_capture_stderr([]() {
    pragati::install_signal_handlers();
    pragati::install_signal_handlers();  // second call — should warn

    // Signal handling should still work
    raise(SIGINT);
    if (!pragati::shutdown_requested()) {
      _exit(1);
    }
    _exit(0);
  });

  EXPECT_TRUE(WIFEXITED(result.status));
  EXPECT_EQ(WEXITSTATUS(result.status), 0)
    << "Double-init should not break shutdown_requested()";

  // Warning should appear in stderr
  EXPECT_NE(result.stderr_output.find("WARN"), std::string::npos)
    << "Second call should log a warning. Got: " << result.stderr_output;
}
