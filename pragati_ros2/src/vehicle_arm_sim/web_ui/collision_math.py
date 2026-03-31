"""collision_math.py — centralized collision distance helpers.

Arms face opposite directions on the vehicle. J4 (prismatic lateral slide)
has opposite sign conventions for each arm. To get the true lateral distance
for collision avoidance, we compute abs(j4_a + j4_b) instead of
abs(j4_a - j4_b).
"""


def j4_collision_gap(j4_a: float, j4_b: float) -> float:
    """Compute lateral gap between two opposite-facing arms for collision avoidance.

    Because the arms face opposite directions, arm2's J4 is effectively
    negated in world-frame. The true lateral distance is:
        abs(j4_arm1 - (-j4_arm2)) = abs(j4_arm1 + j4_arm2)

    Args:
        j4_a: J4 position of the first arm (meters).
        j4_b: J4 position of the second arm (meters).

    Returns:
        Absolute lateral gap in meters.
    """
    return abs(j4_a + j4_b)
