"""Validate portable SES bindings and derive the runtime's exact permissions."""

import re

from operator_checks import require

KEYS = {
    "FITFINITY_TRANSACTIONAL_EMAIL_ENABLED",
    "FITFINITY_EMAIL_SENDER",
    "FITFINITY_EMAIL_DISPATCH_SECRET_ARN",
    "FITFINITY_EMAIL_CONFIGURATION_SET",
    "FITFINITY_EMAIL_IDENTITY_ARN",
}


def checked(target, value):
    """Require explicit sender and dedicated target secret; never accept credential values."""
    if value is None:
        return None
    require(
        isinstance(value, dict)
        and set(value) == {"sender", "identity_arn", "dispatch_secret", "configuration_set"},
        "Exact email bindings required",
    )
    sender, identity, secret, configuration = (
        value[k] for k in ("sender", "identity_arn", "dispatch_secret", "configuration_set")
    )
    require(
        isinstance(sender, str)
        and re.fullmatch(r"[A-Za-z0-9.!#$%&'+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", sender),
        "Valid email sender required",
    )
    root = f"arn:aws:ses:{target['region']}:{target['account']}:identity/"
    require(
        identity in {root + sender, root + sender.split("@", 1)[1]},
        "SES identity must match the sender in this target",
    )
    require(
        isinstance(secret, str)
        and re.fullmatch(
            rf"arn:aws:secretsmanager:{re.escape(target['region'])}:{target['account']}:secret:{re.escape(target['secret_prefix'])}/email-dispatch-[A-Za-z0-9]{{6}}",
            secret,
        ),
        "Exact target email dispatch secret required",
    )
    require(
        isinstance(configuration, str)
        and (configuration == "" or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", configuration)),
        "Invalid SES configuration set",
    )
    return dict(value)


def environment(target, value):
    """Render only validated public configuration; secret material stays in Secrets Manager."""
    value = checked(target, value)
    if value is None:
        return {}
    return {
        "FITFINITY_TRANSACTIONAL_EMAIL_ENABLED": "true",
        "FITFINITY_EMAIL_SENDER": value["sender"],
        "FITFINITY_EMAIL_IDENTITY_ARN": value["identity_arn"],
        "FITFINITY_EMAIL_DISPATCH_SECRET_ARN": value["dispatch_secret"],
        "FITFINITY_EMAIL_CONFIGURATION_SET": value["configuration_set"],
    }


def access(target, value):
    """Allow one sender identity and signing secret, with no SES administration."""
    value = checked(target, value)
    if value is None:
        return []
    resources = [value["identity_arn"]]
    if value["configuration_set"]:
        resources.append(
            f"arn:aws:ses:{target['region']}:{target['account']}:configuration-set/{value['configuration_set']}"
        )
    return [
        {
            "Effect": "Allow",
            "Action": ["ses:SendEmail"],
            "Resource": resources,
            "Condition": {"StringEquals": {"ses:FromAddress": value["sender"]}},
        },
        {
            "Effect": "Allow",
            "Action": ["secretsmanager:GetSecretValue"],
            "Resource": value["dispatch_secret"],
            "Condition": {"StringEquals": {"secretsmanager:VersionStage": "AWSCURRENT"}},
        },
    ]


def from_environment(target, env):
    """Reconstruct a complete prior binding for normal releases and rollback."""
    present = set(env) & KEYS
    if not present:
        return None
    require(
        present == KEYS and env["FITFINITY_TRANSACTIONAL_EMAIL_ENABLED"] == "true",
        "Incomplete or ambiguous original email configuration",
    )
    return checked(
        target,
        {
            "sender": env["FITFINITY_EMAIL_SENDER"],
            "identity_arn": env["FITFINITY_EMAIL_IDENTITY_ARN"],
            "dispatch_secret": env["FITFINITY_EMAIL_DISPATCH_SECRET_ARN"],
            "configuration_set": env["FITFINITY_EMAIL_CONFIGURATION_SET"],
        },
    )
