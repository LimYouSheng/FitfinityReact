"""Exercise original-operation recovery and ownership guards without cloud access."""

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

import hosting_design
from deployment_profile import DEVELOPER, identities
from release_execution import execute
from release_observation import digest
from release_plan import prepare


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.profile = DEVELOPER
        target = identities(self.profile)
        self.target = target
        self.caller = {
            "Account": "418638389566",
            "Arn": "arn:aws:sts::418638389566:assumed-role/fitfinity-test-github-hosting/test",
        }
        original = hosting_design.app_template(
            "releases/" + "a" * 40 + "/" + "b" * 64,
            "arn:aws:wafv2:us-east-1:418638389566:global/webacl/fitfinity-test-login-cloudfront/"
            + "c" * 36,
        )
        original["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 0
        candidate = prepare(
            original,
            observed_template_sha256=digest(original),
            source_sha="c" * 40,
            image_digest="sha256:" + "d" * 64,
            frontend_sha256="e" * 64,
        )["candidate_template"]
        self.review = {
            "profile_sha256": target["profile_sha256"],
            "source_sha": "c" * 40,
            "operation_id": "d" * 32,
            "expires_at": 2000,
            "stack_arn": (
                "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-login/abcd"
            ),
            "original_template": original,
            "candidate_template": candidate,
            "mode": "rollout",
            "boundary_resource": None,
            "maintenance_marker": "a" * 32 + ":" + "c" * 40 + ":" + target["profile_sha256"],
        }
        self.stack = {
            "StackId": self.review["stack_arn"],
            "StackName": target["hosting_stack"],
            "StackStatus": "UPDATE_COMPLETE",
            "Parameters": [{"ParameterKey": "RetainedSetting", "ParameterValue": "never-copy"}],
        }
        self.current_template = deepcopy(original)
        self.concurrency = 0
        self.calls = []
        self.receipts = []
        self.change_set = None
        self.uncertain = None
        self.function = {
            "Configuration": {
                "State": "Active",
                "LastUpdateStatus": "Successful",
                "FunctionArn": (
                    "arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-staff-api"
                ),
                "Role": "arn:aws:iam::418638389566:role/fitfinity-test-hosting-api",
            },
            "Tags": {"FitfinityMaintenance": self.review["maintenance_marker"]},
        }
        self.resources = {
            "StackResourceSummaries": [
                {
                    "LogicalResourceId": "ApiFunction",
                    "ResourceType": "AWS::Lambda::Function",
                    "PhysicalResourceId": target["runtime_function"],
                },
                {
                    "LogicalResourceId": "ApiRole",
                    "ResourceType": "AWS::IAM::Role",
                    "PhysicalResourceId": "fitfinity-test-hosting-api",
                },
            ]
        }

    def call(self, service, operation, arguments):
        self.calls.append((service, operation, deepcopy(arguments)))
        if "RuntimeBoundary" in self.current_template["Resources"]:
            result = self.feature_iam(service, operation, arguments)
            if result is not None:
                return result
        if operation == "get-caller-identity":
            result = deepcopy(self.caller)
            if self.review["mode"] == "pause":
                result["Arn"] = result["Arn"].replace("-github-hosting/", "-github-maintenance/")
            return result
        if operation == "describe-stacks":
            return {"Stacks": [deepcopy(self.stack)]}
        if operation == "get-function":
            return deepcopy(self.function)
        if operation == "get-role":
            return {
                "Role": {
                    "PermissionsBoundary": {
                        "PermissionsBoundaryArn": f"arn:aws:iam::{self.profile['account']}:policy/"
                        + self.profile["resource_prefix"]
                        + "-hosting-api-boundary"
                    }
                }
            }
        if operation == "list-entities-for-policy":
            return {"PolicyRoles": [{"RoleName": self.profile["resource_prefix"] + "-hosting-api"}]}
        if operation == "get-function-concurrency":
            return {"ReservedConcurrentExecutions": self.concurrency}
        if operation == "list-stack-resources":
            return deepcopy(self.resources)
        if operation == "get-template":
            value = (
                self.review["candidate_template"]
                if arguments.get("ChangeSetName")
                else self.current_template
            )
            return {"TemplateBody": json.dumps(value)}
        if operation == "create-change-set":
            self.assertEqual(self.receipts[-1]["state"], "create_submitted")
            self.assertEqual(
                arguments["Parameters"],
                [{"ParameterKey": "RetainedSetting", "UsePreviousValue": True}],
            )
            self.assertNotIn("never-copy", json.dumps(arguments))
            self.assertEqual(
                json.loads(arguments["TemplateBody"]), self.review["candidate_template"]
            )
            self.change_set = {
                "ChangeSetId": (
                    f"arn:aws:cloudformation:{self.profile['region']}:{self.profile['account']}:changeSet/"
                    + arguments["ChangeSetName"]
                    + "/abcd"
                ),
                "ChangeSetName": arguments["ChangeSetName"],
                "Description": arguments["Description"],
                "StackId": self.review["stack_arn"],
                "Status": "CREATE_COMPLETE",
                "ExecutionStatus": "AVAILABLE",
                "Changes": self.changes(),
            }
            if self.uncertain == operation:
                raise TimeoutError("synthetic lost create reply")
            return {"Id": self.change_set["ChangeSetId"], "StackId": self.review["stack_arn"]}
        if operation == "describe-change-set":
            return deepcopy(self.change_set)
        if operation == "execute-change-set":
            self.assertEqual(self.receipts[-1]["state"], "execute_submitted")
            self.assertTrue(self.receipts[-1]["execution_requested"])
            self.change_set["ExecutionStatus"] = "EXECUTE_COMPLETE"
            self.current_template = deepcopy(self.review["candidate_template"])
            if self.review["mode"] == "resume":
                self.concurrency = 2
            if self.uncertain == operation:
                raise TimeoutError("synthetic lost execute reply")
            return {}
        raise AssertionError((service, operation))

    def feature_iam(self, service, operation, args):
        """Report effective permissions from the independently deployed synthetic resources."""
        name = self.target["resource_prefix"] + "-hosting-api"
        arn = f"arn:aws:iam::{self.target['account']}:policy/{name}-boundary"
        resources = self.current_template["Resources"]
        role = resources["ApiRole"]["Properties"]
        policy = role["Policies"][0]
        if (
            operation == "describe-stack-resource"
            and args["LogicalResourceId"] == "RuntimeBoundary"
        ):
            return {
                "StackResourceDetail": {
                    "StackId": self.stack["StackId"],
                    "LogicalResourceId": "RuntimeBoundary",
                    "ResourceType": "AWS::IAM::ManagedPolicy",
                    "PhysicalResourceId": arn,
                    "ResourceStatus": "CREATE_COMPLETE",
                }
            }
        if service != "iam":
            return None
        return {
            "get-role": {
                "Role": {
                    "Arn": f"arn:aws:iam::{self.target['account']}:role/{name}",
                    "RoleName": name,
                    "Path": "/",
                    "AssumeRolePolicyDocument": deepcopy(role["AssumeRolePolicyDocument"]),
                    "PermissionsBoundary": {"PermissionsBoundaryArn": arn},
                }
            },
            "list-role-policies": {"PolicyNames": [policy["PolicyName"]]},
            "list-attached-role-policies": {"AttachedPolicies": []},
            "get-role-policy": {"RoleName": name, **deepcopy(policy)},
            "get-policy": {
                "Policy": {
                    "Arn": arn,
                    "DefaultVersionId": "v1",
                    "AttachmentCount": 0,
                    "PermissionsBoundaryUsageCount": 1,
                }
            },
            "get-policy-version": {
                "PolicyVersion": {
                    "VersionId": "v1",
                    "IsDefaultVersion": True,
                    "Document": deepcopy(
                        resources["RuntimeBoundary"]["Properties"]["PolicyDocument"]
                    ),
                }
            },
            "list-entities-for-policy": {"PolicyRoles": [{"RoleName": name}]},
        }.get(operation)

    def changes(self):
        if self.review["mode"] in {"pause", "resume"}:
            rows = [("ApiFunction", "AWS::Lambda::Function", ["ReservedConcurrentExecutions"])]
        else:
            rows = [
                ("ApiFunction", "AWS::Lambda::Function", ["Code"]),
                ("ApiAlias", "AWS::Lambda::Alias", ["FunctionVersion"]),
                ("Distribution", "AWS::CloudFront::Distribution", ["DistributionConfig"]),
            ]
        if (
            self.review["mode"] == "rollout"
            and self.review["boundary_resource"] == "RuntimeBoundary"
        ):
            rows[0][2].append("Environment")
            rows.extend(
                [
                    ("ApiRole", "AWS::IAM::Role", ["Policies"]),
                    ("RuntimeBoundary", "AWS::IAM::ManagedPolicy", ["PolicyDocument"]),
                ]
            )
        result = [
            {
                "Type": "Resource",
                "ResourceChange": {
                    "Action": "Modify",
                    "LogicalResourceId": name,
                    "ResourceType": kind,
                    "Replacement": "False",
                    "Scope": ["Properties"],
                    "Details": [
                        {
                            "Target": {
                                "Attribute": "Properties",
                                "Name": prop,
                                "RequiresRecreation": "Never",
                            }
                        }
                        for prop in props
                    ],
                },
            }
            for name, kind, props in rows
        ]
        if self.review["mode"] not in {"pause", "resume"}:
            version = self.review["candidate_template"]["Resources"]["ApiAlias"]["Properties"][
                "FunctionVersion"
            ]["Fn::GetAtt"][0]
            result.append(
                {
                    "Type": "Resource",
                    "ResourceChange": {
                        "Action": "Add",
                        "LogicalResourceId": version,
                        "ResourceType": "AWS::Lambda::Version",
                    },
                }
            )
        return result

    def run_step(self, action, prior=None, **kwargs):
        return execute(
            action,
            self.review,
            self.call,
            lambda receipt: self.receipts.append(deepcopy(receipt)),
            profile=self.profile,
            prior=prior,
            now=kwargs.get("now", 1000),
        )

    def test_reviewed_update_keeps_resources_paused_and_requires_separate_steps(self):
        created = self.run_step("create")
        self.assertEqual([op for _, op, _ in self.calls if op.startswith("execute")], [])
        observed = self.run_step("inspect", created)
        self.assertFalse(observed.get("execution_requested", False))
        submitted = self.run_step("execute", observed)
        verified = self.run_step("verify", submitted)
        self.assertEqual(verified["state"], "template_verified")
        self.assertEqual(self.concurrency, 0)
        self.assertEqual(sum(op == "execute-change-set" for _, op, _ in self.calls), 1)

    def test_lost_create_reply_recovers_original_named_change_set_without_recreation(self):
        self.uncertain = "create-change-set"
        with self.assertRaises(TimeoutError):
            self.run_step("create")
        original = deepcopy(self.receipts[-1])
        observed = self.run_step("inspect", original, now=3000)
        self.assertEqual(observed["change_set_arn"], self.change_set["ChangeSetId"])
        with self.assertRaises(RuntimeError):
            self.run_step("create", observed)
        self.assertEqual(sum(op == "create-change-set" for _, op, _ in self.calls), 1)

    def test_lost_execute_reply_cannot_be_replayed_after_repeated_inspections(self):
        created = self.run_step("create")
        self.uncertain = "execute-change-set"
        with self.assertRaises(TimeoutError):
            self.run_step("execute", created)
        original = deepcopy(self.receipts[-1])
        observed = self.run_step("inspect", original, now=3000)
        again = self.run_step("inspect", observed, now=4000)
        self.assertTrue(again["execution_requested"])
        with self.assertRaises(RuntimeError):
            self.run_step("execute", again)
        self.assertEqual(self.run_step("verify", again, now=4000)["state"], "template_verified")
        self.assertEqual(sum(op == "execute-change-set" for _, op, _ in self.calls), 1)

    def test_pending_create_inspection_does_not_claim_an_execution_was_requested(self):
        created = self.run_step("create")
        self.change_set.update(Status="CREATE_IN_PROGRESS", ExecutionStatus="UNAVAILABLE")
        observed = self.run_step("inspect", created)
        self.assertFalse(observed.get("execution_requested", False))
        with self.assertRaises(RuntimeError):
            self.run_step("execute", observed)
        self.assertFalse(any(op == "execute-change-set" for _, op, _ in self.calls))

    def test_changed_template_resources_marker_or_change_set_refuse_writes(self):
        for failure in ("template", "resource", "marker", "page", "service-role", "replacement"):
            with self.subTest(failure=failure):
                self.setUp()
                created = self.run_step("create")
                if failure == "template":
                    self.current_template["Description"] = "changed"
                elif failure == "resource":
                    self.resources["StackResourceSummaries"][0]["PhysicalResourceId"] = "foreign"
                elif failure == "marker":
                    self.function["Tags"]["FitfinityMaintenance"] = "foreign"
                elif failure == "page":
                    self.resources["NextToken"] = "more"
                elif failure == "service-role":
                    self.stack["RoleARN"] = "unreviewed"
                else:
                    self.change_set["Changes"][0]["ResourceChange"]["Replacement"] = "Conditional"
                with self.assertRaises(RuntimeError):
                    self.run_step("execute", created)
                self.assertFalse(any(op == "execute-change-set" for _, op, _ in self.calls))

    def test_failed_receipt_write_prevents_cloud_mutation(self):
        def failed(_):
            raise OSError("synthetic journal failure")

        with self.assertRaises(OSError):
            execute("create", self.review, self.call, failed, profile=self.profile, now=1000)
        self.assertFalse(any(op == "create-change-set" for _, op, _ in self.calls))

    def test_resumption_with_lost_reply_remains_readable_after_traffic_reopens(self):
        paused = deepcopy(self.review["candidate_template"])
        self.review.update(
            mode="resume", original_template=paused, candidate_template=deepcopy(paused)
        )
        self.review["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ] = 2
        self.current_template = deepcopy(paused)
        created = self.run_step("create")
        self.uncertain = "execute-change-set"
        with self.assertRaises(TimeoutError):
            self.run_step("execute", created)
        observed = self.run_step("inspect", self.receipts[-1], now=3000)
        self.assertTrue(observed["execution_requested"])
        self.assertEqual(self.concurrency, 2)
        self.assertEqual(self.run_step("verify", observed, now=3000)["state"], "template_verified")

    def test_wrong_profile_expired_write_or_changed_prior_identity_are_refused(self):
        with self.assertRaises(RuntimeError):
            self.run_step("create", now=3000)
        self.assertFalse(self.calls)
        created = self.run_step("create")
        changed = deepcopy(created)
        changed["identity"]["operation_id"] = "0" * 32
        with self.assertRaises(RuntimeError):
            self.run_step("execute", changed)
        self.review["profile_sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            self.run_step("inspect", created)
        self.assertFalse(any(op == "execute-change-set" for _, op, _ in self.calls))

    def test_expiry_during_reads_prevents_first_cloud_write(self):
        with patch("release_execution.time.time", side_effect=[1000, 2001]):
            with self.assertRaises(RuntimeError):
                execute(
                    "create", self.review, self.call, self.receipts.append, profile=self.profile
                )
        self.assertFalse(self.receipts)
        self.assertFalse(any(op == "create-change-set" for _, op, _ in self.calls))

    def test_boundary_owner_and_sole_runtime_consumer_are_verified(self):
        from release_execution import live_target

        boundary = "arn:aws:iam::418638389566:policy/fitfinity-test-hosting-api-boundary"
        self.review["boundary_resource"] = "ExternalBoundary"
        self.review["mode"] = "boundary"
        self.resources = {
            "StackResourceSummaries": [
                {
                    "LogicalResourceId": "ExternalBoundary",
                    "ResourceType": "AWS::IAM::ManagedPolicy",
                    "PhysicalResourceId": boundary,
                }
            ]
        }
        consumers = {
            "IsTruncated": False,
            "PolicyRoles": [{"RoleName": "fitfinity-test-hosting-api"}],
            "PolicyUsers": [],
            "PolicyGroups": [],
        }
        role = {"Role": {"PermissionsBoundary": {"PermissionsBoundaryArn": boundary}}}

        def call(service, operation, arguments):
            if operation == "get-role":
                return role
            if operation == "list-entities-for-policy":
                self.assertEqual(arguments["PolicyUsageFilter"], "PermissionsBoundary")
                self.assertEqual(arguments["PolicyArn"], boundary)
                return consumers
            return self.call(service, operation, arguments)

        self.assertEqual(
            live_target(self.review, call, self.profile)["StackId"], self.review["stack_arn"]
        )
        for failure in ("owner", "consumer", "page", "association"):
            with self.subTest(failure=failure):
                original_resources, original_consumers, original_role = (
                    deepcopy(self.resources),
                    deepcopy(consumers),
                    deepcopy(role),
                )
                if failure == "owner":
                    self.resources["StackResourceSummaries"][0]["PhysicalResourceId"] += "foreign"
                elif failure == "consumer":
                    consumers["PolicyRoles"].append({"RoleName": "other-service"})
                elif failure == "page":
                    consumers["IsTruncated"] = True
                else:
                    role["Role"]["PermissionsBoundary"]["PermissionsBoundaryArn"] += "foreign"
                with self.assertRaises(RuntimeError):
                    live_target(self.review, call, self.profile)
                self.resources, consumers, role = (
                    original_resources,
                    original_consumers,
                    original_role,
                )

    def use_client_profile(self):
        client = {
            **DEVELOPER,
            "account": "123456789012",
            "region": "eu-west-1",
            "resource_prefix": "client-prod",
            "github_repository": "client-example/portal",
        }
        target = identities(client)
        for name in ("review", "stack", "current_template", "function", "resources", "caller"):
            encoded = json.dumps(getattr(self, name))
            for previous, following in (
                ("418638389566", "123456789012"),
                ("ap-southeast-1", "eu-west-1"),
                ("fitfinity-test", "client-prod"),
                (self.target["profile_sha256"], target["profile_sha256"]),
            ):
                encoded = encoded.replace(previous, following)
            setattr(self, name, json.loads(encoded))
        self.profile = client
        self.target = target

    def test_independent_account_region_and_prefix_execute_without_developer_calls(self):
        self.use_client_profile()
        created = self.run_step("create")
        executed = self.run_step("execute", created)
        self.assertEqual(self.run_step("verify", executed)["state"], "template_verified")
        encoded = json.dumps(self.calls)
        for forbidden in ("418638389566", "ap-southeast-1", "fitfinity-test"):
            self.assertNotIn(forbidden, encoded)
        self.assertIn("123456789012", encoded)
        self.assertIn("eu-west-1", encoded)
        self.assertIn("client-prod-staff-api", encoded)

    def test_direct_pause_is_insufficient_until_cloudformation_records_zero(self):
        self.review["original_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ] = 2
        self.current_template = deepcopy(self.review["original_template"])
        self.assertEqual(self.concurrency, 0)
        with self.assertRaisesRegex(RuntimeError, "rollback baseline"):
            self.run_step("create")
        self.assertFalse(self.receipts)
        self.assertFalse(self.calls)
        from release_access import service_role_arn

        self.stack["RoleARN"] = service_role_arn(self.profile)
        self.review["mode"] = "pause"
        self.review["candidate_template"] = deepcopy(self.current_template)
        self.review["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ] = 0
        created = self.run_step("create")
        call = next(args for _, op, args in self.calls if op == "create-change-set")
        self.assertNotIn("RoleARN", call)
        self.assertEqual(created["service_role_arn"], self.stack["RoleARN"])
        executed = self.run_step("execute", created)
        self.assertEqual(self.run_step("verify", executed)["state"], "template_verified")
        self.assertEqual(
            self.current_template["Resources"]["ApiFunction"]["Properties"][
                "ReservedConcurrentExecutions"
            ],
            0,
        )

    def test_inactive_runtime_is_valid_only_while_paused_and_successfully_updated(self):
        self.function["Configuration"]["State"] = "Inactive"
        created = self.run_step("create")
        submitted = self.run_step("execute", created)
        self.assertEqual(self.run_step("verify", submitted)["state"], "template_verified")
        self.assertEqual(self.concurrency, 0)
        self.function["Configuration"]["LastUpdateStatus"] = "Failed"
        with self.assertRaisesRegex(RuntimeError, "not stable"):
            self.run_step("verify", submitted)
        from release_execution import live_target

        resumed = deepcopy(self.review)
        resumed["mode"] = "resume"
        resumed["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ] = 2
        self.function["Configuration"]["LastUpdateStatus"] = "Successful"
        self.concurrency = 2
        with self.assertRaisesRegex(RuntimeError, "not stable"):
            live_target(resumed, self.call, self.profile, after=True)

    def test_failed_pause_rollback_is_inspectable_but_never_verified(self):
        self.review["mode"] = "pause"
        self.review["original_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ] = 2
        self.current_template = deepcopy(self.review["original_template"])
        self.review["candidate_template"] = deepcopy(self.current_template)
        self.review["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ] = 0
        created = self.run_step("create")
        submitted = self.run_step("execute", created)
        self.stack["StackStatus"] = "UPDATE_ROLLBACK_COMPLETE"
        self.concurrency = 2
        self.current_template = deepcopy(self.review["original_template"])
        result = self.run_step("inspect", submitted, now=3000)
        self.assertEqual(result["stack_status"], "UPDATE_ROLLBACK_COMPLETE")
        self.assertTrue(result["execution_requested"])
        with self.assertRaises(RuntimeError):
            self.run_step("verify", result, now=3000)
        with self.assertRaises(RuntimeError):
            self.run_step("execute", result)
        self.assertEqual(sum(op == "execute-change-set" for _, op, _ in self.calls), 1)

    def rollout_fixture(self):
        import tempfile
        from pathlib import Path

        from hosting_frontend import inventory, manifest_hash

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        for name in ("index.html", "sw.js", "manifest.webmanifest"):
            (folder / name).write_text("synthetic frontend")
        files = inventory(folder)
        manifest = manifest_hash(files)
        self.review["candidate_template"] = prepare(
            self.current_template,
            observed_template_sha256=digest(self.current_template),
            source_sha="c" * 40,
            image_digest="sha256:" + "d" * 64,
            frontend_sha256=manifest,
            profile=self.profile,
        )["candidate_template"]
        self.rollout_evidence = {
            "decision": "HOLD",
            "source_sha": "c" * 40,
            "profile_sha256": self.target["profile_sha256"],
            "image_digest": "sha256:" + "d" * 64,
            "frontend_sha256": manifest,
            "frontend_prefix": "releases/" + "c" * 40 + "/" + manifest,
            "schema_action": "unchanged",
            "producer_runs": {"frontend": "1", "image": "2", "catalog": "3"},
            "catalog_observed_at": "1970-01-01T00:16:39+00:00",
            "required_image_files": {"backend/Dockerfile": "a" * 64},
        }
        self.rollout_image = {
            "revision": "c" * 40,
            "profile_sha256": self.target["profile_sha256"],
            "account": self.target["account"],
            "region": self.target["region"],
            "image_digest": self.rollout_evidence["image_digest"],
            "image_uri": self.target["registry"]
            + "/"
            + self.target["image_repository"]
            + "@sha256:"
            + "d" * 64,
            "candidate_ready": True,
            "image_published": True,
            "scan_policy_passed": True,
            "source_files": self.rollout_evidence["required_image_files"],
        }
        self.scan_status = "COMPLETE"
        self.missing_frontend = False
        self.rollout_reads = []

        def call(service, operation, arguments):
            self.rollout_reads.append(operation)
            if operation == "describe-image-scan-findings":
                return {
                    "registryId": self.target["account"],
                    "repositoryName": self.target["image_repository"],
                    "imageId": {"imageDigest": self.rollout_evidence["image_digest"]},
                    "imageScanStatus": {"status": self.scan_status},
                    "imageScanFindings": {
                        "findingSeverityCounts": {},
                        "findings": [],
                        "imageScanCompletedAt": "1970-01-01T00:16:39+00:00",
                    },
                }
            if (
                operation == "describe-stack-resource"
                and arguments["LogicalResourceId"] == "FrontendBucket"
            ):
                return {
                    "StackResourceDetail": {
                        "StackId": self.stack["StackId"],
                        "LogicalResourceId": "FrontendBucket",
                        "ResourceType": "AWS::S3::Bucket",
                        "ResourceStatus": "CREATE_COMPLETE",
                        "PhysicalResourceId": "owned-test-site",
                    }
                }
            if operation == "head-object":
                if self.missing_frontend:
                    return None
                row = files[arguments["Key"].rsplit("/", 1)[-1]]
                return {
                    "ContentLength": row["bytes"],
                    "ChecksumSHA256": row["checksum"],
                    "ContentType": row["content_type"],
                    "CacheControl": row["cache_control"],
                    "ServerSideEncryption": "AES256",
                }
            return self.call(service, operation, arguments)

        def step(action, prior=None, now=1000):
            from release_rollout import advance

            return advance(
                action,
                self.review,
                self.rollout_evidence,
                self.rollout_image,
                folder,
                call,
                self.receipts.append,
                profile=self.profile,
                prior=prior,
                now=now,
            )

        self.rollout_call = call
        self.rollout_folder = folder
        return step

    def test_rollout_checks_actual_scan_and_frontend_before_each_change_set_write(self):
        step = self.rollout_fixture()
        created = step("create")
        result = step("execute", created)
        self.assertEqual(step("verify", result)["state"], "template_verified")
        self.assertEqual(self.rollout_reads.count("describe-image-scan-findings"), 2)
        self.assertEqual(self.rollout_reads.count("head-object"), 6)
        self.assertNotIn("put-object", self.rollout_reads)
        self.assertEqual(self.concurrency, 0)
        self.assertTrue(
            all(row["evidence_sha256"] == digest(self.rollout_evidence) for row in self.receipts)
        )

    def test_rollout_missing_frontend_or_incomplete_scan_prevents_cloudformation_write(self):
        step = self.rollout_fixture()
        self.missing_frontend = True
        with self.assertRaisesRegex(RuntimeError, "inspection never uploads"):
            step("create")
        self.missing_frontend = False
        self.scan_status = "IN_PROGRESS"
        with self.assertRaisesRegex(RuntimeError, "scan is incomplete"):
            step("create")
        self.assertFalse(self.receipts)
        self.assertFalse(any(op == "create-change-set" for _, op, _ in self.calls))
        self.assertNotIn("put-object", self.rollout_reads)

    def test_rollout_template_cannot_substitute_different_image_or_frontend(self):
        step = self.rollout_fixture()
        original = deepcopy(self.rollout_evidence)
        for field, value in (("image_digest", "sha256:" + "f" * 64), ("frontend_sha256", "f" * 64)):
            self.rollout_evidence = {**original, field: value}
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                step("create")
        self.assertFalse(self.rollout_reads)
        self.assertFalse(self.receipts)

    def test_rollout_stale_catalog_or_changed_recovery_evidence_prevents_write(self):
        step = self.rollout_fixture()
        self.rollout_evidence["catalog_observed_at"] = "1969-12-31T00:00:00+00:00"
        with self.assertRaisesRegex(RuntimeError, "Fresh catalog"):
            step("create")
        self.assertFalse(self.receipts)
        self.rollout_evidence["catalog_observed_at"] = "1970-01-01T00:16:39+00:00"
        created = step("create")
        self.rollout_evidence["producer_runs"]["image"] = "4"
        with self.assertRaisesRegex(RuntimeError, "Original rollout evidence"):
            step("execute", created)
        self.assertFalse(any(op == "execute-change-set" for _, op, _ in self.calls))

    def test_rollout_uncertain_execution_can_be_inspected_without_fresh_scan_or_replay(self):
        step = self.rollout_fixture()
        created = step("create")
        self.uncertain = "execute-change-set"
        with self.assertRaises(TimeoutError):
            step("execute", created)
        self.scan_status = "FAILED"
        self.missing_frontend = True
        inspected = step("inspect", self.receipts[-1], now=100000)
        self.assertTrue(inspected["execution_requested"])
        self.assertEqual(step("verify", inspected, now=100000)["state"], "template_verified")
        self.assertEqual(self.rollout_reads.count("describe-image-scan-findings"), 2)
        self.assertEqual(sum(op == "execute-change-set" for _, op, _ in self.calls), 1)

    def test_combined_rollout_gates_use_independent_client_profile(self):
        self.use_client_profile()
        step = self.rollout_fixture()
        created = step("create")
        completed = step("execute", created)
        self.assertEqual(step("verify", completed)["state"], "template_verified")
        encoded = json.dumps(self.calls)
        for forbidden in ("418638389566", "ap-southeast-1", "fitfinity-test"):
            self.assertNotIn(forbidden, encoded)
        self.assertIn("123456789012", encoded)
        self.assertIn("eu-west-1", encoded)

    def test_actions_adapter_executes_and_recovers_without_raw_template_receipts(self):
        self.exercise_actions_adapter()

    def test_actions_adapter_recovers_feature_configuration_after_lost_execution(self):
        self.exercise_actions_adapter(feature=True)

    def exercise_actions_adapter(self, *, feature=False):
        from rollout_operator import execute_step

        self.rollout_fixture()
        feature_values = None
        if feature:
            from importlib import import_module

            from release_access import service_role_arn

            self.stack["RoleARN"] = service_role_arn(self.profile)
            original, feature_values = import_module("verify-release-features").fixture(
                self.profile
            )
            original["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 0
            self.current_template = deepcopy(original)
            self.review["original_template"] = original
            self.review["boundary_resource"] = "RuntimeBoundary"
            self.review["candidate_template"] = prepare(
                original,
                observed_template_sha256=digest(original),
                source_sha="c" * 40,
                image_digest=self.rollout_evidence["image_digest"],
                frontend_sha256=self.rollout_evidence["frontend_sha256"],
                profile=self.profile,
                feature_values=feature_values,
            )["candidate_template"]
            self.resources["StackResourceSummaries"].append(
                {
                    "LogicalResourceId": "RuntimeBoundary",
                    "ResourceType": "AWS::IAM::ManagedPolicy",
                    "PhysicalResourceId": f"arn:aws:iam::{self.profile['account']}:policy/"
                    + self.profile["resource_prefix"]
                    + "-hosting-api-boundary",
                }
            )
        root = self.rollout_folder
        folder = root / "frontend/release-frontend/dist-api-test"
        folder.mkdir(parents=True)
        for name in ("index.html", "sw.js", "manifest.webmanifest"):
            (root / name).rename(folder / name)
        (root / "image").mkdir()
        (root / "image/fitfinity-image-candidate.json").write_text(json.dumps(self.rollout_image))
        review = {
            key: value
            for key, value in self.review.items()
            if key not in {"original_template", "candidate_template", "mode", "boundary_resource"}
        }
        review.update(
            original_template_sha256=digest(self.review["original_template"]),
            candidate_template_sha256=digest(self.review["candidate_template"]),
        )

        if feature:
            review["feature_values"] = feature_values

        def run(mode, prior=None):
            execute_step(
                mode,
                review,
                self.rollout_evidence,
                root,
                self.rollout_call,
                self.receipts.append,
                profile=self.profile,
                prior=prior,
            )
            return self.receipts[-1]

        with patch("time.time", return_value=1000):
            created = run("create")
            with self.assertRaisesRegex(RuntimeError, "never replay"):
                run("create", created)
            self.uncertain = "execute-change-set"
            with self.assertRaises(TimeoutError):
                run("execute", created)
        submitted = self.receipts[-1]
        with patch("time.time", return_value=100000):
            inspected = run("inspect", submitted)
            verified = run("verify", inspected)
        self.assertEqual(verified["state"], "template_verified")
        self.assertTrue(verified["execution_requested"])
        encoded = json.dumps(self.receipts)
        self.assertNotIn('"Environment"', encoded)
        self.assertNotIn('"Resources"', encoded)
        self.assertEqual(
            set(verified["original_release"]),
            {"image", "version", "frontend"} | ({"features"} if feature else set()),
        )
        if feature:
            env = self.current_template["Resources"]["ApiFunction"]["Properties"]["Environment"][
                "Variables"
            ]
            for key in (
                "FITFINITY_MEDIA_ENABLED",
                "FITFINITY_STAFF_INVITATIONS_ENABLED",
                "FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED",
            ):
                self.assertEqual(env[key], "true")

    def test_reconstructed_original_template_rejects_changed_pointer(self):
        from rollout_operator import original_metadata, restore_original

        original = self.review["original_template"]
        pointers = original_metadata(original)
        restored = restore_original(self.review["candidate_template"], pointers)
        self.assertEqual(restored, original)
        pointers["frontend"] = "/foreign"
        self.assertNotEqual(
            digest(restore_original(self.review["candidate_template"], pointers)), digest(original)
        )

    def test_rollout_metadata_rejects_wrong_target_expiry_or_raw_templates(self):
        from rollout_operator import metadata

        review = {
            key: value
            for key, value in self.review.items()
            if key not in {"original_template", "candidate_template", "mode", "boundary_resource"}
        }
        review.update(
            original_template_sha256=digest(self.review["original_template"]),
            candidate_template_sha256=digest(self.review["candidate_template"]),
        )
        with patch("time.time", return_value=1000):
            self.assertEqual(metadata(review, "c" * 40, self.profile), review)
            for key, value in (
                ("profile_sha256", "f" * 64),
                ("expires_at", 500),
                ("stack_arn", "foreign"),
                ("maintenance_marker", "foreign"),
                ("original_template", {}),
            ):
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    metadata({**review, key: value}, "c" * 40, self.profile)
        with patch("time.time", return_value=100000):
            self.assertEqual(metadata(review, "c" * 40, self.profile, recovery=True), review)

    def test_retained_cloudformation_role_is_explicitly_bound_and_preserved(self):
        from release_access import service_role_arn

        self.stack["RoleARN"] = service_role_arn(self.profile)
        created = self.run_step("create")
        call = next(args for _, op, args in self.calls if op == "create-change-set")
        self.assertEqual(
            call["RoleARN"], "arn:aws:iam::418638389566:role/fitfinity-test-hosting-cloudformation"
        )
        completed = self.run_step("execute", created)
        self.assertEqual(self.run_step("verify", completed)["state"], "template_verified")
        self.assertEqual(completed["service_role_arn"], self.stack["RoleARN"])

    def test_changed_service_role_in_stack_or_change_set_prevents_execution(self):
        from release_access import service_role_arn

        self.stack["RoleARN"] = service_role_arn(self.profile)
        created = self.run_step("create")
        self.change_set["RoleARN"] = "foreign"
        with self.assertRaises(RuntimeError):
            self.run_step("execute", created)
        self.change_set.pop("RoleARN")
        self.stack.pop("RoleARN")
        with self.assertRaisesRegex(RuntimeError, "service role changed"):
            self.run_step("execute", created)
        self.assertFalse(any(op == "execute-change-set" for _, op, _ in self.calls))

    def test_resumption_plan_binds_verified_rollout_without_changing_artifacts(self):
        from release_rollout import resumption_plan

        step = self.rollout_fixture()
        receipt = step("verify", step("execute", step("create")))
        result = resumption_plan(
            self.review,
            self.rollout_evidence,
            receipt,
            profile=self.profile,
            operation_id="f" * 32,
            expires_at=2200,
            concurrency=2,
            now=1500,
        )
        self.assertEqual(result["decision"], "HOLD")
        review = result["review"]
        self.assertEqual(review["original_template"], self.review["candidate_template"])
        expected = deepcopy(review["original_template"])
        expected["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 2
        self.assertEqual(review["candidate_template"], expected)
        self.assertEqual(result["rollout_receipt_sha256"], digest(receipt))
        self.assertEqual(self.concurrency, 0)

    def test_resumption_plan_refuses_unverified_substituted_or_replayed_release(self):
        from release_rollout import resumption_plan

        step = self.rollout_fixture()
        receipt = step("verify", step("execute", step("create")))
        for error in ("state", "identity", "evidence", "operation", "concurrency", "expiry"):
            prior = deepcopy(receipt)
            kwargs = dict(
                profile=self.profile,
                operation_id="f" * 32,
                expires_at=2200,
                concurrency=2,
                now=1500,
            )
            if error == "state":
                prior["state"] = "execute_submitted"
            elif error == "identity":
                prior["identity"]["source_sha"] = "0" * 40
            elif error == "evidence":
                prior["evidence_sha256"] = "0" * 64
            elif error == "operation":
                kwargs["operation_id"] = self.review["operation_id"]
            elif error == "concurrency":
                kwargs["concurrency"] = True
            else:
                kwargs["expires_at"] = 1000
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                resumption_plan(self.review, self.rollout_evidence, prior, **kwargs)
        self.assertEqual(self.concurrency, 0)

    def test_bound_resumption_rechecks_artifacts_and_recovers_lost_execution(self):
        from release_rollout import resume, resumption_plan

        step = self.rollout_fixture()
        verified = step("verify", step("execute", step("create")))
        rollout = deepcopy(self.review)
        plan = resumption_plan(
            rollout,
            self.rollout_evidence,
            verified,
            profile=self.profile,
            operation_id="f" * 32,
            expires_at=2200,
            concurrency=2,
            now=1500,
        )
        self.review = plan["review"]
        self.change_set = None
        self.rollout_reads.clear()

        def run(action, prior=None, now=1500):
            return resume(
                action,
                plan,
                rollout,
                self.rollout_evidence,
                verified,
                self.rollout_image,
                self.rollout_folder,
                self.rollout_call,
                self.receipts.append,
                profile=self.profile,
                prior=prior,
                now=now,
            )

        created = run("create")
        self.missing_frontend = True
        with self.assertRaises(RuntimeError):
            run("execute", created)
        self.assertEqual(self.concurrency, 0)
        self.missing_frontend = False
        self.uncertain = "execute-change-set"
        with self.assertRaises(TimeoutError):
            run("execute", created)
        submitted = deepcopy(self.receipts[-1])
        self.assertEqual(submitted["resumption_plan_sha256"], digest(plan))
        self.assertEqual(self.concurrency, 2)
        before = len(self.calls)
        observed = run("inspect", submitted, now=9000)
        self.assertEqual(run("verify", observed, now=9000)["state"], "template_verified")
        self.assertFalse(
            any(
                op in {"create-change-set", "execute-change-set"}
                for _, op, _ in self.calls[before:]
            )
        )

    def test_resumption_rejects_substituted_plan_receipt_and_stale_catalog(self):
        from release_rollout import resume, resumption_plan

        step = self.rollout_fixture()
        verified = step("verify", step("execute", step("create")))
        rollout = deepcopy(self.review)
        plan = resumption_plan(
            rollout,
            self.rollout_evidence,
            verified,
            profile=self.profile,
            operation_id="f" * 32,
            expires_at=6000,
            concurrency=2,
            now=5000,
        )
        self.review = plan["review"]

        def fresh_scan(service, operation, arguments):
            value = self.rollout_call(service, operation, arguments)
            if operation == "describe-image-scan-findings":
                value["imageScanFindings"]["imageScanCompletedAt"] = "1970-01-01T01:23:19+00:00"
            return value

        for defect in ("receipt", "template", "catalog"):
            changed = deepcopy(plan)
            if defect == "receipt":
                changed["rollout_receipt_sha256"] = "0" * 64
            elif defect == "template":
                changed["review"]["candidate_template"]["Description"] = "unreviewed"
            self.calls.clear()
            with (
                self.subTest(defect=defect),
                self.assertRaisesRegex(
                    RuntimeError, "Fresh catalog" if defect == "catalog" else ".*"
                ),
            ):
                resume(
                    "create",
                    changed,
                    rollout,
                    self.rollout_evidence,
                    verified,
                    self.rollout_image,
                    self.rollout_folder,
                    fresh_scan,
                    self.receipts.append,
                    profile=self.profile,
                    now=5000,
                )
            self.assertFalse(any(op == "create-change-set" for _, op, _ in self.calls))
        confirmation = {
            "run": "105",
            "observed_at": "1970-01-01T01:23:19+00:00",
            "evidence_sha256": digest(self.rollout_evidence),
        }

        def confirmed(value):
            return resume(
                "create",
                plan,
                rollout,
                self.rollout_evidence,
                verified,
                self.rollout_image,
                self.rollout_folder,
                fresh_scan,
                self.receipts.append,
                profile=self.profile,
                now=5000,
                confirmation=value,
            )

        for drift in (
            {"evidence_sha256": "f" * 64},
            {"run": "unbound"},
            {"observed_at": "1970-01-01T00:00:00+00:00"},
            {"observed_at": "1970-01-02T00:00:00+00:00"},
        ):
            with self.subTest(drift=drift), self.assertRaises(RuntimeError):
                confirmed({**confirmation, **drift})
        self.assertFalse(any(op == "create-change-set" for _, op, _ in self.calls))
        submitted = confirmed(confirmation)
        self.assertEqual(submitted["state"], "create_submitted")
        self.assertEqual(submitted["resumption_plan_sha256"], digest(plan))
        self.assertEqual(self.concurrency, 0)

    def test_actions_resumption_recovers_original_templates_and_lost_reply(self):
        from release_rollout import resumption_plan
        from resumption_operator import execute_step
        from rollout_operator import original_metadata

        step = self.rollout_fixture()
        original = deepcopy(self.review)
        verified = step("verify", step("execute", step("create")))
        metadata = {
            key: value
            for key, value in original.items()
            if key not in {"original_template", "candidate_template", "mode", "boundary_resource"}
        }
        metadata.update(
            original_template_sha256=digest(original["original_template"]),
            candidate_template_sha256=digest(original["candidate_template"]),
        )
        verified.update(
            review_sha256=digest(metadata),
            evidence=self.rollout_evidence,
            original_release=original_metadata(original["original_template"]),
        )
        review = {
            **metadata,
            "resumption": {
                "operation_id": "f" * 32,
                "expires_at": 2200,
                "concurrency": 2,
                "verified_run": "123",
            },
        }
        plan = resumption_plan(
            original,
            self.rollout_evidence,
            verified,
            profile=self.profile,
            operation_id="f" * 32,
            expires_at=2200,
            concurrency=2,
            now=1500,
        )
        self.review = plan["review"]
        root = self.rollout_folder
        folder = root / "frontend/release-frontend/dist-api-test"
        folder.mkdir(parents=True)
        for name in ("index.html", "sw.js", "manifest.webmanifest"):
            (root / name).rename(folder / name)
        (root / "image").mkdir()
        (root / "image/fitfinity-image-candidate.json").write_text(json.dumps(self.rollout_image))

        self.stack["Outputs"] = [
            {"OutputKey": key, "OutputValue": value}
            for key, value in (
                ("FrontendDomain", "d123.cloudfront.net"),
                ("DistributionId", "D123"),
                ("FunctionVersion", "7"),
            )
        ]
        self.function["Tags"]["Keep"] = "unrelated"
        removals = []

        def call(service, operation, arguments):
            if operation == "get-distribution":
                return {
                    "Distribution": {
                        "ARN": f"arn:aws:cloudfront::{self.target['account']}:distribution/D123",
                        "DomainName": "d123.cloudfront.net",
                        "Status": "Deployed",
                        "DistributionConfig": {
                            "Enabled": True,
                            "Origins": {
                                "Items": [
                                    {
                                        "Id": "frontend",
                                        "OriginPath": "/"
                                        + self.rollout_evidence["frontend_prefix"],
                                    }
                                ]
                            },
                        },
                    }
                }
            if operation == "get-alias":
                return {"FunctionVersion": "7"}
            if operation == "get-function" and arguments.get("Qualifier") == "7":
                return {
                    "Configuration": {"Version": "7"},
                    "Code": {
                        "ResolvedImageUri": self.target["registry"]
                        + "/"
                        + self.target["image_repository"]
                        + "@"
                        + self.rollout_evidence["image_digest"]
                    },
                }
            if operation == "untag-resource":
                self.assertTrue(self.receipts[-1]["finalization_requested"])
                removals.append(arguments)
                raise TimeoutError("lost finalization reply")
            if (
                operation == "get-template"
                and arguments.get("ChangeSetName") == "release-" + original["operation_id"]
            ):
                if self.concurrency > 0:
                    raise RuntimeError("previous change set no longer available after resume")
                return {"TemplateBody": original["candidate_template"]}
            return self.rollout_call(service, operation, arguments)

        def read(url):
            return {
                "https://d123.cloudfront.net/index.html": (folder / "index.html").read_bytes(),
                "https://d123.cloudfront.net/health/live": b'{"status":"alive"}',
                "https://d123.cloudfront.net/health/ready": b'{"status":"ready"}',
            }[url]

        def run(mode, prior=None, now=1500):
            with patch("time.time", return_value=now), patch("release_health.read_url", read):
                execute_step(
                    mode,
                    review,
                    self.rollout_evidence,
                    root,
                    call,
                    self.receipts.append,
                    profile=self.profile,
                    verified=verified,
                    prior=prior,
                )
            return self.receipts[-1]

        created = run("resume-create")
        with self.assertRaisesRegex(RuntimeError, "never replay"):
            run("resume-create", created)
        self.uncertain = "execute-change-set"
        with self.assertRaises(TimeoutError):
            run("resume-execute", created)
        submitted = deepcopy(self.receipts[-1])
        self.assertEqual(submitted["verified_rollout_sha256"], digest(verified))
        observed = run("resume-inspect", submitted, now=9000)
        self.assertEqual(run("resume-verify", observed, now=9000)["state"], "template_verified")
        self.assertEqual(self.concurrency, 2)
        # A producer rerun can return different bytes at the same artifact run ID.
        # Even a cached public page serving those same bytes cannot establish this release's health.
        index = folder / "index.html"
        reviewed_index = index.read_bytes()
        index.write_bytes(b"other attempt with matching cached public page")
        with self.assertRaisesRegex(RuntimeError, "frontend artifact"):
            run("resume-health", observed, now=1600)
        index.write_bytes(reviewed_index)
        healthy = run("resume-health", observed, now=1600)
        self.assertEqual(healthy["health"]["state"], "health_verified")
        with self.assertRaisesRegex(TimeoutError, "lost finalization reply"):
            run("resume-finalize", healthy, now=1601)
        intent = deepcopy(self.receipts[-1])
        for mode in ("resume-inspect", "resume-verify", "resume-health", "resume-finalize"):
            with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, "finalization"):
                run(mode, intent, now=1602)
        # A later health outage or expired frontend artifact must not obscure the original write.
        (folder / "index.html").unlink()
        pending = run("resume-finalize-inspect", intent, now=9000)
        self.assertEqual(pending["state"], "finalize_submitted")
        self.assertEqual(pending["health"], intent["health"])
        for key in removals[0]["TagKeys"]:
            del self.function["Tags"][key]
        finalized = run("resume-finalize-inspect", pending, now=9010)
        self.assertEqual(finalized["state"], "maintenance_finalized")
        self.assertEqual(finalized["health"]["observed_at"], 1601)
        self.assertEqual(self.function["Tags"], {"Keep": "unrelated"})
        self.assertEqual(len(removals), 1)
        self.assertNotIn('"Environment"', json.dumps(self.receipts))
        changed = deepcopy(verified)
        verified["review_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "Verified original"):
            run("resume-inspect", submitted, now=9000)
        verified.clear()
        verified.update(changed)
        submitted["verified_rollout_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "Original resumption evidence"):
            run("resume-inspect", submitted, now=9000)

    def test_actions_resumption_metadata_rejects_unreviewed_capacity_and_producer(self):
        from resumption_operator import validate

        values = {
            "operation_id": "f" * 32,
            "expires_at": 2000,
            "concurrency": 2,
            "verified_run": "123",
        }
        with patch("time.time", return_value=1000):
            self.assertEqual(validate(values), values)
            for key, value in (
                ("concurrency", True),
                ("concurrency", 0),
                ("verified_run", "../foreign"),
                ("expires_at", 999),
                ("operation_id", "foreign"),
                ("extra", 1),
            ):
                with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                    validate({**values, key: value})
        with patch("time.time", return_value=9000):
            self.assertEqual(validate(values, recovery=True), values)

        import os
        import tempfile
        from pathlib import Path

        from rollout_operator import main

        source = self.review["source_sha"]
        review = {
            key: self.review[key]
            for key in (
                "profile_sha256",
                "source_sha",
                "operation_id",
                "expires_at",
                "stack_arn",
                "maintenance_marker",
            )
        }
        review.update(
            original_template_sha256=digest(self.review["original_template"]),
            candidate_template_sha256=digest(self.review["candidate_template"]),
            resumption=values,
        )
        repository = self.profile["github_repository"]
        failed = {
            "conclusion": "failure",
            "path": ".github/workflows/aws-rollout.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "status": "completed",
            "head_repository": {"full_name": repository},
            "head_sha": source,
            "run_attempt": 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profile.json"
            profile.write_text(json.dumps(self.profile))
            context = {
                "GITHUB_SHA": source,
                "GITHUB_REPOSITORY": repository,
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "RUNNER_TEMP": directory,
                "GITHUB_WORKFLOW_REF": repository
                + "/.github/workflows/aws-rollout.yml@refs/heads/main",
                "ROLLOUT_MODE": "resume",
                "ROLLOUT_REVIEW": json.dumps(review),
                "ROLLOUT_REVIEW_SHA256": digest(review),
                "ROLLOUT_RUNS": "{}",
            }
            with (
                patch.dict(os.environ, context, clear=True),
                patch("sys.argv", ["rollout_operator.py", "fetch", "--profile", str(profile)]),
                patch("time.time", return_value=1000),
                patch("rollout_operator.source_check"),
                patch("rollout_operator.subprocess.check_output", return_value=json.dumps(failed)),
                patch("rollout_operator.subprocess.run") as download,
                self.assertRaisesRegex(RuntimeError, "Successful verified rollout"),
            ):
                main()
            download.assert_not_called()

    def finalization_fixture(self):
        from release_execution import review_identity

        paused = deepcopy(self.review["candidate_template"])
        self.review.update(
            mode="resume", original_template=paused, candidate_template=deepcopy(paused)
        )
        self.review["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ] = 2
        prior = {
            "identity": review_identity(self.review, self.profile, 1000),
            "state": "template_verified",
            "execution_requested": True,
        }
        evidence = {"synthetic": "reviewed"}
        health = {
            "state": "health_verified",
            "review_sha256": digest(self.review),
            "evidence_sha256": digest(evidence),
            "observed_at": 1000,
        }
        return prior, evidence, health

    def test_finalization_recovers_lost_tag_removal_without_replay(self):
        from release_finalize import finish

        prior, evidence, health = self.finalization_fixture()
        self.function["Tags"]["FitfinitySnapshot"] = self.review["maintenance_marker"]
        self.function["Tags"]["Keep"] = "unrelated"
        removals = []

        def call(service, operation, values):
            if operation == "untag-resource":
                self.assertEqual(self.receipts[-1]["state"], "finalize_submitted")
                removals.append(values)
                for key in values["TagKeys"]:
                    del self.function["Tags"][key]
                raise TimeoutError("lost tag removal reply")
            return self.call(service, operation, values)

        with self.assertRaises(TimeoutError):
            finish(
                "finalize",
                self.review,
                evidence,
                prior,
                health,
                call,
                self.receipts.append,
                profile=self.profile,
                now=1000,
            )
        submitted = deepcopy(self.receipts[-1])
        observed = finish(
            "inspect",
            self.review,
            evidence,
            submitted,
            health,
            call,
            self.receipts.append,
            profile=self.profile,
            now=1001,
        )
        self.assertEqual(observed["state"], "maintenance_finalized")
        self.assertEqual(self.function["Tags"], {"Keep": "unrelated"})
        self.assertEqual(len(removals), 1)
        with self.assertRaises(RuntimeError):
            finish(
                "finalize",
                self.review,
                evidence,
                submitted,
                health,
                call,
                self.receipts.append,
                profile=self.profile,
                now=1001,
            )
        self.assertEqual(len(removals), 1)

    def test_finalization_receipt_failure_prevents_tag_removal(self):
        from release_finalize import finish

        prior, evidence, health = self.finalization_fixture()
        original_tags = deepcopy(self.function["Tags"])

        def persist(receipt):
            self.assertEqual(receipt["state"], "finalize_submitted")
            self.assertTrue(receipt["finalization_requested"])
            raise OSError("receipt storage unavailable")

        with self.assertRaisesRegex(OSError, "receipt storage unavailable"):
            finish(
                "finalize",
                self.review,
                evidence,
                prior,
                health,
                self.call,
                persist,
                profile=self.profile,
                now=1000,
            )
        self.assertFalse(any(op == "untag-resource" for _, op, _ in self.calls))
        self.assertEqual(self.function["Tags"], original_tags)
        self.assertEqual(prior["state"], "template_verified")

    def test_finalization_rechecks_review_and_health_deadlines_before_untagging(self):
        from release_finalize import finish

        for stale in ("review", "health"):
            with self.subTest(stale=stale):
                self.setUp()
                if stale == "review":
                    self.review["expires_at"] = 1050
                prior, evidence, health = self.finalization_fixture()
                clock = unittest.mock.Mock(return_value=1000)

                def persist(receipt, clock=clock, expiry=1051 if stale == "review" else 1301):
                    self.receipts.append(deepcopy(receipt))
                    clock.return_value = expiry

                with patch("time.time", clock), self.assertRaises(RuntimeError):
                    finish(
                        "finalize",
                        self.review,
                        evidence,
                        prior,
                        health,
                        self.call,
                        persist,
                        profile=self.profile,
                    )
                self.assertEqual(self.receipts[-1]["state"], "finalize_submitted")
                self.assertFalse(any(op == "untag-resource" for _, op, _ in self.calls))

    def test_finalization_refuses_foreign_marker_stale_health_and_missing_intent(self):
        from release_finalize import finish

        for defect in ("marker", "health", "intent"):
            self.setUp()
            prior, evidence, health = self.finalization_fixture()
            if defect == "marker":
                self.function["Tags"]["FitfinitySnapshot"] = "foreign"
            elif defect == "health":
                health["observed_at"] = 0
            with self.subTest(defect=defect), self.assertRaises(RuntimeError):
                finish(
                    "inspect" if defect == "intent" else "finalize",
                    self.review,
                    evidence,
                    prior,
                    health,
                    self.call,
                    self.receipts.append,
                    profile=self.profile,
                    now=1000,
                )
            self.assertFalse(any(op == "untag-resource" for _, op, _ in self.calls))
            self.assertEqual(self.receipts, [])


class RolloutProviderTests(unittest.TestCase):
    def test_absent_object_is_distinct_from_denied_or_failed_calls(self):
        from types import SimpleNamespace

        from rollout_provider import aws

        for code in ("404", "AccessDenied", "500"):
            result = SimpleNamespace(
                returncode=1,
                stdout="",
                stderr=f"An error occurred ({code}) when calling the HeadObject operation: private",
            )
            with patch("rollout_provider.subprocess.run", return_value=result):
                if code == "404":
                    self.assertIsNone(aws("s3api", "head-object", {}, profile=DEVELOPER))
                else:
                    with self.assertRaisesRegex(RuntimeError, "inspect original intent"):
                        aws("s3api", "head-object", {}, profile=DEVELOPER)

    def test_upload_preserves_binary_bytes_and_disables_retries(self):
        from pathlib import Path
        from types import SimpleNamespace

        from rollout_provider import aws

        def execute(command, **kwargs):
            self.assertEqual(
                Path(command[command.index("--body") + 1]).read_bytes(), b"\x00\xffbinary"
            )
            values = json.loads(command[command.index("--cli-input-json") + 1])
            self.assertNotIn("Body", values)
            self.assertEqual(values["IfNoneMatch"], "*")
            self.assertEqual(kwargs["env"]["AWS_MAX_ATTEMPTS"], "1")
            self.assertEqual(kwargs["env"]["AWS_IGNORE_CONFIGURED_ENDPOINT_URLS"], "true")
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")

        with patch("rollout_provider.subprocess.run", side_effect=execute):
            aws(
                "s3api",
                "put-object",
                {"Body": b"\x00\xffbinary", "IfNoneMatch": "*"},
                profile=DEVELOPER,
            )

    def test_endpoint_override_or_unlisted_operation_never_reaches_provider(self):
        from rollout_provider import aws

        with patch("rollout_provider.subprocess.run") as run:
            with self.assertRaises(RuntimeError):
                aws("cloudformation", "delete-stack", {}, profile=DEVELOPER)
            with patch.dict("os.environ", {"AWS_ENDPOINT_URL": "https://foreign.invalid"}):
                with self.assertRaises(RuntimeError):
                    aws("sts", "get-caller-identity", {}, profile=DEVELOPER)
            run.assert_not_called()


class RolloutAncestorRecoveryTests(unittest.TestCase):
    def test_writes_require_current_source_and_recovery_checks_git_ancestry(self):
        from rollout_operator import reviewed_source

        old, current = "a" * 40, "b" * 40
        with patch("rollout_operator.subprocess.run") as run:
            for mode in ("upload", "create", "execute"):
                with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                    reviewed_source({"source_sha": old}, current, mode)
            run.assert_not_called()
            for mode in ("inspect", "verify", "upload-inspect"):
                self.assertEqual(reviewed_source({"source_sha": old}, current, mode), old)
                run.assert_called_with(
                    ["git", "merge-base", "--is-ancestor", old, current], check=True
                )

    def test_nonancestor_and_invalid_sources_cannot_enter_recovery(self):
        import subprocess

        from rollout_operator import reviewed_source

        with patch(
            "rollout_operator.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                reviewed_source({"source_sha": "a" * 40}, "b" * 40, "inspect")
        with patch("rollout_operator.subprocess.run") as run:
            with self.assertRaises(RuntimeError):
                reviewed_source({"source_sha": "--help"}, "b" * 40, "inspect")
            run.assert_not_called()

    def test_later_recovery_receipt_producer_must_descend_from_release_and_precede_head(self):
        import tempfile
        from pathlib import Path

        from rollout_operator import fetch_prior

        value = {
            "path": ".github/workflows/aws-rollout.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": DEVELOPER["github_repository"]},
            "status": "completed",
            "conclusion": "failure",
            "head_sha": "b" * 40,
            "run_attempt": 2,
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("rollout_operator.subprocess.check_output", return_value=json.dumps(value)),
            patch("rollout_operator.subprocess.run") as run,
        ):
            fetch_prior("123", Path(directory), "a" * 40, DEVELOPER, recovery=True)
            self.assertEqual(
                run.call_args_list[0].args[0],
                ["git", "merge-base", "--is-ancestor", "a" * 40, "b" * 40],
            )
            self.assertEqual(
                run.call_args_list[1].args[0],
                ["git", "merge-base", "--is-ancestor", "b" * 40, "HEAD"],
            )
            self.assertIn("fitfinity-rollout-123-2", run.call_args_list[2].args[0])
            with self.assertRaises(RuntimeError):
                fetch_prior("123", Path(directory), "a" * 40, DEVELOPER)

        for result in ("failure", "cancelled", "success"):
            producer = {**value, "head_sha": "a" * 40, "conclusion": result}
            with (
                self.subTest(result=result),
                patch(
                    "rollout_operator.subprocess.check_output", return_value=json.dumps(producer)
                ),
                patch("rollout_operator.subprocess.run") as download,
            ):
                args = ("123", Path("/tmp/unused"), "a" * 40, DEVELOPER)
                if result != "success":
                    with self.assertRaisesRegex(RuntimeError, "Successful verified rollout"):
                        fetch_prior(*args, require_success=True)
                    download.assert_not_called()
                    fetch_prior(*args)
                else:
                    fetch_prior(*args, require_success=True)
                self.assertEqual(download.call_count, 1)

    def test_foreign_receipt_ancestry_fails_before_artifact_download(self):
        import subprocess
        from pathlib import Path

        from rollout_operator import fetch_prior

        value = {
            "path": ".github/workflows/aws-rollout.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": DEVELOPER["github_repository"]},
            "status": "completed",
            "conclusion": "success",
            "head_sha": "b" * 40,
            "run_attempt": 1,
        }
        with (
            patch("rollout_operator.subprocess.check_output", return_value=json.dumps(value)),
            patch(
                "rollout_operator.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "git"),
            ) as run,
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                fetch_prior("123", Path("/tmp/unused"), "a" * 40, DEVELOPER, recovery=True)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], "git")

    def test_recovery_provider_refuses_every_mutating_operation(self):
        from rollout_provider import aws

        with patch("rollout_provider.subprocess.run") as run:
            for service, operation in (
                ("s3api", "put-object"),
                ("cloudformation", "create-change-set"),
                ("cloudformation", "execute-change-set"),
                ("lambda", "untag-resource"),
            ):
                with (
                    self.subTest(operation=operation),
                    self.assertRaisesRegex(RuntimeError, "cannot mutate"),
                ):
                    aws(service, operation, {}, profile=DEVELOPER, read_only=True)
            run.assert_not_called()
