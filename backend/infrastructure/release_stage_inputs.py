"""Build child inputs from reviewed target configuration and authenticated stage receipts."""

import hashlib
import json
import re
import uuid
from pathlib import Path

from deployment_profile import fingerprint, identities
from hosting_frontend import manifest_hash
from operator_checks import require
from release_execution import template
from release_observation import digest
from release_plan import prepare as prepare_rollout
from release_readiness import migration_chain
from rollout_provider import aws


def document(record, stage, name):
    """Read a receipt from a completed authenticated stage."""
    return record["stages"][stage]["evidence"]["documents"][name]


def producer(record, stage):
    """Return an exact authenticated producer ID without selecting arbitrary latest runs."""
    value = record["stages"][stage]["evidence"]["run_id"]
    require(type(value) is int and value > 0, "Exact producer run required")
    return str(value)


def inputs(record, stage):
    """Recover original child inputs retained alongside completed stage evidence."""
    return record["stages"][stage]["evidence"]["dispatch_inputs"]


def plan(stage, record, configuration, profile, *, now, new_id=lambda: uuid.uuid4().hex):
    """Prepare operational inputs without AWS calls or implicit adoption of an existing pause."""
    target = configuration["target"]
    require(
        isinstance(target, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", target),
        "Exact configured target name required",
    )
    require(
        configuration.get("profile_sha256") == fingerprint(profile)
        and record["identity"]["profile_sha256"] == fingerprint(profile),
        "Stage configuration target differs",
    )
    source = record["identity"]["source_sha"]
    result = {"target": target}
    if stage == "image":
        result.update(
            source_sha=source, verification_run=str(record["verification"]["verification_run"])
        )
    elif stage == "observation":
        pass
    elif stage == "prepare":
        image = document(record, "image", "fitfinity-image-candidate.json")
        observed = document(record, "observation", "release-observation.json")
        capacity = observed["runtime"]["reserved_concurrency"]
        require(
            type(capacity) is int and capacity > 0,
            "Paused release requires authenticated continuation; do not repeat backup",
        )
        probe = {
            **configuration["probe"],
            "account": profile["account"],
            "region": profile["region"],
            "source_sha": source,
            "image_digest": image["image_digest"],
            "sql_sha256": hashlib.sha256(
                Path(__file__).with_name("read-schema.sql").read_bytes()
            ).hexdigest(),
            "expires_at": int(now) + 3600,
        }
        maintenance = {
            "source_sha": source,
            "profile_sha256": fingerprint(profile),
            "operation_id": new_id(),
            "expires_at": int(now) + 3600,
            "function_revision": observed["runtime"]["revision_id"],
            "database_resource_id": observed["database"]["DbiResourceId"],
            "previous_concurrency": capacity,
            "hosting_stack_arn": observed["stack"]["id"],
            "hosting_template_sha256": observed["stack"]["template_sha256"],
        }
        result.update(
            probe_bindings=json.dumps(probe), maintenance_bindings=json.dumps(maintenance)
        )
    elif stage in {
        "probe_create",
        "catalog",
        "post_upgrade_catalog",
        "cleanup_probe",
        "cleanup_probe_check",
    }:
        review = document(record, "prepare", "schema-probe-review/review.json")
        mode = {
            "probe_create": "create",
            "catalog": "collect",
            "post_upgrade_catalog": "collect",
            "cleanup_probe": "cleanup",
            "cleanup_probe_check": "cleanup-check",
        }[stage]
        result.update(
            mode=mode,
            review_run=producer(record, "prepare"),
            template_sha256=review["template_sha256"],
        )
        if stage == "probe_create":
            result["operation_id"] = new_id()
        else:
            result["operation_id"] = inputs(record, "probe_create")["operation_id"]
            result["stack_id"] = document(record, "probe_create", "schema-probe-receipt.json")[
                "stack_id"
            ]
        if not mode.startswith("cleanup"):
            result["image_run"] = producer(record, "image")
    elif stage == "backup":
        result.update(mode="backup", review_run=producer(record, "prepare"))
    elif stage == "upgrade_prepare":
        catalog = document(record, "catalog", "schema-probe-receipt.json")["receipt"]["catalog"]
        revisions = catalog["alembic_revisions"]
        require(
            isinstance(revisions, list) and len(revisions) == 1,
            "Single observed schema revision required",
        )
        head = migration_chain(Path(__file__).parents[1] / "migrations/versions")[-1]["revision"]
        require(
            revisions[0] != head, "Schema already current; a verified no-upgrade route is required"
        )
        probe = document(record, "prepare", "schema-probe-review/review.json")["bindings"]
        binding = {key: value for key, value in probe.items() if key != "sql_sha256"}
        binding.update(
            operation_id=new_id(),
            from_revision=revisions[0],
            to_revision=head,
            expires_at=int(now) + 3600,
        )
        result["upgrade_bindings"] = json.dumps(binding)
    elif stage in {
        "upgrade_create",
        "upgrade_inspect",
        "upgrade",
        "cleanup_upgrade",
        "cleanup_upgrade_check",
    }:
        review = document(record, "upgrade_prepare", "schema-upgrade-review/review.json")
        mode = {
            "upgrade_create": "create",
            "upgrade_inspect": "inspect",
            "upgrade": "invoke",
            "cleanup_upgrade": "cleanup",
            "cleanup_upgrade_check": "cleanup-check",
        }[stage]
        result.update(
            mode=mode,
            review_run=producer(record, "upgrade_prepare"),
            template_sha256=review["template_sha256"],
        )
        if not mode.startswith("cleanup"):
            result["image_run"] = producer(record, "image")
        if stage != "upgrade_create":
            prior = {
                "upgrade_inspect": "upgrade_create",
                "upgrade": "upgrade_inspect",
                "cleanup_upgrade": "upgrade",
                "cleanup_upgrade_check": "cleanup_upgrade",
            }[stage]
            result.update(
                prior_run=producer(record, prior),
                stack_id=document(record, "upgrade_create", "schema-upgrade-receipt.json")[
                    "stack_id"
                ],
            )
        if stage == "upgrade":
            backup = document(record, "backup", "maintenance-receipt.json")
            result.update(
                catalog_run=producer(record, "catalog"),
                maintenance_run=producer(record, "backup"),
                snapshot_arn=backup["snapshot_arn"],
            )
    elif stage == "rollout":
        observed = document(record, "observation", "release-observation.json")
        stack = observed["stack"]["id"]
        installed = template(
            lambda service, operation, values: aws(
                service, operation, values, profile=profile, read_only=True
            ),
            stack,
        )
        image = document(record, "image", "fitfinity-image-candidate.json")
        ready = document(record, "prepare", "release-readiness.json")
        proposed = prepare_rollout(
            installed,
            observed_template_sha256=digest(installed),
            source_sha=source,
            image_digest=image["image_digest"],
            frontend_sha256=manifest_hash(ready["frontend_manifest"]),
            profile=profile,
        )
        backup = document(record, "backup", "maintenance-receipt.json")["identity"]
        review = {
            "source_sha": source,
            "profile_sha256": fingerprint(profile),
            "operation_id": new_id(),
            "expires_at": int(now) + 3600,
            "stack_arn": stack,
            "original_template_sha256": digest(installed),
            "candidate_template_sha256": digest(proposed["candidate_template"]),
            "maintenance_marker": ":".join(
                backup[key] for key in ("operation_id", "source_sha", "profile_sha256")
            ),
        }
        runs = {
            "frontend": producer(record, "prepare"),
            "image": producer(record, "image"),
            "catalog": producer(record, "post_upgrade_catalog"),
        }
        if record["stages"]["upgrade"]["outcome"] == "complete":
            runs["upgrade"] = producer(record, "upgrade")
        result.update(
            mode="deploy",
            review_json=json.dumps(review),
            review_sha256=digest(review),
            producer_runs_json=json.dumps(runs),
            verification_run=str(record["verification"]["verification_run"]),
        )
    elif stage == "resume":
        review = json.loads(inputs(record, "rollout")["review_json"])
        review["resumption"] = {
            "operation_id": new_id(),
            "expires_at": int(now) + 3600,
            "concurrency": document(record, "observation", "release-observation.json")["runtime"][
                "reserved_concurrency"
            ],
            "verified_run": producer(record, "rollout"),
        }
        result.update(
            mode="resume",
            review_json=json.dumps(review),
            review_sha256=digest(review),
            producer_runs_json=inputs(record, "rollout")["producer_runs_json"],
            verification_run=str(record["verification"]["verification_run"]),
        )
    else:
        raise RuntimeError("Unknown release stage; no dispatch authorized")
    require(
        all(isinstance(value, str) for value in result.values()), "String workflow inputs required"
    )
    return {"inputs": result}


def worker_readiness(stage, record, profile):
    """Poll reads before invoking a new worker or confirming a submitted deletion."""
    owner = {
        "catalog": "probe_create",
        "upgrade_inspect": "upgrade_create",
        "cleanup_probe_check": "probe_create",
        "cleanup_upgrade_check": "upgrade_create",
    }.get(stage)
    if owner is None:
        return None
    name = "schema-probe-receipt.json" if owner == "probe_create" else "schema-upgrade-receipt.json"
    stack = document(record, owner, name)["stack_id"]
    target = identities(profile)
    worker = target["probe_name"] if owner == "probe_create" else target["upgrade_name"]
    prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/{worker}/"
    require(stack.startswith(prefix), "Worker readiness stack belongs to another target")
    rows = aws(
        "cloudformation", "describe-stacks", {"StackName": stack}, profile=profile, read_only=True
    )["Stacks"]
    require(len(rows) == 1 and rows[0].get("StackId") == stack, "Worker readiness identity differs")
    status = rows[0].get("StackStatus")
    if stage.startswith("cleanup"):
        require(
            status in {"DELETE_IN_PROGRESS", "DELETE_COMPLETE"},
            "Worker deletion failed; inspect original cleanup receipt",
        )
        return None if status == "DELETE_COMPLETE" else "Worker deletion is still in progress"
    require(
        status in {"CREATE_IN_PROGRESS", "CREATE_COMPLETE"},
        "Worker creation failed; inspect original creation receipt",
    )
    if status != "CREATE_COMPLETE":
        return "Worker creation is still in progress"
    return None
