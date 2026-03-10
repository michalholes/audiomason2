from __future__ import annotations

import sys
from pathlib import Path


def _import_runner_modules():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))

    from am_patch import gates_policy_wiring as wiring_mod
    from am_patch.config import Policy

    return Policy, wiring_mod


def test_biome_controls_propagated(monkeypatch, tmp_path: Path) -> None:
    policy_cls, wiring_mod = _import_runner_modules()

    captured: dict[str, object] = {}

    def fake_run_gates(*_args, **kwargs):
        captured["biome_format"] = kwargs.get("biome_format")
        captured["biome_format_command"] = kwargs.get("biome_format_command")

    import am_patch.gates as gates_mod

    monkeypatch.setattr(gates_mod, "run_gates", fake_run_gates)
    monkeypatch.setattr(wiring_mod, "changed_path_entries", lambda *_a, **_k: [])
    policy = policy_cls()
    policy.biome_format = False
    policy.gate_biome_format_command = ["biome", "format", "--write"]

    wiring_mod.run_policy_gates(
        logger=None,  # type: ignore[arg-type]
        cwd=tmp_path,
        repo_root=tmp_path,
        policy=policy,
        decision_paths=[],
        progress=None,
    )

    assert captured.get("biome_format") is False
    assert captured.get("biome_format_command") == ["biome", "format", "--write"]
