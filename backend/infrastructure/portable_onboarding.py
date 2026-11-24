"""Export first-install CloudFormation templates for review without AWS credentials."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import portable_foundation
import portable_hosting
import portable_services
from deployment_profile import fingerprint, unique_json, validate
from operator_checks import require


def templates(phase, profile, inputs):
    """Use the existing target-aware factories for the selected stage of onboarding."""
    require(isinstance(inputs, dict), "Expected a JSON object with public configuration")
    if phase == "foundation":
        require(
            set(inputs) == {"foundation", "session_hours", "staff_portal_url", "browser_origin"}
            and isinstance(inputs["foundation"], dict)
            and isinstance(inputs["staff_portal_url"], str)
            and isinstance(inputs["browser_origin"], str),
            "Expected foundation, session_hours, staff_portal_url and browser_origin",
        )
        # Portable hosting uses the staff application's eight-hour session lifetime.
        require(
            inputs["session_hours"] == 8,
            "Use session_hours 8 to match the current staff runtime",
        )
        foundation = portable_foundation.prepare(profile, inputs["foundation"])
        return {
            "foundation.json": foundation["template"],
            "identity.json": portable_services.identity(
                profile,
                session_hours=inputs["session_hours"],
                staff_portal_url=inputs["staff_portal_url"],
            ),
            "storage.json": portable_services.storage(
                profile, browser_origin=inputs["browser_origin"]
            ),
            "image-access.json": portable_services.image_access(profile),
            "maintenance-access.json": portable_services.maintenance_access(profile),
            "edge.json": portable_hosting.edge(profile),
        }
    require(
        phase == "hosting" and set(inputs) == {"hosting", "frontend_prefix", "edge_arn"},
        "Expected hosting, frontend_prefix and edge_arn",
    )
    return {
        "hosting.json": portable_hosting.prepare(
            profile,
            inputs["hosting"],
            frontend_prefix=inputs["frontend_prefix"],
            edge_arn=inputs["edge_arn"],
        )
    }


def encoded(value):
    """Serialize templates and the receipt reproducibly for byte-level review."""
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def export(phase, profile_path, inputs_path, output):
    """Validate all inputs and atomically publish one new private review archive."""
    profile_bytes = profile_path.read_bytes()
    inputs_bytes = inputs_path.read_bytes()
    profile = validate(unique_json(profile_bytes))
    rendered = templates(phase, profile, unique_json(inputs_bytes))
    files = {name: encoded(document) for name, document in rendered.items()}
    receipt = {
        "purpose": "first-install-template-review",
        "phase": phase,
        "profile_sha256": fingerprint(profile),
        "input_file_sha256": {
            "profile": hashlib.sha256(profile_bytes).hexdigest(),
            "inputs": hashlib.sha256(inputs_bytes).hexdigest(),
        },
        "template_file_sha256": {
            name: hashlib.sha256(content).hexdigest() for name, content in files.items()
        },
    }
    files["receipt.json"] = encoded(receipt)
    # The hard link publishes a completed archive and refuses even an existing empty file.
    with tempfile.NamedTemporaryFile(dir=output.parent) as staged:
        with ZipFile(staged, "w") as archive:
            for name, content in sorted(files.items()):
                archive.writestr(ZipInfo(name), content, compress_type=ZIP_DEFLATED)
        staged.flush()
        os.link(staged.name, output)


def main(argv=None):
    """Read metadata files and write the requested review package."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("foundation", "hosting"))
    parser.add_argument("--profile", type=Path, required=True, help="target identity JSON file")
    parser.add_argument("--inputs", type=Path, required=True, help="phase-specific metadata JSON")
    parser.add_argument("--output", type=Path, required=True, help="new review ZIP file")
    args = parser.parse_args(argv)
    try:
        export(args.phase, args.profile, args.inputs, args.output)
    except FileExistsError:
        parser.exit(1, "Review output already exists. Choose a new file.\n")
    except RuntimeError as error:
        parser.exit(1, f"{error}\n")
    except (KeyError, TypeError, ValueError):
        parser.exit(1, "Invalid profile or inputs. Check the metadata field names and types.\n")
    except OSError:
        parser.exit(1, "Check the input files and the writable output directory.\n")


if __name__ == "__main__":
    main()
