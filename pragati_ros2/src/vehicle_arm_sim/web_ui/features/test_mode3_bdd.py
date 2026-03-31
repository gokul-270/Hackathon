"""BDD test: Mode 3 — Sequential Pick (Contention Arbitration).

Includes extra step definitions for contention-specific Given/When/Then steps.
"""
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from sequential_pick_policy import SequentialPickPolicy

FEATURE = "mode3_sequential_pick.feature"


# ===================================================================
# Scenario bindings
# ===================================================================

# -- Contention detected --

@scenario(FEATURE, "Contention detected when j4 gap is 0.05m and both arms extend")
def test_contention_005():
    pass


@scenario(FEATURE, "Contention detected when j4 gap is 0.01m")
def test_contention_001():
    pass


@scenario(FEATURE, "Contention detected when j4 gap is exactly 0.0m")
def test_contention_000():
    pass


@scenario(FEATURE, "Contention detected when j4 gap is 0.099m (just below threshold)")
def test_contention_099():
    pass


# -- No contention: gap --

@scenario(FEATURE, "No contention when j4 gap is 0.15m (above threshold)")
def test_no_contention_015():
    pass


@scenario(FEATURE, "No contention when j4 gap is exactly 0.10m (boundary — at threshold)")
def test_no_contention_boundary():
    pass


@scenario(FEATURE, "No contention when j4 gap is 0.50m (well separated)")
def test_no_contention_050():
    pass


# -- No contention: j5 --

@scenario(FEATURE, "No contention when own arm j5 is zero (not extending)")
def test_no_contention_own_j5_zero():
    pass


@scenario(FEATURE, "No contention when peer arm j5 is zero (not extending)")
def test_no_contention_peer_j5_zero():
    pass


@scenario(FEATURE, "No contention when both arms j5 is zero")
def test_no_contention_both_j5_zero():
    pass


# -- No peer --

@scenario(FEATURE, "No contention when no peer arm is active")
def test_no_contention_no_peer():
    pass


# -- Turn alternation --

@scenario(FEATURE, "arm1 wins the first contention step")
def test_arm1_wins_first():
    pass


@scenario(FEATURE, "arm2 is the loser at the first contention step")
def test_arm2_loses_first():
    pass


@scenario(FEATURE, "Winner alternates to arm2 on second contention step")
def test_arm2_wins_second():
    pass


@scenario(FEATURE, "Winner alternates back to arm1 on third contention step")
def test_arm1_wins_third():
    pass


# -- Joints unchanged --

@scenario(FEATURE, "Winner arm receives unmodified joints")
def test_winner_joints_unchanged():
    pass


@scenario(FEATURE, "Loser arm also receives unmodified joints")
def test_loser_joints_unchanged():
    pass


@scenario(FEATURE, "Skipped is always false even during contention")
def test_skipped_false_on_contention():
    pass


# ===================================================================
# Extra step definitions specific to Mode 3
# ===================================================================

@when(parsers.re(r'the policy evaluates contention for step (?P<step>\d+)'))
def when_evaluate_contention(ctx, step):
    policy = ctx.get("policy") or SequentialPickPolicy()
    ctx["policy"] = policy
    peer_joints = ctx["arm2_joints"]

    applied, skipped, is_contention, is_winner = policy.apply(
        int(step), "arm1", ctx["arm1_joints"], peer_joints,
    )
    ctx["result_joints"] = applied
    ctx["result_skipped"] = skipped
    ctx["result_contention"] = is_contention
    ctx["result_winner"] = is_winner


@when(parsers.re(r'the policy evaluates contention for step (?P<step>\d+) with no peer'))
def when_evaluate_no_peer(ctx, step):
    policy = ctx.get("policy") or SequentialPickPolicy()
    ctx["policy"] = policy

    applied, skipped, is_contention, is_winner = policy.apply(
        int(step), "arm1", ctx["arm1_joints"], None,
    )
    ctx["result_joints"] = applied
    ctx["result_skipped"] = skipped
    ctx["result_contention"] = is_contention
    ctx["result_winner"] = is_winner


@when(parsers.re(r'arm1 is evaluated for contention at step (?P<step>\d+)'))
def when_arm1_contention(ctx, step):
    policy = ctx["policy"]
    peer_joints = ctx["arm2_joints"]
    applied, skipped, is_contention, is_winner = policy.apply(
        int(step), "arm1", ctx["arm1_joints"], peer_joints,
    )
    ctx["arm_results"]["arm1"] = {
        "joints": applied,
        "skipped": skipped,
        "contention": is_contention,
        "winner": is_winner,
    }
    ctx["result_joints"] = applied
    ctx["result_skipped"] = skipped
    ctx["result_contention"] = is_contention
    ctx["result_winner"] = is_winner


@when(parsers.re(r'arm2 is evaluated for contention at step (?P<step>\d+)'))
def when_arm2_contention(ctx, step):
    policy = ctx["policy"]
    peer_joints = ctx["arm1_joints"]  # arm2's peer is arm1
    applied, skipped, is_contention, is_winner = policy.apply(
        int(step), "arm2", ctx["arm2_joints"], peer_joints,
    )
    ctx["arm_results"]["arm2"] = {
        "joints": applied,
        "skipped": skipped,
        "contention": is_contention,
        "winner": is_winner,
    }


@when(parsers.re(r'arm1 wins step 0 and arm2 loses step 0'))
def when_arm1_wins_step0(ctx):
    policy = ctx["policy"]
    peer_joints = ctx["arm2_joints"]
    # arm1 at step 0
    policy.apply(0, "arm1", ctx["arm1_joints"], peer_joints)
    # arm2 at step 0 (peer is arm1)
    policy.apply(0, "arm2", ctx["arm2_joints"], ctx["arm1_joints"])


@when("three contention steps are processed")
def when_three_steps(ctx):
    policy = ctx["policy"]
    winners = []
    for step_id in range(3):
        _, _, _, is_winner_a1 = policy.apply(
            step_id, "arm1", ctx["arm1_joints"], ctx["arm2_joints"],
        )
        _, _, _, is_winner_a2 = policy.apply(
            step_id, "arm2", ctx["arm2_joints"], ctx["arm1_joints"],
        )
        if is_winner_a1:
            winners.append("arm1")
        elif is_winner_a2:
            winners.append("arm2")
        else:
            winners.append("unknown")
    ctx["winners_sequence"] = winners


# ===================================================================
# THEN steps specific to Mode 3
# ===================================================================

@then("contention is detected")
def then_contention(ctx):
    assert ctx["result_contention"] is True


@then("no contention is detected")
def then_no_contention(ctx):
    assert ctx["result_contention"] is False


@then("arm1 is the winner")
def then_arm1_winner(ctx):
    assert ctx["result_winner"] is True


@then("arm2 is the loser")
def then_arm2_loser(ctx):
    arm2_result = ctx["arm_results"].get("arm2", {})
    assert arm2_result.get("winner") is False


@then(parsers.re(r'arm1 is the loser at step (?P<step>\d+)'))
def then_arm1_loser_at_step(ctx, step):
    assert ctx["result_winner"] is False


@then(parsers.re(r'the winners alternate as (?P<seq>.+)'))
def then_winners_alternate(ctx, seq):
    expected = seq.split()
    assert ctx["winners_sequence"] == expected


@then(parsers.re(
    r'the returned joints for arm1 are j3=(?P<j3>[\d.]+) j4=(?P<j4>[\d.]+) j5=(?P<j5>[\d.]+)'
))
def then_arm1_joints_match(ctx, j3, j4, j5):
    result = ctx["arm_results"].get("arm1", {}).get("joints") or ctx["result_joints"]
    assert result["j3"] == pytest.approx(float(j3))
    assert result["j4"] == pytest.approx(float(j4))
    assert result["j5"] == pytest.approx(float(j5))


@then(parsers.re(
    r'the returned joints for arm2 are j3=(?P<j3>-?[\d.]+) j4=(?P<j4>-?[\d.]+) j5=(?P<j5>-?[\d.]+)'
))
def then_arm2_joints_match(ctx, j3, j4, j5):
    result = ctx["arm_results"]["arm2"]["joints"]
    assert result["j3"] == pytest.approx(float(j3))
    assert result["j4"] == pytest.approx(float(j4))
    assert result["j5"] == pytest.approx(float(j5))
