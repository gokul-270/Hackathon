"""Ziegler-Nichols open-loop process reaction curve analyzer for PID auto-tuning.

Implements the Z-N open-loop PRC method for extracting FOPDT (First-Order Plus
Dead Time) model parameters from step response data, then computing tuning
rules for P, PI, and PID controllers.

Motor firmware (MG6010/MG6012) exposes only Kp/Ki per loop — Kd terms are
computed for reference but flagged as not-applicable.  Final suggested gains
are clamped and rounded to uint8 (0-255).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ZNAnalysisResult:
    """Result of Ziegler-Nichols open-loop PRC analysis.

    Attributes:
        success: True if extraction succeeded.
        error_message: Reason for failure (empty on success).
        K: Static gain  = (steady_state - initial) / step_size.
        L: Dead-time (delay) in seconds.
        T: Time constant in seconds.
        inflection_index: Index of the inflection point in the data.
        tangent_slope: Slope of the tangent line at inflection.
        tangent_intercept: Y-intercept of the tangent line.
        confidence: 'high' / 'medium' / 'low' based on tangent R².
        r_squared: R² of tangent fit against the data in the rise region.
    """

    success: bool = False
    error_message: str = ""
    K: float = 0.0
    L: float = 0.0
    T: float = 0.0
    inflection_index: int = 0
    tangent_slope: float = 0.0
    tangent_intercept: float = 0.0
    confidence: str = "low"
    r_squared: float = 0.0


@dataclass
class TuningRule:
    """Gains produced by a single Z-N tuning rule.

    Attributes:
        rule_name: Human-readable rule identifier.
        kp: Proportional gain (continuous domain).
        ki: Integral gain (continuous domain).
        kd: Derivative gain (continuous domain).
        applicable: True if the motor firmware can use all non-zero gains.
    """

    rule_name: str = ""
    kp: float = 0.0
    ki: float = 0.0
    kd: float = 0.0
    applicable: bool = True


@dataclass
class GainSuggestion:
    """Mapped uint8 gains ready for motor firmware.

    Attributes:
        rule_name: Name of the tuning rule used.
        position_kp: Position loop Kp (0-255).
        position_ki: Position loop Ki (0-255).
        speed_kp: Speed loop Kp (0-255).
        speed_ki: Speed loop Ki (0-255).
        torque_kp: Torque loop Kp (0-255).
        torque_ki: Torque loop Ki (0-255).
        confidence: 'high' / 'medium' / 'low'.
        applicable_note: Note about firmware limitations.
    """

    rule_name: str = ""
    position_kp: int = 0
    position_ki: int = 0
    speed_kp: int = 0
    speed_ki: int = 0
    torque_kp: int = 0
    torque_ki: int = 0
    confidence: str = "low"
    applicable_note: str = ""


# ---------------------------------------------------------------------------
# Motor-type scaling defaults
# ---------------------------------------------------------------------------

# Maps motor_type → dict of loop → (kp_scale, ki_scale).
# These heuristic scaling factors translate continuous-domain Z-N gains into
# the uint8 register space of the MG601x firmware.  Tuned empirically.
_MOTOR_SCALING: Dict[str, Dict[str, tuple]] = {
    "mg6010": {
        "position": (30.0, 10.0),
        "speed": (15.0, 5.0),
        "torque": (10.0, 3.0),
    },
    "mg6012": {
        "position": (25.0, 8.0),
        "speed": (12.0, 4.0),
        "torque": (8.0, 2.5),
    },
}


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_step_response(
    timestamps: np.ndarray,
    positions: np.ndarray,
    setpoint: float,
    step_size: float,
) -> ZNAnalysisResult:
    """Extract FOPDT model parameters from a step response via PRC method.

    Args:
        timestamps: 1-D array of time values in seconds (monotonic).
        positions: 1-D array of measured position values (same length).
        setpoint: Commanded target position (after the step).
        step_size: Magnitude of the step input (positive).

    Returns:
        ZNAnalysisResult with extracted K, L, T and fit quality metrics.
    """
    result = ZNAnalysisResult()

    ts = np.asarray(timestamps, dtype=np.float64)
    pos = np.asarray(positions, dtype=np.float64)

    # --- basic validation ---
    if ts.size < 5 or pos.size < 5:
        result.error_message = (
            "Insufficient data: need at least 5 samples."
        )
        return result

    if ts.size != pos.size:
        result.error_message = "timestamps and positions length mismatch."
        return result

    if step_size == 0.0:
        result.error_message = "step_size must be non-zero."
        return result

    n = ts.size

    # --- steady-state value (average of last 20 %) ---
    tail_start = max(1, int(0.8 * n))
    steady_state = float(np.mean(pos[tail_start:]))
    initial_value = float(pos[0])

    # --- static gain K ---
    K = (steady_state - initial_value) / step_size
    if K <= 0:
        result.error_message = (
            f"Non-positive static gain K={K:.4f}. "
            "Response may be inverted or incomplete."
        )
        return result

    # --- inflection point via maximum slope (steepest point) ---
    # The PRC method draws a tangent at the steepest point of the response.
    # Smooth the position data before computing the derivative to reduce
    # noise sensitivity.  Window is ~2% of data, minimum 3, must be odd.
    smooth_win = max(3, (n // 50) | 1)
    if smooth_win >= n:
        smooth_win = n if n % 2 == 1 else max(1, n - 1)
    if smooth_win >= 3:
        kernel = np.ones(smooth_win) / smooth_win
        pos_smooth = np.convolve(pos, kernel, mode="same")
    else:
        pos_smooth = pos

    # First derivative of smoothed signal.
    dy = np.gradient(pos_smooth, ts)

    # Only look for the steepest point where response is actively changing.
    # Restrict search to 5 %–80 % of the data to avoid noisy endpoints.
    search_start = max(1, int(0.05 * n))
    search_end = max(search_start + 1, int(0.80 * n))

    dy_region = dy[search_start:search_end]
    if dy_region.size == 0:
        result.error_message = "Data too short to find inflection region."
        return result

    inflection_local = int(np.argmax(np.abs(dy_region)))
    inflection_idx = search_start + inflection_local

    # --- tangent at inflection ---
    slope = float(dy[inflection_idx])
    t_infl = float(ts[inflection_idx])
    y_infl = float(pos_smooth[inflection_idx])

    if abs(slope) < 1e-12:
        result.error_message = (
            "Slope at inflection is ~0; cannot fit tangent."
        )
        return result

    # Tangent line: y = slope * (t - t_infl) + y_infl
    # Tangent y-intercept (in y = m*t + b form): b = y_infl - slope * t_infl
    tangent_intercept = y_infl - slope * t_infl

    # --- L (dead time): time where tangent crosses initial_value ---
    # slope * t + tangent_intercept = initial_value
    # t = (initial_value - tangent_intercept) / slope
    t_cross_initial = (initial_value - tangent_intercept) / slope

    # --- T (time constant): tangent crosses steady_state, minus L ---
    # slope * t + tangent_intercept = steady_state
    t_cross_steady = (steady_state - tangent_intercept) / slope

    L = t_cross_initial - ts[0]
    T = t_cross_steady - t_cross_initial

    if L <= 0:
        result.error_message = (
            f"Negative dead-time L={L:.4f}s. "
            "The response may lack measurable delay."
        )
        return result
    if T <= 0:
        result.error_message = (
            f"Negative time constant T={T:.4f}s. "
            "Tangent fit did not cross steady-state correctly."
        )
        return result

    # --- R² of tangent fit in the rise region ---
    # Evaluate tangent line over the region [inflection - 20%, inflection + 20%]
    r2_start = max(0, int(inflection_idx - 0.2 * n))
    r2_end = min(n, int(inflection_idx + 0.2 * n))
    if r2_end <= r2_start:
        r2_start, r2_end = 0, n

    t_region = ts[r2_start:r2_end]
    y_region = pos[r2_start:r2_end]
    y_tangent = slope * t_region + tangent_intercept

    ss_res = float(np.sum((y_region - y_tangent) ** 2))
    ss_tot = float(np.sum((y_region - np.mean(y_region)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    r_squared = max(0.0, r_squared)

    if r_squared > 0.95:
        confidence = "high"
    elif r_squared > 0.80:
        confidence = "medium"
    else:
        confidence = "low"

    result.success = True
    result.K = K
    result.L = L
    result.T = T
    result.inflection_index = inflection_idx
    result.tangent_slope = slope
    result.tangent_intercept = tangent_intercept
    result.r_squared = r_squared
    result.confidence = confidence
    return result


# ---------------------------------------------------------------------------
# Tuning rules
# ---------------------------------------------------------------------------

def compute_tuning_rules(
    L: float,
    T: float,
    K: float,
) -> Dict[str, TuningRule]:
    """Compute standard Z-N open-loop PRC tuning rules.

    Args:
        L: Dead-time (delay) in seconds.  Must be > 0.
        T: Time constant in seconds.  Must be > 0.
        K: Static gain.  Must be > 0.

    Returns:
        Dict mapping rule name to TuningRule.

    Raises:
        ValueError: If any parameter is non-positive.
    """
    if L <= 0 or T <= 0 or K <= 0:
        raise ValueError(
            f"L, T, K must all be positive (got L={L}, T={T}, K={K})."
        )

    rules: Dict[str, TuningRule] = {}

    # P-only
    kp = T / (K * L)
    rules["p_only"] = TuningRule(
        rule_name="P-only",
        kp=kp,
        ki=0.0,
        kd=0.0,
        applicable=True,
    )

    # PI
    kp = 0.9 * T / (K * L)
    ki = kp / (3.33 * L)
    rules["pi"] = TuningRule(
        rule_name="PI",
        kp=kp,
        ki=ki,
        kd=0.0,
        applicable=True,
    )

    # Classic PID
    kp = 1.2 * T / (K * L)
    ki = kp / (2.0 * L)
    kd = kp * 0.5 * L
    rules["classic_pid"] = TuningRule(
        rule_name="Classic PID",
        kp=kp,
        ki=ki,
        kd=kd,
        applicable=False,  # Motor firmware has no Kd
    )

    # Pessen Integral Rule
    kp = 1.4 * T / (K * L)
    ki = kp / (1.75 * L)
    kd = kp * 0.42 * L
    rules["pessen"] = TuningRule(
        rule_name="Pessen Integral",
        kp=kp,
        ki=ki,
        kd=kd,
        applicable=False,
    )

    # Some-Overshoot (Tyreus-Luyben-like conservative)
    kp = T / (3.0 * K * L)
    ki = kp / (2.0 * L)
    rules["some_overshoot"] = TuningRule(
        rule_name="Some-Overshoot",
        kp=kp,
        ki=ki,
        kd=0.0,
        applicable=True,
    )

    # No-Overshoot
    kp = 0.2 * T / (K * L)
    ki = kp / (2.0 * L)
    rules["no_overshoot"] = TuningRule(
        rule_name="No-Overshoot",
        kp=kp,
        ki=ki,
        kd=0.0,
        applicable=True,
    )

    return rules


# ---------------------------------------------------------------------------
# Gain suggestion
# ---------------------------------------------------------------------------

def suggest_gains(
    analysis_result: ZNAnalysisResult,
    motor_type: str = "mg6010",
    rule: str = "classic_pid",
) -> GainSuggestion:
    """Map Z-N gains to uint8 motor registers for a given tuning rule.

    Args:
        analysis_result: Output of ``analyze_step_response``.
        motor_type: 'mg6010' or 'mg6012'.
        rule: Key into the tuning-rules dict (e.g. 'classic_pid', 'pi').

    Returns:
        GainSuggestion with clamped integer gains for each loop.
    """
    suggestion = GainSuggestion()

    if not analysis_result.success:
        suggestion.applicable_note = (
            f"Analysis failed: {analysis_result.error_message}"
        )
        return suggestion

    rules = compute_tuning_rules(
        analysis_result.L, analysis_result.T, analysis_result.K
    )

    if rule not in rules:
        suggestion.applicable_note = (
            f"Unknown rule '{rule}'. "
            f"Available: {', '.join(sorted(rules.keys()))}"
        )
        return suggestion

    tr = rules[rule]
    suggestion.rule_name = tr.rule_name
    suggestion.confidence = analysis_result.confidence

    scaling = _MOTOR_SCALING.get(motor_type, _MOTOR_SCALING["mg6010"])

    # Map continuous gains → uint8 via per-loop scaling factors.
    for loop_name in ("position", "speed", "torque"):
        kp_scale, ki_scale = scaling[loop_name]
        mapped_kp = _clamp_uint8(tr.kp * kp_scale)
        mapped_ki = _clamp_uint8(tr.ki * ki_scale)
        setattr(suggestion, f"{loop_name}_kp", mapped_kp)
        setattr(suggestion, f"{loop_name}_ki", mapped_ki)

    # Applicable note about firmware Kd limitation
    if tr.kd > 0:
        suggestion.applicable_note = (
            f"Kd={tr.kd:.4f} computed but NOT applicable — "
            "MG601x firmware only exposes Kp/Ki per loop."
        )
    else:
        suggestion.applicable_note = (
            "All suggested gains are applicable (no Kd term)."
        )

    return suggestion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_uint8(value: float) -> int:
    """Round and clamp a float to the uint8 range [0, 255]."""
    return int(max(0, min(255, round(value))))
