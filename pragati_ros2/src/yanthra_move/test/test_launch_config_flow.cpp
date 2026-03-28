/**
 * @file test_launch_config_flow.cpp
 * @brief Source-verification test: launch file does not override YAML config.
 *
 * Regression test for the Mar 17 2026 field failure where the
 * pragati_complete.launch.py launch argument "j4_multiposition" (default=true)
 * always overrode the joint4_multiposition/enabled value from production.yaml.
 * Changing the YAML and restarting had no effect.
 *
 * Fix: removed the j4_multiposition LaunchConfiguration and DeclareLaunchArgument
 * entirely.  production.yaml is now the single source of truth.
 *
 * This test reads the launch file source and verifies:
 * 1. No LaunchConfiguration("j4_multiposition") exists
 * 2. No DeclareLaunchArgument for j4_multiposition exists
 * 3. No inline parameter override for joint4_multiposition/enabled exists
 */

#include <gtest/gtest.h>
#include <fstream>
#include <string>

namespace yanthra_move
{

class LaunchConfigFlowTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    const std::string launch_path =
      std::string(SOURCE_DIR) + "/launch/pragati_complete.launch.py";

    std::ifstream file(launch_path);
    ASSERT_TRUE(file.is_open()) << "Cannot open " << launch_path;

    content_ = std::string(
      (std::istreambuf_iterator<char>(file)),
       std::istreambuf_iterator<char>());

    ASSERT_FALSE(content_.empty()) << "Launch file is empty";
  }

  std::string content_;
};

// ---------------------------------------------------------------------------
// Test: no LaunchConfiguration("j4_multiposition")
// ---------------------------------------------------------------------------
TEST_F(LaunchConfigFlowTest, NoJ4MultipositionLaunchConfiguration)
{
  EXPECT_EQ(content_.find("LaunchConfiguration(\"j4_multiposition\")"),
            std::string::npos)
    << "pragati_complete.launch.py must NOT have "
       "LaunchConfiguration(\"j4_multiposition\") — "
       "this causes launch arg to override production.yaml";
}

// ---------------------------------------------------------------------------
// Test: no DeclareLaunchArgument for j4_multiposition
// ---------------------------------------------------------------------------
TEST_F(LaunchConfigFlowTest, NoJ4MultipositionDeclareArg)
{
  // Check for both quoting styles
  EXPECT_EQ(content_.find("name=\"j4_multiposition\""), std::string::npos)
    << "pragati_complete.launch.py must NOT declare a launch argument "
       "for j4_multiposition — production.yaml is the single source of truth";

  EXPECT_EQ(content_.find("name='j4_multiposition'"), std::string::npos)
    << "pragati_complete.launch.py must NOT declare a launch argument "
       "for j4_multiposition (single-quote variant)";
}

// ---------------------------------------------------------------------------
// Test: no inline parameter override for joint4_multiposition/enabled
//
// The fix replaced the override with a comment.  This test ensures
// the parameter key is not assigned to a LaunchConfiguration variable.
// We allow the key to appear in comments (lines starting with #).
// ---------------------------------------------------------------------------
TEST_F(LaunchConfigFlowTest, NoInlineMultipositionOverride)
{
  // Search for the pattern: "joint4_multiposition/enabled": <variable>
  // This catches re-introduction of the override regardless of variable name.
  // We need to exclude comment lines.
  std::istringstream stream(content_);
  std::string line;
  int line_num = 0;
  while (std::getline(stream, line)) {
    line_num++;
    // Skip comment lines (stripped leading whitespace)
    auto first_char = line.find_first_not_of(" \t");
    if (first_char != std::string::npos && line[first_char] == '#') {
      continue;
    }
    // Check for the override pattern in non-comment lines
    EXPECT_EQ(line.find("\"joint4_multiposition/enabled\":"), std::string::npos)
      << "Line " << line_num << ": pragati_complete.launch.py must NOT have "
         "an inline parameter override for joint4_multiposition/enabled — "
         "use production.yaml instead. Found: " << line;
  }
}

}  // namespace yanthra_move

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
