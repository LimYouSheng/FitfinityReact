"""Prepare non-destructive Lambda/frontend template deltas; never execute AWS calls.

Input must be the observed current template, not a regenerated historical design.
The caller must still review IAM/features, scan, populated migration and recovery.
"""

import re
from copy import deepcopy

from deployment_profile import DEVELOPER, identities
from release_features import prepare as prepare_features
from release_observation import digest, require


def prepare(
    template,
    *,
    observed_template_sha256,
    source_sha,
    image_digest,
    frontend_sha256,
    profile=DEVELOPER,
    feature_values=None,
    boundary_template=None,
    boundary_template_sha256=None,
):
    target_identity = identities(profile)
    uri = target_identity["registry"] + "/" + target_identity["image_repository"]
    require(digest(template) == observed_template_sha256, "Observed template changed")
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha), "Exact source SHA required")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest), "Exact image digest required")
    require(re.fullmatch(r"[0-9a-f]{64}", frontend_sha256), "Exact frontend manifest required")
    resources = template["Resources"]
    function = resources["ApiFunction"]
    require(function["Type"] == "AWS::Lambda::Function", "Function resource differs")
    properties = function["Properties"]
    require(
        properties["FunctionName"] == target_identity["runtime_function"],
        "Function identity differs",
    )
    require(properties["PackageType"] == "Image", "Image runtime required")
    require(
        type(properties.get("ReservedConcurrentExecutions")) is int
        and properties["ReservedConcurrentExecutions"] >= 0,
        "Explicit runtime concurrency required",
    )
    previous_image = properties["Code"]["ImageUri"]
    require(
        re.fullmatch(re.escape(uri) + r"@sha256:[0-9a-f]{64}", previous_image),
        "Previous image is not a retained exact repository digest",
    )
    alias = resources["ApiAlias"]
    require(
        alias["Type"] == "AWS::Lambda::Alias"
        and alias["Properties"]["Name"] == target_identity["runtime_alias"]
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
    feature_review = None
    if feature_values is not None:
        feature_review = prepare_features(
            template,
            feature_values,
            profile=profile,
            boundary_template=boundary_template,
            boundary_template_sha256=boundary_template_sha256,
        )
    else:
        require(
            boundary_template is None and boundary_template_sha256 is None,
            "Boundary changes require an explicit feature review",
        )
    candidate = (
        deepcopy(feature_review["candidate_template"]) if feature_review else deepcopy(template)
    )
    target = candidate["Resources"]
    target["ApiFunction"]["Properties"]["Code"] = {"ImageUri": uri + "@" + image_digest}
    target["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 0
    configuration = {"runtime": target["ApiFunction"]["Properties"], "frontend": frontend_sha256}
    new_id = "ReleaseVersion" + source_sha + digest(configuration)[:16]
    require(new_id not in resources, "Candidate version already exists; inspect before resuming")
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
    rollback["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 0
    return {
        "deployment_decision": "HOLD",
        **({"feature_review": feature_review} if feature_review else {}),
        "profile_sha256": target_identity["profile_sha256"],
        "source_sha": source_sha,
        "base_template_sha256": observed_template_sha256,
        "candidate_template": candidate,
        "rollback_template": rollback,
        "preserved_resource_ids": sorted(resources),
        "migration": "Separate reviewed forward-only upgrade; no downgrade on code rollback",
        "traffic": "Keep concurrency zero through forward/rollback; separately review resumption",
        "required_before_execution": [
            "Fresh observed stack/configuration and no unexpected change-set replacement/deletion",
            "Exact image scan/provenance and frontend manifest verification",
            "Populated upgrade, runtime grants, maintenance and recoverable backup",
            "Current feature IAM/environment configuration review",
            "Explicit rollout authorization and post-deploy health/provider/device acceptance",
            "Prove outgoing code compatibility with upgraded schema before using rollback template",
        ],
    }
