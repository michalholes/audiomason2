from __future__ import annotations

from am_patch.apply_failure_gates_policy import evaluate_apply_failure_gates_policy


def test_apply_failure_gates_policy_matrix() -> None:
    # attempt=1, partial fail, policy=repair_only -> False
    assert (
        evaluate_apply_failure_gates_policy(
            patch_applied_any=True,
            workspace_attempt=1,
            partial_policy="repair_only",
            zero_policy="never",
        )
        is False
    )

    # attempt=2, partial fail, policy=repair_only -> True
    assert (
        evaluate_apply_failure_gates_policy(
            patch_applied_any=True,
            workspace_attempt=2,
            partial_policy="repair_only",
            zero_policy="never",
        )
        is True
    )

    # attempt=2, zero fail, policy=never -> False
    assert (
        evaluate_apply_failure_gates_policy(
            patch_applied_any=False,
            workspace_attempt=2,
            partial_policy="repair_only",
            zero_policy="never",
        )
        is False
    )

    # attempt=1, zero fail, policy=always -> True
    assert (
        evaluate_apply_failure_gates_policy(
            patch_applied_any=False,
            workspace_attempt=1,
            partial_policy="repair_only",
            zero_policy="always",
        )
        is True
    )

    # attempt=2, partial fail, policy=never -> False
    assert (
        evaluate_apply_failure_gates_policy(
            patch_applied_any=True,
            workspace_attempt=2,
            partial_policy="never",
            zero_policy="never",
        )
        is False
    )
