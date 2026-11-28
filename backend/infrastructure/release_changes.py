"""Validate reviewed existing-stack release changes without executing cloud operations."""

import re

from deployment_profile import identities
from operator_checks import require
from release_observation import digest

RUNTIME_PROPERTIES = {
    "ApiFunction": (
        "AWS::Lambda::Function",
        {"Code", "Environment", "ReservedConcurrentExecutions"},
    ),
    "ApiAlias": ("AWS::Lambda::Alias", {"FunctionVersion"}),
    "Distribution": ("AWS::CloudFront::Distribution", {"DistributionConfig"}),
    "ApiRole": ("AWS::IAM::Role", {"Policies"}),
}


def expected_changes(original, candidate, *, mode, boundary_resource=None):
    """Derive the exact permitted resource/property delta from reviewed templates."""
    require(mode in {"rollout", "boundary", "pause", "resume"}, "Unknown release change mode")
    require(
        {k: v for k, v in original.items() if k not in {"Resources", "Outputs"}}
        == {k: v for k, v in candidate.items() if k not in {"Resources", "Outputs"}},
        "Unreviewed template attributes changed",
    )
    old_outputs, new_outputs = original.get("Outputs", {}), candidate.get("Outputs", {})
    require(set(old_outputs) == set(new_outputs), "Output inventory changed")
    for name in old_outputs:
        if old_outputs[name] != new_outputs[name]:
            require(mode == "rollout" and name == "FunctionVersion", "Unrelated output changed")
    before, after = original["Resources"], candidate["Resources"]
    require(set(before) <= set(after), "Resource deletion refused")
    expected = {}
    for name, resource in after.items():
        if name not in before:
            require(
                mode == "rollout"
                and re.fullmatch(r"ReleaseVersion[a-f0-9]{56}", name)
                and resource.get("Type") == "AWS::Lambda::Version"
                and resource.get("DeletionPolicy") == "Retain"
                and resource.get("UpdateReplacePolicy") == "Retain"
                and resource.get("Properties", {}).get("FunctionName") == {"Ref": "ApiFunction"},
                "Only the reviewed retained runtime version may be added",
            )
            expected[name] = ("Add", resource["Type"], set())
            continue
        previous = before[name]
        if previous == resource:
            continue
        require(
            {k: v for k, v in previous.items() if k != "Properties"}
            == {k: v for k, v in resource.items() if k != "Properties"},
            "Resource identity, policy or dependency attributes changed",
        )
        old, new = previous.get("Properties", {}), resource.get("Properties", {})
        missing = object()
        changed = {
            key for key in old.keys() | new.keys() if old.get(key, missing) != new.get(key, missing)
        }
        if name == boundary_resource and mode in {"rollout", "boundary"}:
            kind, allowed = "AWS::IAM::ManagedPolicy", {"PolicyDocument"}
        elif mode == "rollout" and name in RUNTIME_PROPERTIES:
            kind, allowed = RUNTIME_PROPERTIES[name]
        elif mode in {"pause", "resume"} and name == "ApiFunction":
            kind, allowed = "AWS::Lambda::Function", {"ReservedConcurrentExecutions"}
            require(
                type(old.get("ReservedConcurrentExecutions")) is int
                and type(new.get("ReservedConcurrentExecutions")) is int
                and (
                    old["ReservedConcurrentExecutions"] == 0
                    and new["ReservedConcurrentExecutions"] > 0
                    if mode == "resume"
                    else old["ReservedConcurrentExecutions"] > 0
                    and new["ReservedConcurrentExecutions"] == 0
                ),
                "Pause/resumption must change only explicit reviewed concurrency",
            )
        else:
            require(False, "Unrelated resource change refused")
        require(resource.get("Type") == kind and changed <= allowed, "Unrelated property changed")
        expected[name] = ("Modify", kind, changed)
    if mode == "rollout":
        old_concurrency = before["ApiFunction"]["Properties"].get("ReservedConcurrentExecutions")
        require(
            type(old_concurrency) is int and old_concurrency == 0,
            "CloudFormation rollback baseline must already keep traffic paused",
        )
        concurrency = after["ApiFunction"]["Properties"].get("ReservedConcurrentExecutions")
        require(type(concurrency) is int and concurrency == 0, "Rollout must keep traffic paused")
        require(sum(row[0] == "Add" for row in expected.values()) == 1, "One new version required")
    require(bool(expected), "No release changes to review")
    return expected


def unchanged_attribute_dependency(original, candidate, name, detail, expected):
    """Recognize a retained attribute reference to another reviewed resource change."""
    key = detail.get("Target", {}).get("Name")
    before = original["Resources"][name].get("Properties", {})
    after = candidate["Resources"][name].get("Properties", {})
    value = before.get(key)
    if key not in before or key not in after or value != after[key]:
        return False
    cause = detail.get("CausingEntity", "")
    if not isinstance(cause, str) or "." not in cause:
        return False
    resource, _ = cause.split(".", 1)
    return (
        resource in expected
        and expected[resource][0] == "Modify"
        and detail.get("Evaluation") == "Dynamic"
        and detail.get("ChangeSource") == "ResourceAttribute"
        and contains_attribute_reference(value, cause)
    )


def contains_attribute_reference(value, cause):
    """Find an actual attribute reference, respecting Sub escapes and variable overrides."""
    if isinstance(value, list):
        return any(contains_attribute_reference(item, cause) for item in value)
    if not isinstance(value, dict):
        return False
    if set(value) == {"Fn::GetAtt"}:
        reference = value["Fn::GetAtt"]
        return reference == cause or reference == cause.split(".", 1)
    if set(value) == {"Fn::Sub"}:
        expression = value["Fn::Sub"]
        variables = {}
        if isinstance(expression, list):
            if len(expression) != 2 or not isinstance(expression[1], dict):
                return False
            expression, variables = expression
        if not isinstance(expression, str):
            return False
        for token in re.findall(r"\$\{([^}]+)\}", expression):
            if token.startswith("!"):
                continue
            if token in variables:
                if contains_attribute_reference(variables[token], cause):
                    return True
            elif token == cause:
                return True
        return False
    return any(contains_attribute_reference(item, cause) for item in value.values())


def validate(
    original,
    candidate,
    change_set,
    *,
    profile,
    stack_arn,
    reviewed_template_sha256,
    mode="rollout",
    boundary_resource=None,
):
    """Require the complete change set to match the reviewed target and property delta."""
    target = identities(profile)
    prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
    require(
        isinstance(stack_arn, str)
        and re.fullmatch(re.escape(prefix) + r"[A-Za-z][A-Za-z0-9-]*/[a-f0-9-]+", stack_arn)
        and (mode == "boundary" or stack_arn.split("/")[1] == target["hosting_stack"]),
        "Wrong release stack identity",
    )
    require(digest(candidate) == reviewed_template_sha256, "Reviewed candidate bytes changed")
    require(
        change_set.get("Status") == "CREATE_COMPLETE"
        and change_set.get("ExecutionStatus") == "AVAILABLE"
        and change_set.get("StackId") == stack_arn
        and not change_set.get("NextToken")
        and not change_set.get("IncludeNestedStacks"),
        "Complete executable change set for the exact stack required",
    )
    expected = expected_changes(original, candidate, mode=mode, boundary_resource=boundary_resource)
    seen = set()
    for row in change_set.get("Changes", []):
        require(row.get("Type") == "Resource", "Unknown change kind")
        resource = row.get("ResourceChange", {})
        name = resource.get("LogicalResourceId")
        require(name in expected and name not in seen, "Unexpected or duplicate resource change")
        seen.add(name)
        action, kind, properties = expected[name]
        require(
            resource.get("Action") == action
            and resource.get("ResourceType") == kind
            and (
                resource.get("Replacement") == "False"
                if action == "Modify"
                else resource.get("Replacement") in (None, "False")
            )
            and not resource.get("ChangeSetId"),
            "Replacement, nested or unexpected resource change refused",
        )
        if action == "Modify":
            require(resource.get("Scope") == ["Properties"], "Non-property change refused")
            observed = set()
            for detail in resource.get("Details", []):
                target_property = detail.get("Target", {})
                require(
                    target_property.get("Attribute") == "Properties"
                    and (
                        target_property.get("Name") in properties
                        or (
                            mode == "rollout"
                            and unchanged_attribute_dependency(
                                original, candidate, name, detail, expected
                            )
                        )
                    )
                    and target_property.get("RequiresRecreation") == "Never",
                    f"Unreviewed property or possible recreation refused: {name}."
                    f"{target_property.get('Name', 'unknown')}",
                )
                if target_property["Name"] in properties:
                    observed.add(target_property["Name"])
            require(observed == properties, "Incomplete property-change evidence")
    require(seen == set(expected), "Incomplete resource-change evidence")
    return {"stack_arn": stack_arn, "template_sha256": reviewed_template_sha256, "mode": mode}
