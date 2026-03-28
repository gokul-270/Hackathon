from setuptools import find_packages, setup

package_name = 'pid_tuning'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Udayakumar',
    maintainer_email='udayakumar@example.com',
    description='Motor config and PID tuning relay node for Pragati cotton-picking robot web dashboard',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'motor_config_service = pid_tuning.pid_tuning_node:main',
            'pid_tuning_node = pid_tuning.pid_tuning_node:main',
            'pid_tuning_service = pid_tuning.pid_tuning_node:main',
        ],
    },
)
