import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

PROFILE = "fitfinity-test"
REGION = "ap-southeast-1"
ACCOUNT = "418638389566"
REPO = "fitfinity-test-api"
OWNER = "fitfinity-test-image-uploader"
IMAGE = "fitfinity-api:admin-access"
EXPECTED = "sha256:efa53edd08c54786bb7e04cc2509b6ace31ff903d1a2c473f203548b2e4d6d12"
EXPECTED_CREATED = "2026-09-24T17:33:51.472849773Z"
EXPECTED_MANIFEST = EXPECTED
SCAN_ATTEMPTS = 19
SCAN_INTERVAL_SECONDS = 10
CLOUD_WRITE_ATTEMPTED = False
UPLOAD_VERIFIED = False
AUTHORIZED = False
GREEN = "\033[32m" if sys.stdout.isatty() else ""
BLUE = "\033[36m" if sys.stdout.isatty() else ""
RESET = "\033[0m" if sys.stdout.isatty() else ""


def note(message):
    print(BLUE + message + RESET, flush=True)


def fail(message):
    raise RuntimeError(message)


def command(args, capture=True, input_data=None, env=None):
    result = subprocess.run(
        args,
        input=input_data,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=env,
    )
    return result


def checked(args, capture=True, input_data=None, env=None):
    result = command(args, capture, input_data, env)
    if result.returncode:
        fail((result.stderr or "Command failed; see the output above.").strip())
    return result.stdout or ""


def aws_args(service, operation, *args):
    return [
        "aws",
        service,
        operation,
        "--profile",
        PROFILE,
        "--region",
        REGION,
        "--output",
        "json",
        "--no-cli-pager",
        "--no-cli-auto-prompt",
        "--cli-connect-timeout",
        "10",
        "--cli-read-timeout",
        "60",
        *args,
    ]


def aws(service, operation, *args):
    return json.loads(checked(aws_args(service, operation, *args)))


def maybe(service, operation, missing_code, *args):
    result = command(aws_args(service, operation, *args))
    if result.returncode:
        if "(" + missing_code + ")" in (result.stderr or ""):
            return None
        fail((result.stderr or "AWS request failed.").strip())
    return json.loads(result.stdout)


def verify_repository(repository, account):
    if (
        repository.get("registryId") != account
        or repository.get("repositoryName") != REPO
        or repository.get("repositoryArn") != f"arn:aws:ecr:{REGION}:{account}:repository/{REPO}"
        or repository.get("repositoryUri") != f"{account}.dkr.ecr.{REGION}.amazonaws.com/{REPO}"
        or repository.get("imageTagMutability") != "IMMUTABLE"
        or repository.get("encryptionConfiguration", {}).get("encryptionType") != "AES256"
    ):
        fail("Existing repository configuration differs. Nothing will be overwritten.")
    tags = aws("ecr", "list-tags-for-resource", "--resource-arn", repository["repositoryArn"])
    tags = {item["Key"]: item["Value"] for item in tags.get("tags", [])}
    if any(
        tags.get(key) != value
        for key, value in {
            "Application": "Fitfinity",
            "Environment": "test",
            "ManagedBy": OWNER,
        }.items()
    ):
        fail("Repository ownership tags differ. Refusing to reuse an unrelated repository.")


def remote_image(tag):
    return maybe(
        "ecr",
        "describe-images",
        "ImageNotFoundException",
        "--repository-name",
        REPO,
        "--image-ids",
        "imageTag=" + tag,
    )


def verify_remote(tag):
    response = aws(
        "ecr", "batch-get-image", "--repository-name", REPO, "--image-ids", "imageTag=" + tag
    )
    images = response.get("images", [])
    if response.get("failures") or len(images) != 1:
        fail("Unable to verify the remote image manifest.")
    manifest = json.loads(images[0]["imageManifest"])
    if images[0]["imageId"]["imageDigest"] != EXPECTED_MANIFEST or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", manifest.get("config", {}).get("digest", "")
    ):
        fail("Remote tag does not reference the accepted local image. Refusing to overwrite it.")
    digest = images[0]["imageId"]["imageDigest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        fail("Invalid image digest in AWS response.")
    return digest


def authorize(action):
    global AUTHORIZED
    if AUTHORIZED:
        return
    note("Target account: " + ACCOUNT)
    note("Region: " + REGION + " | Existing private repository: " + REPO)
    note("Pinned image: " + IMAGE + " | " + EXPECTED)
    note("Action: " + action)
    note("ECR storage may consume credits or incur charges under your account plan.")
    note("No database, Lambda, networking, DNS, source edits, or deletions are performed.")
    # Embedded stdin contains Python source. Use separate terminal handles on macOS.
    with open("/dev/tty", "w") as terminal_output:
        terminal_output.write("To authorize this image publication/scan, type " + ACCOUNT + ": ")
        terminal_output.flush()
    with open("/dev/tty") as terminal_input:
        answer = terminal_input.readline().strip()
    if answer != ACCOUNT:
        fail("Account confirmation did not match. No cloud resources were changed.")
    AUTHORIZED = True


def verify_scan_identity(scan, digest):
    if (
        scan.get("registryId") != ACCOUNT
        or scan.get("repositoryName") != REPO
        or scan.get("imageId", {}).get("imageDigest") != digest
    ):
        fail("Scan response does not match the accepted account, repository and image digest.")


def save_scan(digest):
    global CLOUD_WRITE_ATTEMPTED
    note("Reading the vulnerability scan for the verified image…")
    scan = None
    started = False
    for attempt in range(SCAN_ATTEMPTS):
        scan = maybe(
            "ecr",
            "describe-image-scan-findings",
            "ScanNotFoundException",
            "--registry-id",
            ACCOUNT,
            "--repository-name",
            REPO,
            "--image-id",
            "imageDigest=" + digest,
        )
        if scan is not None:
            verify_scan_identity(scan, digest)
            status = scan.get("imageScanStatus", {}).get("status", "UNKNOWN")
            if status not in ("IN_PROGRESS", "PENDING"):
                break
        elif not started:
            authorize("Start the missing basic vulnerability scan for this already verified image.")
            note("No scan exists yet; requesting one basic scan for the verified digest…")
            CLOUD_WRITE_ATTEMPTED = True
            started = True
            result = command(
                aws_args(
                    "ecr",
                    "start-image-scan",
                    "--registry-id",
                    ACCOUNT,
                    "--repository-name",
                    REPO,
                    "--image-id",
                    "imageDigest=" + digest,
                )
            )
            if result.returncode:
                if "(LimitExceededException)" not in (result.stderr or ""):
                    fail((result.stderr or "Unable to start the image scan.").strip())
                note(
                    "AWS scan limit reported; checking for an existing scan witho"
                    "ut another start request."
                )
            else:
                verify_scan_identity(json.loads(result.stdout), digest)
        if attempt + 1 < SCAN_ATTEMPTS:
            note("Waiting for scan results (10 seconds)…")
            time.sleep(SCAN_INTERVAL_SECONDS)
    if scan is None:
        fail(
            "Upload verified, but no scan report is available yet. Rerun "
            "this script later; the image will not be uploaded again."
        )
    status = scan.get("imageScanStatus", {}).get("status", "UNKNOWN")
    if scan.get("nextToken") or scan.get("NextToken"):
        fail("Scan findings are truncated. A complete scan report is required for review.")
    destination = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(destination, exist_ok=True)
    # A unique file avoids overwriting previous scan evidence.
    fd, path = tempfile.mkstemp(
        prefix="Fitfinity_ECR_Admin_Scan_" + digest[7:19] + "_", suffix=".json", dir=destination
    )
    with os.fdopen(fd, "w") as output:
        json.dump(scan, output, indent=2)
        output.write("\n")
    print("SCAN_STATUS=" + status)
    print(
        "SCAN_COUNTS="
        + json.dumps(scan.get("imageScanFindings", {}).get("findingSeverityCounts", {}))
    )
    print("SCAN_REPORT=" + path)
    if status != "COMPLETE":
        fail(
            "Scan status is "
            + status
            + (
                "; upload remains verified. Keep the report for review; no se"
                "curity acceptance is implied."
            )
        )
    else:
        note(
            "Send the saved JSON report for vulnerability review. COMPLET"
            "E means the scan finished, not security acceptance."
        )


def main():
    global CLOUD_WRITE_ATTEMPTED, UPLOAD_VERIFIED
    if len(sys.argv) != 1:
        fail("Run this script without arguments.")
    for name in ("aws", "docker"):
        if not shutil.which(name):
            fail(name + " is required.")
    # Refuse credential/endpoint overrides instead of silently targeting another account/service.
    for name in os.environ:
        if (
            name
            in (
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
                "AWS_SECURITY_TOKEN",
                "AWS_WEB_IDENTITY_TOKEN_FILE",
                "AWS_ROLE_ARN",
            )
            or name.startswith("AWS_ENDPOINT_URL")
        ) and os.environ[name]:
            fail("Unset " + name + " before using the named test profile.")
    note("Fitfinity AWS Admin image — upload and scan preflight")
    identity = aws("sts", "get-caller-identity")
    account = identity.get("Account", "")
    if account != ACCOUNT:
        fail("Expected AWS test account " + ACCOUNT + ". No cloud writes were made.")
    if identity.get("Arn") != f"arn:aws:iam::{account}:user/fitfinity-deployer":
        fail(
            "Expected the fitfinity-deployer IAM user. Sign in with aws l"
            "ogin --profile fitfinity-test."
        )
    image = json.loads(checked(["docker", "image", "inspect", IMAGE]))[0]
    # This Docker Desktop receipt exposes the accepted manifest digest as .Id.
    local_image_id = image.get("Id")
    if local_image_id != EXPECTED_MANIFEST:
        fail(
            "Local image differs from the successful build receipt. Stop "
            "and report the new image ID."
        )
    if image.get("Created") != EXPECTED_CREATED:
        fail("Local image creation time differs from the supplied Admin build receipt.")
    if (image.get("Os"), image.get("Architecture")) != ("linux", "amd64"):
        fail("Expected the linux/amd64 runtime image.")
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        fail(
            "Unset DOCKER_HOST and DOCKER_CONTEXT; select Docker Desktop "
            "with docker context use desktop-linux."
        )
    context = checked(["docker", "context", "show"]).strip()
    endpoint = checked(
        ["docker", "context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}"]
    ).strip()
    if not endpoint.startswith("unix://"):
        fail("Expected a local Docker Desktop Unix socket; remote engines are not supported.")
    registry = f"{account}.dkr.ecr.{REGION}.amazonaws.com"
    uri = registry + "/" + REPO
    tag = "manifest-" + EXPECTED_MANIFEST.split(":")[1]
    full_tag = uri + ":" + tag
    existing = maybe(
        "ecr", "describe-repositories", "RepositoryNotFoundException", "--repository-names", REPO
    )
    if not existing:
        fail(
            "The previously created test repository is missing. No reposi"
            "tory will be created by this step."
        )
    verify_repository(existing["repositories"][0], account)
    scanning = aws("ecr", "get-registry-scanning-configuration")
    if (
        scanning.get("registryId") != ACCOUNT
        or scanning.get("scanningConfiguration", {}).get("scanType") != "BASIC"
    ):
        fail(
            "Expected basic ECR scanning in the test account. Registry sc"
            "anning settings will not be changed."
        )
    if remote_image(tag):
        digest = verify_remote(tag)
        UPLOAD_VERIFIED = True
        print(GREEN + "ALREADY UPLOADED — verified image manifest." + RESET)
        print("IMAGE_URI=" + uri + "@" + digest)
        save_scan(digest)
        return
    authorize(
        "Upload the accepted Admin runtime image to the verified repo"
        "sitory and retrieve its basic scan; start the scan if absent"
        "."
    )
    note("Authenticating Docker with a temporary configuration…")
    with tempfile.TemporaryDirectory(prefix="fitfinity-ecr-") as temp:
        environment = dict(os.environ, DOCKER_CONFIG=temp)
        # Docker Desktop's selected engine remains in the original Docker config.
        # Only login/push use the isolated config; image tagging uses the original context.
        password = checked(
            [
                "aws",
                "ecr",
                "get-login-password",
                "--profile",
                PROFILE,
                "--region",
                REGION,
                "--no-cli-pager",
                "--no-cli-auto-prompt",
            ]
        )
        checked(
            [
                "docker",
                "--config",
                temp,
                "login",
                "--username",
                "AWS",
                "--password-stdin",
                registry,
            ],
            input_data=password,
            env=environment,
        )
        del password
        checked(["docker", "tag", local_image_id, full_tag], capture=False)
        # Pin the existing engine explicitly because the temporary config has no context.
        note("Uploading image layers…")
        CLOUD_WRITE_ATTEMPTED = True
        checked(
            ["docker", "--config", temp, "--host", endpoint, "push", full_tag],
            capture=False,
            env=environment,
        )
    digest = verify_remote(tag)
    UPLOAD_VERIFIED = True
    print(GREEN + "UPLOAD PASSED — remote image manifest verified." + RESET)
    print("IMAGE_URI=" + uri + "@" + digest)
    print("Image publication only. App deployment and vulnerability review remain pending.")
    save_scan(digest)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, IndexError) as error:
        print("STOPPED: " + str(error), file=sys.stderr)
        if UPLOAD_VERIFIED:
            print(
                (
                    "Image publication is verified. Vulnerability acceptance and "
                    "app deployment remain pending."
                ),
                file=sys.stderr,
            )
        print(
            (
                "An image upload or scan was attempted. Existing resources an"
                "d uploaded images are preserved."
            )
            if CLOUD_WRITE_ATTEMPTED
            else "Stopped before any cloud writes. This run created no resources or uploads.",
            file=sys.stderr,
        )
        sys.exit(1)
