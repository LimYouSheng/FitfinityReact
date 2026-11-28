"""Bind optional email activation to reviewed configuration and actual stack templates."""

import json
import os

import email_runtime
from deployment_profile import identities, load
from operator_checks import require
from portable_hosting import bindings
from release_execution import template
from release_features import FEATURE_FLAGS, external_identity
from release_observation import digest


def configured(configuration, profile):
    """Reject incomplete email configuration before any release is paused."""
    value = configuration.get("email")
    if value is None:
        require("email_boundary" not in configuration, "Email boundary requires email bindings")
        return None
    email_runtime.checked(identities(profile), value)
    owner = configuration.get("email_boundary")
    if owner is not None:
        external_identity(owner, profile)
        target = identities(profile)
        require(
            owner["stack_arn"].split("/")[1] == target["resource_prefix"] + "-github-hosting",
            "Coordinator email boundary must use the existing hosting-access stack",
        )
    return value


def hosting_values(installed, profile, email):
    """Preserve all existing hosting/feature bindings; only email is newly configured."""
    resources = installed["Resources"]
    function = resources["ApiFunction"]["Properties"]
    env = function["Environment"]["Variables"]
    values = {
        key: env[name]
        for key, name in {
            "database_secret": "FITFINITY_DATABASE_SECRET_ARN",
            "auth_secret": "FITFINITY_AUTH_SECRET_ARN",
            "db_host": "FITFINITY_DB_HOST",
            "pool": "FITFINITY_COGNITO_POOL_ID",
            "client": "FITFINITY_COGNITO_CLIENT_ID",
            "environment": "FITFINITY_ENVIRONMENT",
        }.items()
    }
    flags = {key: env.get(name, "false") for key, name in FEATURE_FLAGS.items()}
    require(all(value in {"true", "false"} for value in flags.values()), "Ambiguous feature flags")
    values.update(
        image=function["Code"]["ImageUri"],
        subnets=function["VpcConfig"]["SubnetIds"],
        security_groups=function["VpcConfig"]["SecurityGroupIds"],
        stage=resources["ApiStage"]["Properties"]["StageName"],
        features={key: value == "true" for key, value in flags.items()},
        email=email,
    )
    bindings(profile, values)
    return values


def rollout_arguments(configuration, installed, profile, call):
    """Freeze email and boundary inputs in the same hashed review used by child workflows."""
    email = configured(configuration, profile)
    if email is None:
        return {}, {}
    values = hosting_values(installed, profile, email)
    args = {"feature_values": values}
    review = {"feature_values": values}
    boundary = installed["Resources"]["ApiRole"]["Properties"]["PermissionsBoundary"]
    owner = configuration.get("email_boundary")
    if isinstance(boundary, str):
        require(owner is not None, "Configure the observed external email boundary owner")
        document = template(call, owner["stack_arn"])
        require(digest(document) == owner["template_sha256"], "Email boundary template changed")
        args.update(boundary_template=document, boundary_template_sha256=digest(document))
        review["external_boundary"] = owner
    else:
        require(owner is None, "Internal runtime boundary must not have an external owner")
    return args, review


def verify_review(configuration, review, profile):
    """Compare new rollout intent; recovery continues using its original frozen review."""
    email = configured(configuration, profile)
    requested = review.get("feature_values", {}).get("email")
    require(requested == email, "Reviewed email settings differ from release configuration")
    if email is not None:
        require(
            review.get("external_boundary") == configuration.get("email_boundary"),
            "Reviewed email boundary differs from release configuration",
        )


if __name__ == "__main__":
    if os.environ["ROLLOUT_MODE"] in {"upload", "create", "deploy"}:
        verify_review(
            json.loads(os.environ.get("FITFINITY_RELEASE_CONFIG_JSON") or "{}"),
            json.loads(os.environ["ROLLOUT_REVIEW"]),
            load(os.environ["DEPLOYMENT_PROFILE"]),
        )
    print("Email review configuration checked; original recovery inputs preserved")
