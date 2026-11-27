"""Safe deployment diagnostics: static checks and allowlisted provider codes only."""

import json
import re
import subprocess

from operator_checks import OperatorCheckError

PROVIDER_ERRORS = frozenset(
    {
        "AccessDenied",
        "NoSuchBucket",
        "PreconditionFailed",
        "ConditionalRequestConflict",
        "RequestTimeout",
        "ValidationError",
        "ChangeSetNotFound",
        "Throttling",
        "ThrottlingException",
        "ExpiredToken",
        "ScanNotFoundException",
        "ImageNotFoundException",
        "RepositoryNotFoundException",
        "AccessDeniedException",
        "ExpiredTokenException",
        "InvalidClientTokenId",
        "UnrecognizedClientException",
        "ResourceNotFoundException",
        "ResourceConflictException",
        "ResourceNotReadyException",
        "TooManyRequestsException",
        "InvalidRequestContentException",
        "InvalidParameterValueException",
        "InvalidRuntimeException",
        "InvalidZipFileException",
        "InvalidSecurityGroupIDException",
        "InvalidSubnetIDException",
        "EC2AccessDeniedException",
        "EC2ThrottledException",
        "EC2UnexpectedException",
        "ENILimitReachedException",
        "SubnetIPAddressLimitReachedException",
        "EFSIOException",
        "EFSMountConnectivityException",
        "EFSMountFailureException",
        "EFSMountTimeoutException",
        "KMSAccessDeniedException",
        "KMSDisabledException",
        "KMSInvalidStateException",
        "KMSNotFoundException",
        "SnapStartException",
        "SnapStartNotReadyException",
        "SnapStartTimeoutException",
        "ServiceException",
        "RequestTooLargeException",
        "UnsupportedMediaTypeException",
    }
)


def failure_code(stderr):
    """Return only static diagnostic labels; never copy provider messages or unknown tokens."""
    match = re.search(
        r"An error occurred \(([A-Za-z0-9]+)\) when calling the [A-Za-z0-9]+ operation",
        stderr,
    )
    if match:
        return next((code for code in PROVIDER_ERRORS if code == match[1]), "UnknownProviderError")
    if "Parameter validation failed:" in stderr or "An error occurred (ParamValidation):" in stderr:
        return "CliParameterValidation"
    if "Error parsing parameter" in stderr or "Unknown options:" in stderr:
        return "CliArgumentError"
    return "UnclassifiedCliFailure"


class OperatorFailure(RuntimeError):
    """A diagnostic constructed only from fixed operation names and safe codes."""


def provider_failure(service, operation, stderr):
    code = failure_code(stderr)
    return OperatorFailure(
        f"AWS {service}/{operation} failed; code={code}. "
        "inspect original intent and AWS state before retrying a write."
    )


def run_process(*args, **kwargs):
    """Never expose TimeoutExpired command arguments or captured private output."""
    try:
        return subprocess.run(*args, **kwargs)
    except subprocess.TimeoutExpired:
        raise OperatorFailure(
            "AWS CLI timed out locally; code=LocalProcessTimeout. "
            "The request may have reached AWS; inspect original intent before recovery."
        ) from None
    except FileNotFoundError:
        raise OperatorFailure("AWS CLI executable missing; check runner installation.") from None


def decode_response(stdout, service, operation):
    try:
        return json.loads(stdout) if stdout.strip() else {}
    except (ValueError, TypeError):
        raise OperatorFailure(
            f"AWS {service}/{operation} returned invalid JSON; code=InvalidProviderResponse. "
            "Inspect original intent before retrying a write."
        ) from None


def safe_reason(error):
    """Unexpected exceptions must not leak provider replies, command arguments or payloads."""
    if isinstance(error, (OperatorCheckError, OperatorFailure)):
        return str(error)
    if isinstance(error, (KeyError, TypeError, ValueError)):
        return "Unexpected response structure; check the stage's input and response contract."
    if isinstance(error, OSError):
        return (
            "Local file or network operation failed; "
            "inspect runner availability and retained receipt."
        )
    return "Unexpected operator failure; inspect the retained phase and original resource state."


def retain_failure(journal, error, stage):
    reason = safe_reason(error)
    journal.save({**journal.value, "error": reason, "failed_stage": stage})
    return OperatorFailure(f"{stage} failed: {reason}")
