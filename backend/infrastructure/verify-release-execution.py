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
        if operation == "get-caller-identity":
            result = deepcopy(self.caller)
            if self.review["mode"] == "pause":
                result["Arn"] = result["Arn"].replace("-github-hosting/", "-github-maintenance/")
            return result
        if operation == "describe-stacks":
            return {"Stacks": [deepcopy(self.stack)]}
        if operation == "get-function":
            return deepcopy(self.function)
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

    def changes(self):
        if self.review["mode"] in {"pause", "resume"}:
            rows = [("ApiFunction", "AWS::Lambda::Function", ["ReservedConcurrentExecutions"])]
        else:
            rows = [
                ("ApiFunction", "AWS::Lambda::Function", ["Code"]),
                ("ApiAlias", "AWS::Lambda::Alias", ["FunctionVersion"]),
                ("Distribution", "AWS::CloudFront::Distribution", ["DistributionConfig"]),
            ]
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

    def test_independent_account_region_and_prefix_execute_without_developer_calls(self):
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
        self.review["mode"] = "pause"
        self.review["candidate_template"] = deepcopy(self.current_template)
        self.review["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ] = 0
        created = self.run_step("create")
        executed = self.run_step("execute", created)
        self.assertEqual(self.run_step("verify", executed)["state"], "template_verified")
        self.assertEqual(
            self.current_template["Resources"]["ApiFunction"]["Properties"][
                "ReservedConcurrentExecutions"
            ],
            0,
        )

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
