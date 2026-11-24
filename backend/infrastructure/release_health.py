"""Verify deployed release identity and bounded public readiness without user credentials."""

import hashlib
import json
import re
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from deployment_profile import identities
from operator_checks import require
from release_execution import template
from release_observation import digest


class NoRedirect(HTTPRedirectHandler):
    """Refuse redirects so readiness cannot silently move to another endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_url(url):
    """Fetch bounded HTTPS health bytes without retries, redirects or credentials."""
    require(
        re.fullmatch(
            r"https://[a-z0-9]+\.cloudfront\.net/(?:index\.html|health/(?:live|ready))", url
        ),
        "Exact CloudFront health URL required",
    )
    request = Request(url, headers={"Cache-Control": "no-cache"})
    try:
        with build_opener(NoRedirect).open(request, timeout=15) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            require(
                response.status == 200 and len(body) <= 2 * 1024 * 1024,
                "Bounded successful health response required",
            )
            return body
    except (HTTPError, OSError):
        raise RuntimeError("Public release readiness request failed") from None


def verify(review, evidence, call, read, expected_index, *, profile, now=None):
    """Bind live image, frontend distribution and API readiness to the reviewed release."""
    target = identities(profile)
    rows = call("cloudformation", "describe-stacks", {"StackName": review["stack_arn"]})["Stacks"]
    require(
        len(rows) == 1
        and rows[0].get("StackId") == review["stack_arn"]
        and rows[0].get("StackStatus") == "UPDATE_COMPLETE",
        "Completed release stack required",
    )
    require(
        template(call, review["stack_arn"]) == review["candidate_template"],
        "Live release template differs",
    )
    outputs = rows[0].get("Outputs", [])
    values = {row["OutputKey"]: row["OutputValue"] for row in outputs}
    require(len(values) == len(outputs), "Unique stack outputs required")
    domain, distribution, version = (
        values.get(key, "") for key in ("FrontendDomain", "DistributionId", "FunctionVersion")
    )
    require(
        re.fullmatch(r"[a-z0-9]+\.cloudfront\.net", domain)
        and re.fullmatch(r"[A-Z0-9]+", distribution)
        and re.fullmatch(r"[1-9][0-9]*", version),
        "Exact public release identities required",
    )
    dist = call("cloudfront", "get-distribution", {"Id": distribution})["Distribution"]
    require(
        dist.get("ARN") == f"arn:aws:cloudfront::{target['account']}:distribution/{distribution}"
        and dist.get("DomainName") == domain
        and dist.get("Status") == "Deployed"
        and dist.get("DistributionConfig", {}).get("Enabled") is True,
        "Owned deployed distribution required",
    )
    origins = dist["DistributionConfig"].get("Origins", {}).get("Items", [])
    frontend = [row for row in origins if row.get("Id") == "frontend"]
    require(
        len(frontend) == 1 and frontend[0].get("OriginPath") == "/" + evidence["frontend_prefix"],
        "Deployed frontend release differs",
    )
    alias = review["candidate_template"]["Resources"]["ApiAlias"]["Properties"]["Name"]
    actual_alias = call(
        "lambda", "get-alias", {"FunctionName": target["runtime_function"], "Name": alias}
    )
    require(
        actual_alias.get("FunctionVersion") == version
        and not actual_alias.get("RoutingConfig", {}).get("AdditionalVersionWeights"),
        "Runtime alias version or weighted routing differs",
    )
    function = call(
        "lambda", "get-function", {"FunctionName": target["runtime_function"], "Qualifier": version}
    )
    require(
        function.get("Configuration", {}).get("Version") == version
        and function.get("Code", {}).get("ResolvedImageUri")
        == target["registry"] + "/" + target["image_repository"] + "@" + evidence["image_digest"],
        "Deployed runtime image differs",
    )
    concurrency = call(
        "lambda", "get-function-concurrency", {"FunctionName": target["runtime_function"]}
    ).get("ReservedConcurrentExecutions")
    require(
        type(concurrency) is int
        and concurrency > 0
        and concurrency
        == review["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ],
        "Reviewed active capacity required",
    )
    require(
        isinstance(expected_index, bytes) and expected_index, "Reviewed frontend index required"
    )
    base = "https://" + domain
    require(read(base + "/index.html") == expected_index, "Public frontend bytes differ")
    for path, status in (("live", "alive"), ("ready", "ready")):
        require(
            json.loads(read(base + "/health/" + path)) == {"status": status},
            "Public API health response differs",
        )
    return {
        "state": "health_verified",
        "review_sha256": digest(review),
        "evidence_sha256": digest(evidence),
        "observed_at": time.time() if now is None else now,
        "frontend_sha256": hashlib.sha256(expected_index).hexdigest(),
        "function_version": version,
        "domain": domain,
    }
