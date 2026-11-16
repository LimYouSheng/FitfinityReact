"""Execute fixed rollout API operations without retries or private error output."""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from deployment_profile import identities
from operator_checks import require

OPERATIONS = {
    ("sts", "get-caller-identity"),
    ("ecr", "describe-image-scan-findings"),
    ("s3api", "head-object"),
    ("s3api", "put-object"),
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "get-template"),
    ("cloudformation", "describe-stack-resource"),
    ("cloudformation", "list-stack-resources"),
    ("cloudformation", "create-change-set"),
    ("cloudformation", "describe-change-set"),
    ("cloudformation", "execute-change-set"),
    ("lambda", "get-function"),
    ("lambda", "get-function-concurrency"),
    ("iam", "get-role"),
    ("iam", "list-entities-for-policy"),
}


def aws(service, operation, values, *, profile):
    """Translate fixed calls and distinguish a missing object from access denial."""
    require((service, operation) in OPERATIONS, "Rollout operation is not allowed")
    require(
        not any(key.startswith("AWS_ENDPOINT_URL") for key in os.environ),
        "AWS endpoint override refused",
    )
    values = dict(values)
    with tempfile.TemporaryDirectory(prefix="fitfinity-upload-") as temporary:
        extra = []
        if (service, operation) == ("s3api", "put-object"):
            body = values.pop("Body")
            require(
                isinstance(body, bytes) and len(body) <= 20 * 1024 * 1024,
                "Bounded frontend bytes required",
            )
            path = Path(temporary) / "object"
            path.write_bytes(body)
            extra = ["--body", str(path)]
        result = subprocess.run(
            [
                "aws",
                service,
                operation,
                "--cli-input-json",
                json.dumps(values),
                *extra,
                "--region",
                identities(profile)["region"],
                "--output",
                "json",
                "--no-cli-pager",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                "AWS_MAX_ATTEMPTS": "1",
                "AWS_EC2_METADATA_DISABLED": "true",
                "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
            },
        )
    if result.returncode != 0:
        missing = re.search(
            r"An error occurred \((404|NoSuchKey|NotFound)\) when calling the HeadObject operation",
            result.stderr,
        )
        if (service, operation) == ("s3api", "head-object") and missing:
            return None
        raise RuntimeError("Rollout call failed; inspect original intent before recovery")
    return json.loads(result.stdout) if result.stdout.strip() else {}
