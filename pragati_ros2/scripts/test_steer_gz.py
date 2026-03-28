#!/usr/bin/env python3
"""
DEPRECATED: This script is superseded by scripts/demo_patterns.py which
provides a comprehensive motion pattern library with composable functions.
Use: python3 scripts/demo_patterns.py --stress

Direct Gazebo steering test - bypasses ROS2 entirely.
Uses gz topic CLI in a loop for continuous publishing.
"""
import subprocess, time, sys, os, re, math, threading

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

def gz_pub_loop(topic, value, duration=5.0):
    """Continuously publish to a gz topic for given duration."""
    end = time.time() + duration
    while time.time() < end:
        subprocess.run(
            ['gz', 'topic', '-t', topic, '-m', 'gz.msgs.Double', '-p', f'data: {value}'],
            capture_output=True, timeout=3
        )

def gz_pub_all_steering(left, right, front, duration=5.0):
    """Publish to all three steering topics in parallel."""
    threads = [
        threading.Thread(target=gz_pub_loop, args=('/steering/left', left, duration)),
        threading.Thread(target=gz_pub_loop, args=('/steering/right', right, duration)),
        threading.Thread(target=gz_pub_loop, args=('/steering/front', front, duration)),
        # Also zero drives
        threading.Thread(target=gz_pub_loop, args=('/wheel/left/velocity', 0.0, duration)),
        threading.Thread(target=gz_pub_loop, args=('/wheel/right/velocity', 0.0, duration)),
        threading.Thread(target=gz_pub_loop, args=('/wheel/front/velocity', 0.0, duration)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

def read_joint_states():
    """Read joint states from Gazebo."""
    try:
        result = subprocess.run(
            ['timeout', '3', 'gz', 'topic', '-e', '-n', '1', '-t', '/joint_states'],
            capture_output=True, text=True, timeout=5
        )
        text = result.stdout
        blocks = text.split('joint {')
        seen = {}
        for block in blocks:
            name_match = re.search(r'name: "([^"]+Revolute[^"]+)"', block)
            if name_match:
                name = name_match.group(1)
                if name in seen:
                    continue
                axis_match = re.search(r'axis1 \{.*?position: ([\d.e+-]+)', block, re.DOTALL)
                if axis_match:
                    seen[name] = float(axis_match.group(1))
        return seen
    except Exception as e:
        print(f'Error reading joint states: {e}')
        return {}

def print_steering(states):
    """Print steering joint states."""
    steering_map = {
        'base-plate-front_Revolute-14': 'FRONT',
        'base-plate-right_Revolute-18': 'RIGHT',
        'base-plate-left_Revolute-20': 'LEFT',
    }
    for name, label in steering_map.items():
        if name in states:
            pos = states[name]
            print(f'  {label}: {pos:.4f} rad ({math.degrees(pos):.1f}°)')
        else:
            print(f'  {label}: NOT FOUND')


def main():
    test = sys.argv[1] if len(sys.argv) > 1 else 'both_same'
    angle = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5

    print(f'\n=== STEP 1: Zeroing all steering (8s) ===')
    gz_pub_all_steering(0.0, 0.0, 0.0, duration=8.0)
    print('Reading zeroed state...')
    states = read_joint_states()
    print_steering(states)

    print(f'\n=== STEP 2: Test "{test}" with angle={angle:.3f} rad ({math.degrees(angle):.1f}°) (8s) ===')
    
    if test == 'left_only':
        print(f'Sending LEFT={angle}, others=0')
        gz_pub_all_steering(angle, 0.0, 0.0, duration=8.0)
    elif test == 'right_only':
        print(f'Sending RIGHT={angle}, others=0')
        gz_pub_all_steering(0.0, angle, 0.0, duration=8.0)
    elif test == 'both_same':
        print(f'Sending LEFT={angle}, RIGHT={angle} (same positive angle)')
        print('EXPECTATION: If axes are same direction → wheels turn same way')
        print('             If left axis is inverted → wheels turn OPPOSITE')
        gz_pub_all_steering(angle, angle, 0.0, duration=8.0)
    elif test == 'both_negated':
        print(f'Sending LEFT={-angle}, RIGHT={angle} (kinematics negation)')
        print('EXPECTATION: If left axis is inverted → wheels turn SAME way')
        gz_pub_all_steering(-angle, angle, 0.0, duration=8.0)
    else:
        print(f'Unknown test: {test}')
        os._exit(1)

    print('\nReading final state...')
    states = read_joint_states()
    print_steering(states)

    # Check if both rear wheels ended up at similar angles
    left_pos = states.get('base-plate-left_Revolute-20', None)
    right_pos = states.get('base-plate-right_Revolute-18', None)
    if left_pos is not None and right_pos is not None:
        print(f'\n  Left-Right difference: {math.degrees(left_pos - right_pos):.1f}°')
        if abs(left_pos - right_pos) < 5.0 * math.pi / 180:
            print('  → Wheels at SAME joint angle → same physical direction (if axes match)')
        elif abs(left_pos + right_pos) < 5.0 * math.pi / 180:
            print('  → Wheels at OPPOSITE joint angles → axes may be inverted')
        else:
            print('  → Inconclusive — PID may not have settled')

    print('\n=== STEP 3: Zeroing again (5s) ===')
    gz_pub_all_steering(0.0, 0.0, 0.0, duration=5.0)
    print('Done.')
    os._exit(0)


if __name__ == '__main__':
    main()
