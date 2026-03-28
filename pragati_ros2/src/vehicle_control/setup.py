from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'vehicle_control'

# Find all subpackages (core, hardware, integration, utils, simulation)
subpackages = find_packages()

# Build package list: vehicle_control + vehicle_control.subpackage for each
packages = [package_name] + [f'{package_name}.{p}' for p in subpackages]

# Map package names to directories
package_dir = {package_name: '.'}
for p in subpackages:
    package_dir[f'{package_name}.{p}'] = p

setup(
    name=package_name,
    version='2.0.0',
    packages=packages,
    package_dir=package_dir,
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yml')),
        # Gazebo simulation files
        (os.path.join('share', package_name, 'launch'), glob('simulation/gazebo/launch/*.launch.py')),
        (os.path.join('share', package_name, 'urdf'), glob('simulation/gazebo/urdf/*.urdf')),
        (os.path.join('share', package_name, 'urdf'), glob('simulation/gazebo/urdf/*.xacro')),
        (os.path.join('share', package_name, 'worlds'), glob('simulation/gazebo/worlds/*.sdf')),
        (os.path.join('share', package_name, 'worlds'), glob('simulation/gazebo/worlds/*.world')),
        (os.path.join('share', package_name, 'simulation/config'), glob('simulation/gazebo/config/*')),
        (os.path.join('share', package_name, 'meshes'), glob('simulation/gazebo/meshes/*')),
        # NOTE: vehicle_mqtt_bridge.py is installed via CMakeLists.txt, not here.
        # This setup.py is NOT used for installation — the package uses ament_cmake.
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Cotton Picker Team',
    maintainer_email='support@example.com',
    description='Advanced Vehicle Control System for Cotton Picker Robot',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'ros2_vehicle_control_node = vehicle_control.integration.ros2_vehicle_control_node:main',
            # Gazebo simulation nodes
            'gazebo_kinematics_node = vehicle_control.simulation.gazebo.nodes.kinematics_node:main',
            'gazebo_joy_teleop = vehicle_control.simulation.gazebo.nodes.joy_teleop:main',
            'gazebo_keyboard_teleop = vehicle_control.simulation.gazebo.nodes.keyboard_teleop:main',
            'gazebo_ackermann_steering = vehicle_control.simulation.gazebo.nodes.ackermann_steering:main',
            'gazebo_rtk_gps_simulator = vehicle_control.simulation.gazebo.nodes.rtk_gps_simulator:main',
            'gazebo_front_camera_cotton_detector = vehicle_control.simulation.gazebo.nodes.front_camera_cotton_detector:main',
        ],
    },
)
