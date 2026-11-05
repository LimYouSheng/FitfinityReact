"""Prepare non-destructive Lambda/frontend template deltas; never execute AWS calls.

Input must be the observed current template, not a regenerated historical design.
The caller must still review IAM/features, scan, populated migration and recovery.
"""

import re
from copy import deepcopy

import hosting_design as design
from release_image import URI
from release_observation import digest, require


def prepare(template, *, observed_template_sha256, source_sha, image_digest, frontend_sha256):
    require(digest(template) == observed_template_sha256, "Observed template changed")
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha), "Exact source SHA required")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest), "Exact image digest required")
    require(re.fullmatch(r"[0-9a-f]{64}", frontend_sha256), "Exact frontend manifest required")
    resources = template["Resources"]
    function = resources["ApiFunction"]
    require(function["Type"] == "AWS::Lambda::Function", "Function resource differs")
    properties = function["Properties"]
    require(properties["FunctionName"] == design.FUNCTION, "Function identity differs")
    require(properties["PackageType"] == "Image", "Image runtime required")
    previous_image = properties["Code"]["ImageUri"]
    require(
        re.fullmatch(re.escape(URI) + r"@sha256:[0-9a-f]{64}", previous_image),
        "Previous image is not a retained exact repository digest",
    )
    alias = resources["ApiAlias"]
    require(
        alias["Type"] == "AWS::Lambda::Alias"
        and alias["Properties"]["Name"] == "first-test"
        and alias["Properties"]["FunctionName"] == {"Ref": "ApiFunction"}
        and not alias["Properties"].get("RoutingConfig"),
        "Alias identity/routing differs",
    )
    previous_version = alias["Properties"]["FunctionVersion"]
    require(
        isinstance(previous_version, dict) and set(previous_version) == {"Fn::GetAtt"},
        "Expected a managed Lambda version",
    )
    old_id, attribute = previous_version["Fn::GetAtt"]
    require(
        attribute == "Version" and resources[old_id]["Type"] == "AWS::Lambda::Version",
        "Previous version is missing",
    )
    new_id = "ReleaseVersion" + source_sha
    require(new_id not in resources, "Candidate version already exists; inspect before resuming")
    candidate = deepcopy(template)
    target = candidate["Resources"]
    target["ApiFunction"]["Properties"]["Code"] = {"ImageUri": URI + "@" + image_digest}
    target[new_id] = {
        "Type": "AWS::Lambda::Version",
        "DeletionPolicy": "Retain",
        "UpdateReplacePolicy": "Retain",
        "Properties": {"FunctionName": {"Ref": "ApiFunction"}, "Description": source_sha},
        "DependsOn": ["ApiFunction"],
    }
    target["ApiAlias"]["Properties"]["FunctionVersion"] = {"Fn::GetAtt": [new_id, "Version"]}
    distribution = target["Distribution"]["Properties"]["DistributionConfig"]
    origins = [origin for origin in distribution["Origins"] if origin["Id"] == "frontend"]
    require(
        len(origins) == 1
        and re.fullmatch(r"/releases/[0-9a-f]{40}/[0-9a-f]{64}", origins[0]["OriginPath"]),
        "Frontend origin does not bind a retained manifest",
    )
    origins[0]["OriginPath"] = f"/releases/{source_sha}/{frontend_sha256}"
    if "FunctionVersion" in candidate.get("Outputs", {}):
        candidate["Outputs"]["FunctionVersion"]["Value"] = {"Fn::GetAtt": [new_id, "Version"]}
    # Keep the new version managed even when rolling code/assets back. Never remove resources.
    rollback = deepcopy(template)
    rollback["Resources"][new_id] = deepcopy(target[new_id])
    return {
        "deployment_decision": "HOLD",
        "source_sha": source_sha,
        "base_template_sha256": observed_template_sha256,
        "candidate_template": candidate,
        "rollback_template": rollback,
        "preserved_resource_ids": sorted(resources),
        "migration": "Separate reviewed forward-only upgrade; no downgrade on code rollback",
        "required_before_execution": [
            "Fresh observed stack/configuration and no unexpected change-set replacement/deletion",
            "Exact image scan/provenance and frontend manifest verification",
            "Populated upgrade, runtime grants, maintenance and recoverable backup",
            "Current feature IAM/environment configuration review",
            "Explicit rollout authorization and post-deploy health/provider/device acceptance",
            "Prove outgoing code compatibility with upgraded schema before using rollback template",
        ],
    }
