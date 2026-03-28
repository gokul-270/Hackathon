// Copyright 2026 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.

#include <gtest/gtest.h>

#include <fstream>
#include <string>
#include <vector>

class RemoteMotionLoggingTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    std::string source_dir;
#ifdef SOURCE_DIR
    source_dir = SOURCE_DIR;
#else
    source_dir = "..";
#endif
    const std::string filepath = source_dir + "/src/mg6010_controller_node.cpp";
    std::ifstream file(filepath);
    ASSERT_TRUE(file.is_open()) << "Cannot open source file: " << filepath;

    std::string line;
    while (std::getline(file, line)) {
      source_lines_.push_back(line);
    }
    ASSERT_GT(source_lines_.size(), 2500u) << "Source file suspiciously small";
  }

  bool contains(const std::string & pattern) const
  {
    for (const auto & line : source_lines_) {
      if (line.find(pattern) != std::string::npos) {
        return true;
      }
    }
    return false;
  }

  std::vector<std::string> source_lines_;
};

TEST_F(RemoteMotionLoggingTest, ActionLogsLifecycleStates)
{
  EXPECT_TRUE(contains("joint_position_command action: START"));
  EXPECT_TRUE(contains("joint_position_command action: PROGRESS"));
  EXPECT_TRUE(contains("joint_position_command action: REACHED"));
  EXPECT_TRUE(contains("joint_position_command action: TIMEOUT"));
  EXPECT_TRUE(contains("joint_position_command action: CANCEL COMPLETE"));
}

TEST_F(RemoteMotionLoggingTest, ActionLogsProgressFields)
{
  EXPECT_TRUE(contains("err=%.4f"));
  EXPECT_TRUE(contains("vel=%.4f"));
  EXPECT_TRUE(contains("current=%.3f"));
  EXPECT_TRUE(contains("temp=%.1f"));
  EXPECT_TRUE(contains("connected=%s"));
  EXPECT_TRUE(contains("elapsed=%.3fs"));
}

TEST_F(RemoteMotionLoggingTest, CancelRequestIncludesGoalIdentity)
{
  EXPECT_TRUE(contains("cancel requested joint_id=%ld target=%.4f"));
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
