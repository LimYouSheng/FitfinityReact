"""Bind Buildx output metadata to a local image across Docker image stores."""

import argparse
import json
import re
from pathlib import Path

from operator_checks import require

MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}


def valid_digest(value):
    """Require a complete SHA256 content identity."""
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def build_identity(metadata, row):
    """Require config identity or a described single-image manifest, without guessing."""
    output = metadata.get("containerimage.digest")
    config = metadata.get("containerimage.config.digest")
    require(valid_digest(output), "Build output digest missing or malformed")
    require(
        "containerimage.config.digest" not in metadata or valid_digest(config),
        "Build config digest malformed",
    )
    descriptor = metadata.get("containerimage.descriptor")
    result = {"build_output_digest": output}
    if descriptor is not None:
        require(
            isinstance(descriptor, dict)
            and descriptor.get("digest") == output
            and descriptor.get("mediaType") in MANIFEST_TYPES,
            "Build descriptor must identify the exact single-image manifest",
        )
        result["build_manifest_digest"] = output
    require(
        config is not None or "build_manifest_digest" in result,
        "Build metadata must identify configuration or an exact manifest",
    )
    require(
        row.get("Id") in {output, config} and valid_digest(row.get("Id")),
        "Local image identity differs from build metadata",
    )
    if config is not None:
        result["config_digest"] = config
    return result


def main():
    """Exercise the publication identity guard without AWS credentials or publication."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--inspect", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.inspect.read_text())
    require(len(rows) == 1, "Expected one inspected image")
    print(json.dumps(build_identity(json.loads(args.metadata.read_text()), rows[0]), indent=2))


if __name__ == "__main__":
    main()
