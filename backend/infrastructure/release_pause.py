"""Check the saved hosting-stack pause before data or runtime changes."""

import json
import re

from deployment_profile import identities
from operator_checks import require


def require_recorded_pause(call, profile):
    """Require CloudFormation's rollback baseline to keep the staff runtime paused."""
    target = identities(profile)
    rows = call("cloudformation", "describe-stacks", {"StackName": target["hosting_stack"]})[
        "Stacks"
    ]
    prefix = (
        f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
        + target["hosting_stack"]
        + "/"
    )
    require(
        len(rows) == 1
        and rows[0].get("StackName") == target["hosting_stack"]
        and re.fullmatch(re.escape(prefix) + r"[a-f0-9-]+", rows[0].get("StackId", ""))
        and rows[0].get("StackStatus")
        in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"},
        "Stable target hosting stack required before migration or rollout",
    )
    value = call(
        "cloudformation",
        "get-template",
        {
            "StackName": rows[0]["StackId"],
            "TemplateStage": "Original",
        },
    )["TemplateBody"]
    value = json.loads(value) if isinstance(value, str) else value
    function = value.get("Resources", {}).get("ApiFunction", {})
    props = function.get("Properties", {})
    require(
        function.get("Type") == "AWS::Lambda::Function"
        and props.get("FunctionName") == target["runtime_function"]
        and type(props.get("ReservedConcurrentExecutions")) is int
        and props["ReservedConcurrentExecutions"] == 0,
        "Record concurrency zero in CloudFormation before migration or rollout",
    )
