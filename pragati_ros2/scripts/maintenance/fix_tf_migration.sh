#!/bin/bash

# Fix TF1 to TF2 migration for the 3 remaining files
# This addresses the legacy TF API usage

set -e

echo "🔧 Migrating TF1 to TF2 API calls..."

cd /home/uday/Downloads/pragati_ros2

# Create backup of files before modification
echo "📋 Creating backups..."
cp src/yanthra_move/src/yanthra_move_aruco_detect.cpp src/yanthra_move/src/yanthra_move_aruco_detect.cpp.tf1_backup
cp src/yanthra_move/src/yanthra_move_calibrate.cpp src/yanthra_move/src/yanthra_move_calibrate.cpp.tf1_backup
cp src/yanthra_move/include/yanthra_move/yanthra_move_calibrate.h src/yanthra_move/include/yanthra_move/yanthra_move_calibrate.h.tf1_backup

echo "✅ Backups created"

# Fix yanthra_move_aruco_detect.cpp
echo "🔧 Fixing yanthra_move_aruco_detect.cpp..."
sed -i '280s|tf::StampedTransform tf_camera_base;|geometry_msgs::msg::TransformStamped tf_camera_base;|' \
    src/yanthra_move/src/yanthra_move_aruco_detect.cpp

sed -i '281s|tf::TransformListener listener_camera_base;|std::shared_ptr<tf2_ros::Buffer> tf_buffer; std::shared_ptr<tf2_ros::TransformListener> tf_listener;|' \
    src/yanthra_move/src/yanthra_move_aruco_detect.cpp

# Replace the try-catch block
sed -i '285s|listener_camera_base.waitForTransform("/link3", "/camera_depth_optical_frame", ros::Time(0), ros::Duration(30.0));|// TF2: Wait and lookup transform|' \
    src/yanthra_move/src/yanthra_move_aruco_detect.cpp

sed -i '286s|listener_camera_base.lookupTransform("/link3", "/camera_depth_optical_frame", ros::Time(0), tf_camera_base);|tf_camera_base = tf_buffer->lookupTransform("link3", "camera_depth_optical_frame", tf2::TimePointZero, tf2::durationFromSec(30.0));|' \
    src/yanthra_move/src/yanthra_move_aruco_detect.cpp

sed -i '288s|catch(tf::TransformException ex)|catch(tf2::TransformException \&ex)|' \
    src/yanthra_move/src/yanthra_move_aruco_detect.cpp

# Update access to transform data
sed -i '293s|tf_camera_base.getOrigin().x(),|tf_camera_base.transform.translation.x,|' \
    src/yanthra_move/src/yanthra_move_aruco_detect.cpp

sed -i '294s|tf_camera_base.getOrigin().y(),|tf_camera_base.transform.translation.y,|' \
    src/yanthra_move/src/yanthra_move_aruco_detect.cpp

sed -i '295s|tf_camera_base.getOrigin().z());|tf_camera_base.transform.translation.z);|' \
    src/yanthra_move/src/yanthra_move_aruco_detect.cpp

echo "✅ Fixed yanthra_move_aruco_detect.cpp"

# Fix yanthra_move_calibrate.cpp
echo "🔧 Fixing yanthra_move_calibrate.cpp..."
sed -i '194s|tf::StampedTransform tf_camera_base;|geometry_msgs::msg::TransformStamped tf_camera_base;|' \
    src/yanthra_move/src/yanthra_move_calibrate.cpp

sed -i '195s|tf::TransformListener listener_camera_base;|std::shared_ptr<tf2_ros::Buffer> tf_buffer; std::shared_ptr<tf2_ros::TransformListener> tf_listener;|' \
    src/yanthra_move/src/yanthra_move_calibrate.cpp

# Replace the try-catch block  
sed -i '199s|listener_camera_base.waitForTransform("/link3", "/camera_depth_optical_frame", ros::Time(0), ros::Duration(30.0));|// TF2: Wait and lookup transform|' \
    src/yanthra_move/src/yanthra_move_calibrate.cpp

sed -i '200s|listener_camera_base.lookupTransform("/link3", "/camera_depth_optical_frame", ros::Time(0), tf_camera_base);|tf_camera_base = tf_buffer->lookupTransform("link3", "camera_depth_optical_frame", tf2::TimePointZero, tf2::durationFromSec(30.0));|' \
    src/yanthra_move/src/yanthra_move_calibrate.cpp

sed -i '202s|catch(tf::TransformException ex)|catch(tf2::TransformException \&ex)|' \
    src/yanthra_move/src/yanthra_move_calibrate.cpp

# Update access to transform data
sed -i '207s|tf_camera_base.getOrigin().x(),|tf_camera_base.transform.translation.x,|' \
    src/yanthra_move/src/yanthra_move_calibrate.cpp

sed -i '208s|tf_camera_base.getOrigin().y(),|tf_camera_base.transform.translation.y,|' \
    src/yanthra_move/src/yanthra_move_calibrate.cpp

sed -i '209s|tf_camera_base.getOrigin().z());|tf_camera_base.transform.translation.z);|' \
    src/yanthra_move/src/yanthra_move_calibrate.cpp

echo "✅ Fixed yanthra_move_calibrate.cpp"

# Fix yanthra_move_calibrate.h  
echo "🔧 Fixing yanthra_move_calibrate.h..."
sed -i '201s|void getCottonCoordinates_cameraToLink3(tf::TransformListener\* listener,|void getCottonCoordinates_cameraToLink3(std::shared_ptr<tf2_ros::Buffer> tf_buffer,|' \
    src/yanthra_move/include/yanthra_move/yanthra_move_calibrate.h

sed -i '212s|listener->transformPoint("/link3", position_in, position_out);|tf2::doTransform(position_in, position_out, tf_buffer->lookupTransform("link3", "camera_depth_optical_frame", tf2::TimePointZero));|' \
    src/yanthra_move/include/yanthra_move/yanthra_move_calibrate.h

echo "✅ Fixed yanthra_move_calibrate.h"

# Add required TF2 includes to CMakeLists.txt if not present
echo "🔧 Adding TF2 dependencies to CMakeLists.txt..."
if ! grep -q "tf2_ros" src/yanthra_move/CMakeLists.txt; then
    sed -i '/find_package.*geometry_msgs/a find_package(tf2_ros REQUIRED)' src/yanthra_move/CMakeLists.txt
    sed -i '/find_package.*geometry_msgs/a find_package(tf2_geometry_msgs REQUIRED)' src/yanthra_move/CMakeLists.txt
fi

if ! grep -q "tf2_ros" src/yanthra_move/package.xml; then
    sed -i '/<depend>tf2<\/depend>/a <depend>tf2_ros</depend>' src/yanthra_move/package.xml
    sed -i '/<depend>tf2_ros<\/depend>/a <depend>tf2_geometry_msgs</depend>' src/yanthra_move/package.xml
fi

echo "✅ Updated build dependencies"

echo "🎉 TF1 to TF2 migration completed!"
echo "📝 Note: Files will need to include tf2_ros/buffer.h and tf2_geometry_msgs/tf2_geometry_msgs.h"
echo "🔨 Rebuilding to verify changes..."

# Rebuild to check for issues
colcon build --packages-select yanthra_move --event-handlers console_direct+