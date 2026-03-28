// Copyright 2026 Pragati Robotics Team
// SPDX-License-Identifier: Apache-2.0

#include "common_utils/signal_handler.hpp"

#include <atomic>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <execinfo.h>
#include <unistd.h>

namespace pragati
{

namespace
{
std::atomic<bool> g_shutdown_flag{false};
bool g_initialized = false;  // not atomic — only written from main thread

void graceful_signal_handler(int /*signum*/)
{
  // Async-signal-safe: atomic store + write()
  g_shutdown_flag.store(true, std::memory_order_release);
}

// Helper: write an integer as decimal string (async-signal-safe)
void write_int(int fd, int value)
{
  char buf[16];
  int len = 0;
  if (value < 0) {
    (void)write(fd, "-", 1);
    value = -value;
  }
  if (value == 0) {
    (void)write(fd, "0", 1);
    return;
  }
  while (value > 0 && len < 15) {
    buf[len++] = '0' + (value % 10);
    value /= 10;
  }
  // Reverse
  for (int i = len - 1; i >= 0; --i) {
    (void)write(fd, &buf[i], 1);
  }
}

void crash_signal_handler(int signum)
{
  // All functions used here are async-signal-safe on Linux

  const char hdr[] = "\n[CRASH] Fatal signal ";
  (void)write(STDERR_FILENO, hdr, sizeof(hdr) - 1);
  write_int(STDERR_FILENO, signum);

  const char* name = (signum == SIGSEGV) ? " (SIGSEGV)" :
                     (signum == SIGABRT) ? " (SIGABRT)" :
                     (signum == SIGBUS)  ? " (SIGBUS)"  : "";
  (void)write(STDERR_FILENO, name, strlen(name));

  const char nl[] = "\n[CRASH] Backtrace:\n";
  (void)write(STDERR_FILENO, nl, sizeof(nl) - 1);

  // backtrace + backtrace_symbols_fd are async-signal-safe on glibc/Linux
  void* frames[64];
  int depth = backtrace(frames, 64);
  backtrace_symbols_fd(frames, depth, STDERR_FILENO);

  const char end[] = "[CRASH] End backtrace. Terminating.\n";
  (void)write(STDERR_FILENO, end, sizeof(end) - 1);

  // Restore default handler and re-raise to get a core dump
  std::signal(signum, SIG_DFL);
  raise(signum);
}

}  // namespace

void install_signal_handlers(bool enable_crash_handler)
{
  if (g_initialized) {
    const char warn[] =
      "[WARN] pragati::install_signal_handlers() called more than once — ignoring.\n";
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-vararg)
    (void)write(STDERR_FILENO, warn, sizeof(warn) - 1);
    return;
  }
  g_initialized = true;

  // Graceful shutdown on SIGINT / SIGTERM
  struct sigaction sa{};
  sa.sa_handler = graceful_signal_handler;
  sigemptyset(&sa.sa_mask);
  sa.sa_flags = 0;  // no SA_RESTART — let blocking syscalls return EINTR

  sigaction(SIGINT, &sa, nullptr);
  sigaction(SIGTERM, &sa, nullptr);

  if (enable_crash_handler) {
    struct sigaction crash_sa{};
    crash_sa.sa_handler = crash_signal_handler;
    sigemptyset(&crash_sa.sa_mask);
    crash_sa.sa_flags = 0;

    sigaction(SIGSEGV, &crash_sa, nullptr);
    sigaction(SIGABRT, &crash_sa, nullptr);
  }
}

bool shutdown_requested()
{
  return g_shutdown_flag.load(std::memory_order_acquire);
}

}  // namespace pragati
