#include <gtest/gtest.h>
#include <common_utils/consecutive_failure_tracker.hpp>

using pragati::ConsecutiveFailureTracker;

TEST(ConsecutiveFailureTrackerTest, DefaultThreshold)
{
  ConsecutiveFailureTracker tracker;
  EXPECT_EQ(tracker.threshold(), 5u);
}

TEST(ConsecutiveFailureTrackerTest, CustomThreshold)
{
  ConsecutiveFailureTracker tracker(3);
  EXPECT_EQ(tracker.threshold(), 3u);
}

TEST(ConsecutiveFailureTrackerTest, IncrementReturnsFalseBeforeThreshold)
{
  ConsecutiveFailureTracker tracker(5);
  for (int i = 0; i < 4; ++i) {
    EXPECT_FALSE(tracker.increment()) << "increment #" << (i + 1) << " should return false";
  }
}

TEST(ConsecutiveFailureTrackerTest, IncrementReturnsTrueAtThreshold)
{
  ConsecutiveFailureTracker tracker(5);
  for (int i = 0; i < 4; ++i) {
    tracker.increment();
  }
  EXPECT_TRUE(tracker.increment()) << "5th increment should return true";
}

TEST(ConsecutiveFailureTrackerTest, IncrementReturnsTrueAboveThreshold)
{
  ConsecutiveFailureTracker tracker(5);
  for (int i = 0; i < 5; ++i) {
    tracker.increment();
  }
  EXPECT_TRUE(tracker.increment()) << "6th increment should return true";
  EXPECT_TRUE(tracker.increment()) << "7th increment should return true";
}

TEST(ConsecutiveFailureTrackerTest, ResetClearsCount)
{
  ConsecutiveFailureTracker tracker(5);
  tracker.increment();
  tracker.increment();
  tracker.increment();
  tracker.reset();
  EXPECT_EQ(tracker.count(), 0u);
  EXPECT_FALSE(tracker.exceeded());
}

TEST(ConsecutiveFailureTrackerTest, ResetAllowsNewCounting)
{
  ConsecutiveFailureTracker tracker(5);
  // Increment to threshold
  for (int i = 0; i < 5; ++i) {
    tracker.increment();
  }
  EXPECT_TRUE(tracker.exceeded());

  tracker.reset();
  EXPECT_FALSE(tracker.exceeded());

  // Increment to threshold again
  for (int i = 0; i < 4; ++i) {
    EXPECT_FALSE(tracker.increment());
  }
  EXPECT_TRUE(tracker.increment()) << "5th increment after reset should return true";
  EXPECT_TRUE(tracker.exceeded());
}

TEST(ConsecutiveFailureTrackerTest, ExceededWithCustomThreshold)
{
  ConsecutiveFailureTracker tracker(5);
  tracker.increment();
  tracker.increment();
  tracker.increment();
  EXPECT_TRUE(tracker.exceeded(3));
  EXPECT_FALSE(tracker.exceeded(5));
}

TEST(ConsecutiveFailureTrackerTest, CountReturnsCurrentValue)
{
  ConsecutiveFailureTracker tracker(5);
  EXPECT_EQ(tracker.count(), 0u);
  tracker.increment();
  EXPECT_EQ(tracker.count(), 1u);
  tracker.increment();
  EXPECT_EQ(tracker.count(), 2u);
  tracker.increment();
  EXPECT_EQ(tracker.count(), 3u);
}

TEST(ConsecutiveFailureTrackerTest, SingleFailureDoesNotTrigger)
{
  ConsecutiveFailureTracker tracker(5);
  EXPECT_FALSE(tracker.increment());
  EXPECT_FALSE(tracker.exceeded());
}
