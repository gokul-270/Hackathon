/**
 * @file test_async_json_logger.cpp
 * @brief Unit tests for AsyncJsonLogger — background JSON logging off detection hot path
 *
 * Tests the producer-consumer pattern: detection thread queues JSON log tasks,
 * background worker thread serializes and emits them via logger callback.
 */

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "cotton_detection_ros2/async_json_logger.hpp"
#include "cotton_detection_ros2/logging_types.hpp"
#include <nlohmann/json.hpp>

using cotton_detection::LogLevel;
using cotton_detection::LoggerCallback;
using cotton_detection_ros2::AsyncJsonLogger;

/**
 * Helper: collects all log messages for assertion.
 */
class LogCollector {
public:
    LoggerCallback callback() {
        return [this](LogLevel level, const std::string& msg) {
            std::lock_guard<std::mutex> lock(mutex_);
            messages_.push_back(msg);
            levels_.push_back(level);
        };
    }

    std::vector<std::string> messages() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return messages_;
    }

    std::vector<LogLevel> levels() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return levels_;
    }

    size_t count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return messages_.size();
    }

    void wait_for(size_t n, std::chrono::milliseconds timeout = std::chrono::milliseconds(2000)) const {
        auto deadline = std::chrono::steady_clock::now() + timeout;
        while (std::chrono::steady_clock::now() < deadline) {
            if (count() >= n) return;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }

private:
    mutable std::mutex mutex_;
    std::vector<std::string> messages_;
    std::vector<LogLevel> levels_;
};

// ===========================================================================
// Test: log_async with pre-built JSON object
// ===========================================================================
TEST(AsyncJsonLoggerTest, LogsPrebuiltJsonObject) {
    LogCollector collector;
    AsyncJsonLogger logger(collector.callback(), 5);
    logger.start();

    nlohmann::json j;
    j["event"] = "detection_frame";
    j["seq"] = 42;
    logger.log_async(j);

    collector.wait_for(1);
    logger.stop();

    auto msgs = collector.messages();
    ASSERT_EQ(msgs.size(), 1u);

    // Worker should have called j.dump() — verify it's valid JSON with our fields
    auto parsed = nlohmann::json::parse(msgs[0]);
    EXPECT_EQ(parsed["event"], "detection_frame");
    EXPECT_EQ(parsed["seq"], 42);
    EXPECT_EQ(logger.get_logged_count(), 1u);
}

// ===========================================================================
// Test: log_async with deferred builder function
// ===========================================================================
TEST(AsyncJsonLoggerTest, LogsDeferredBuilderFunction) {
    LogCollector collector;
    AsyncJsonLogger logger(collector.callback(), 5);
    logger.start();

    // Track which thread the builder runs on
    std::thread::id builder_thread_id;
    std::thread::id caller_thread_id = std::this_thread::get_id();

    logger.log_async([&]() -> nlohmann::json {
        builder_thread_id = std::this_thread::get_id();
        nlohmann::json j;
        j["event"] = "deferred";
        j["expensive_data"] = "computed_in_worker";
        return j;
    });

    collector.wait_for(1);
    logger.stop();

    auto msgs = collector.messages();
    ASSERT_EQ(msgs.size(), 1u);

    auto parsed = nlohmann::json::parse(msgs[0]);
    EXPECT_EQ(parsed["event"], "deferred");
    EXPECT_EQ(parsed["expensive_data"], "computed_in_worker");

    // Builder must have run on the worker thread, NOT the caller thread
    EXPECT_NE(builder_thread_id, caller_thread_id);
}

// ===========================================================================
// Test: queue returns immediately (non-blocking)
// ===========================================================================
TEST(AsyncJsonLoggerTest, LogAsyncReturnsImmediately) {
    LogCollector collector;
    AsyncJsonLogger logger(collector.callback(), 5);
    logger.start();

    // Queue a builder that takes 100ms to simulate expensive work (getStats)
    auto start = std::chrono::steady_clock::now();
    logger.log_async([]() -> nlohmann::json {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        nlohmann::json j;
        j["event"] = "slow";
        return j;
    });
    auto elapsed = std::chrono::steady_clock::now() - start;

    // log_async must return in < 5ms (just a queue push)
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count();
    EXPECT_LT(elapsed_ms, 5) << "log_async blocked for " << elapsed_ms << "ms — should be non-blocking";

    collector.wait_for(1);
    logger.stop();
    EXPECT_EQ(logger.get_logged_count(), 1u);
}

// ===========================================================================
// Test: drop-oldest policy when queue is full
// ===========================================================================
TEST(AsyncJsonLoggerTest, DropsOldestWhenQueueFull) {
    LogCollector collector;
    // Queue depth 2
    AsyncJsonLogger logger(collector.callback(), 2);
    // Do NOT start yet — queue fills without being drained

    nlohmann::json j1, j2, j3;
    j1["seq"] = 1;
    j2["seq"] = 2;
    j3["seq"] = 3;

    // Start, then immediately block the worker with a slow task
    logger.start();

    // Queue a slow builder to occupy the worker
    logger.log_async([]() -> nlohmann::json {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        nlohmann::json j;
        j["seq"] = 0;
        return j;
    });

    // Give the worker a moment to pick up the slow task
    std::this_thread::sleep_for(std::chrono::milliseconds(20));

    // Now queue 3 more — only 2 fit, so seq=1 should be dropped
    logger.log_async(j1);
    logger.log_async(j2);
    logger.log_async(j3);  // This should drop j1 (oldest)

    EXPECT_GE(logger.get_dropped_count(), 1u);

    collector.wait_for(3, std::chrono::milliseconds(3000));
    logger.stop();
}

// ===========================================================================
// Test: log_async returns false when not started
// ===========================================================================
TEST(AsyncJsonLoggerTest, ReturnsFalseWhenNotStarted) {
    LogCollector collector;
    AsyncJsonLogger logger(collector.callback(), 5);
    // Don't call start()

    nlohmann::json j;
    j["event"] = "test";
    bool result = logger.log_async(j);

    EXPECT_FALSE(result);
    EXPECT_EQ(logger.get_logged_count(), 0u);
}

// ===========================================================================
// Test: stop() drains remaining queued items
// ===========================================================================
TEST(AsyncJsonLoggerTest, StopDrainsQueue) {
    LogCollector collector;
    AsyncJsonLogger logger(collector.callback(), 10);
    logger.start();

    // Queue multiple items rapidly
    for (int i = 0; i < 5; ++i) {
        nlohmann::json j;
        j["seq"] = i;
        logger.log_async(j);
    }

    // Stop should wait for worker to process remaining items
    logger.stop();

    EXPECT_EQ(logger.get_logged_count(), 5u);
    EXPECT_EQ(collector.count(), 5u);
}

// ===========================================================================
// Test: multiple rapid calls are all processed
// ===========================================================================
TEST(AsyncJsonLoggerTest, ProcessesMultipleRapidCalls) {
    LogCollector collector;
    AsyncJsonLogger logger(collector.callback(), 20);
    logger.start();

    for (int i = 0; i < 10; ++i) {
        nlohmann::json j;
        j["seq"] = i;
        logger.log_async(j);
    }

    collector.wait_for(10);
    logger.stop();

    EXPECT_EQ(logger.get_logged_count(), 10u);
    auto msgs = collector.messages();
    EXPECT_EQ(msgs.size(), 10u);

    // Verify ordering preserved
    for (size_t i = 0; i < msgs.size(); ++i) {
        auto parsed = nlohmann::json::parse(msgs[i]);
        EXPECT_EQ(parsed["seq"], static_cast<int>(i));
    }
}

// ===========================================================================
// Test: builder exception doesn't crash the worker
// ===========================================================================
TEST(AsyncJsonLoggerTest, BuilderExceptionDoesNotCrashWorker) {
    LogCollector collector;
    AsyncJsonLogger logger(collector.callback(), 5);
    logger.start();

    // Queue a builder that throws
    logger.log_async([]() -> nlohmann::json {
        throw std::runtime_error("simulated getStats failure");
    });

    // Queue a normal item after — it should still be processed
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    nlohmann::json j;
    j["event"] = "after_exception";
    logger.log_async(j);

    collector.wait_for(1);
    logger.stop();

    // The normal item should have been processed despite the earlier exception
    auto msgs = collector.messages();
    ASSERT_GE(msgs.size(), 1u);
    auto parsed = nlohmann::json::parse(msgs.back());
    EXPECT_EQ(parsed["event"], "after_exception");
}

// ===========================================================================
// Test: destructor calls stop (no leak)
// ===========================================================================
TEST(AsyncJsonLoggerTest, DestructorCallsStop) {
    LogCollector collector;
    {
        AsyncJsonLogger logger(collector.callback(), 5);
        logger.start();
        nlohmann::json j;
        j["event"] = "before_destruct";
        logger.log_async(j);
        // Destructor should call stop() and drain
    }

    // Item should have been logged before destruction completed
    EXPECT_GE(collector.count(), 1u);
}
