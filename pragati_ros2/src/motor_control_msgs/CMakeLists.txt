cmake_minimum_required(VERSION 3.8)
project(motor_control_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(action_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/ClearMotorErrors.srv"
  "srv/DriveStop.srv"
  "srv/EmergencyStop.srv"
  "srv/JointHoming.srv"
  "srv/JointPositionCommand.srv"
  "srv/JointStatus.srv"
  "srv/MotorCommand.srv"
  "srv/MotorLifecycle.srv"
  "srv/ReadEncoder.srv"
  "srv/ReadMotorAngles.srv"
  "srv/ReadMotorLimits.srv"
  "srv/ReadMotorState.srv"
  "srv/ReadPID.srv"
  "srv/SetAxisState.srv"
  "srv/WriteEncoderZero.srv"
  "srv/WriteMotorLimits.srv"
  "srv/WritePID.srv"
  "srv/WritePIDToROM.srv"
  "action/StepResponseTest.action"
  "action/JointPositionCommand.action"
  "action/JointHoming.action"
  DEPENDENCIES std_msgs action_msgs
)

ament_package()
