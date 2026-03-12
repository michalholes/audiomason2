def test_policy_schema_includes_all_policy_fields():
    from dataclasses import fields

    from am_patch.config import Policy
    from am_patch.config_schema import get_policy_schema

    schema = get_policy_schema()
    policy = schema.get("policy")
    assert isinstance(policy, dict)

    expected = {f.name for f in fields(Policy) if f.name != "_src"}
    assert set(policy.keys()) == expected


def test_policy_schema_exposes_bucketed_pytest_routing_keys() -> None:
    from am_patch.config_schema import SCHEMA_VERSION, get_policy_schema

    schema = get_policy_schema()
    policy = schema["policy"]

    assert SCHEMA_VERSION == "2"
    assert schema["schema_version"] == "2"
    assert policy["pytest_routing_mode"]["enum"] == ["legacy", "bucketed"]
    assert policy["pytest_area_targets"]["type"] == "dict[str,list[str]]"
