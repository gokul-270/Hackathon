// Copyright 2026 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.

#include <gtest/gtest.h>

#include <fstream>
#include <string>
#include <vector>

class JointMoveLoggingContractTest : public ::testing::Test
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
    const std::string filepath = source_dir + "/src/joint_move.cpp";
    std::ifstream file(filepath);
    ASSERT_TRUE(file.is_open()) << "Cannot open source file: " << filepath;

    std::string line;
    while (std::getline(file, line)) {
      source_lines_.push_back(line);
    }
    ASSERT_GT(source_lines_.size(), 150u) << "Source file suspiciously small";
  }

  int findLine(const std::string & pattern, int start = 0) const
  {
    for (int i = start; i < static_cast<int>(source_lines_.size()); ++i) {
      if (source_lines_[i].find(pattern) != std::string::npos) {
        return i;
      }
    }
    return -1;
  }

  int findFunctionEnd(int body_start) const
  {
    int depth = 0;
    for (int i = body_start; i < static_cast<int>(source_lines_.size()); ++i) {
      for (char c : source_lines_[i]) {
        if (c == '{') depth++;
        if (c == '}') {
          depth--;
          if (depth == 0) {
            return i;
          }
        }
      }
    }
    return -1;
  }

  bool blockContains(int start, int end, const std::string & pattern) const
  {
    for (int i = start; i <= end && i < static_cast<int>(source_lines_.size()); ++i) {
      if (source_lines_[i].find(pattern) != std::string::npos) {
        return true;
      }
    }
    return false;
  }

  std::vector<std::string> source_lines_;
};

TEST_F(JointMoveLoggingContractTest, ActionModeRegistersFeedbackCallback)
{
  const int move_line = findLine("MoveResult joint_move::move_joint");
  ASSERT_GE(move_line, 0);

  const int func_end = findFunctionEnd(move_line);
  ASSERT_GT(func_end, move_line);

  EXPECT_TRUE(blockContains(move_line, func_end, "send_goal_options.feedback_callback"))
    << "move_joint() must register an action feedback callback so timeout logs can include progress.";
}

TEST_F(JointMoveLoggingContractTest, TimeoutLogIncludesRemoteDebugFields)
{
  const int move_line = findLine("MoveResult joint_move::move_joint");
  ASSERT_GE(move_line, 0);

  const int func_end = findFunctionEnd(move_line);
  ASSERT_GT(func_end, move_line);

  EXPECT_TRUE(blockContains(move_line, func_end, "last_feedback_received=%s"));
  EXPECT_TRUE(blockContains(move_line, func_end, "feedback_samples=%zu"));
  EXPECT_TRUE(blockContains(move_line, func_end, "last_feedback_pos=%.4f"));
  EXPECT_TRUE(blockContains(move_line, func_end, "last_feedback_err=%.4f"));
  EXPECT_TRUE(blockContains(move_line, func_end, "last_feedback_age_ms=%.0f"));
  EXPECT_TRUE(blockContains(move_line, func_end, "cached_position=%.4f"));
  EXPECT_TRUE(blockContains(move_line, func_end, "cancel_requested=true"));
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
