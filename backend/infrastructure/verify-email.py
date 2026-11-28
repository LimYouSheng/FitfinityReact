"""Offline sender isolation, closed scheduler and release-recovery evidence."""

import hashlib
import hmac
import io
import json
import os
import unittest
from copy import deepcopy
from importlib import import_module
from unittest.mock import Mock, patch

import email_runtime
from deployment_profile import identities
from email_scheduler import template
from release_features import prepare, recovery_state, restore_state

fixtures = import_module("verify-release-features")


def binding(profile):
    return {
        "sender": "sender@example.test",
        "identity_arn": (
            f"arn:aws:ses:{profile['region']}:{profile['account']}:identity/example.test"
        ),
        "dispatch_secret": (
            f"arn:aws:secretsmanager:{profile['region']}:{profile['account']}"
            f":secret:{profile['secret_prefix']}/email-dispatch-aBc123"
        ),
        "configuration_set": "",
    }


class EmailInfrastructureTests(unittest.TestCase):
    def test_email_grants_bind_sender_identity_and_dedicated_secret(self):
        profile = fixtures.CLIENT
        value = binding(profile)
        access = email_runtime.access(identities(profile), value)
        self.assertEqual(access[0]["Action"], ["ses:SendEmail"])
        self.assertEqual(access[0]["Resource"], [value["identity_arn"]])
        self.assertEqual(
            access[0]["Condition"], {"StringEquals": {"ses:FromAddress": "sender@example.test"}}
        )
        self.assertEqual(access[1]["Resource"], value["dispatch_secret"])
        self.assertEqual(email_runtime.access(identities(profile), None), [])

    def test_foreign_identity_wildcards_and_secret_values_are_rejected(self):
        value = binding(fixtures.CLIENT)
        for field, replacement in [
            ("identity_arn", "*"),
            ("sender", "forged@other.test"),
            ("dispatch_secret", value["dispatch_secret"] + "*"),
            ("configuration_set", "invalid/name"),
        ]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                email_runtime.checked(identities(fixtures.CLIENT), {**value, field: replacement})

    def test_email_configuration_survives_feature_release_and_recovers_exact_original(self):
        original, values = fixtures.fixture(fixtures.CLIENT)
        activated = prepare(
            original, {**values, "email": binding(fixtures.CLIENT)}, profile=fixtures.CLIENT
        )["candidate_template"]
        env = activated["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
        self.assertEqual(env["FITFINITY_TRANSACTIONAL_EMAIL_ENABLED"], "true")
        self.assertEqual(
            prepare(activated, values, profile=fixtures.CLIENT)["candidate_template"], activated
        )
        restored = restore_state(
            activated, recovery_state(original, fixtures.CLIENT), values, fixtures.CLIENT
        )
        self.assertEqual(restored, original)
        state = recovery_state(activated, fixtures.CLIENT)
        self.assertEqual(restore_state(original, state, values, fixtures.CLIENT), activated)
        # Developer hosting has a separate boundary owner. Omitting a new email
        # override must preserve that owner's existing SES access during rollout.
        from release_features import boundary_arn, check_rollout_access

        external_host = deepcopy(activated)
        resource = external_host["Resources"].pop("RuntimeBoundary")
        external_host["Resources"]["ApiRole"]["Properties"]["PermissionsBoundary"] = boundary_arn(
            fixtures.CLIENT
        )
        external = {"Resources": {"Boundary": resource}}
        reviewed = {"feature_values": values, "external_boundary": {"logical_id": "Boundary"}}
        with patch("release_features.verify_effective") as effective:
            check_rollout_access(reviewed, external_host, None, fixtures.CLIENT, external)
            self.assertEqual(effective.call_args.args[-1], resource["Properties"]["PolicyDocument"])

    def test_email_setup_preserves_cognito_and_keeps_worker_disabled(self):
        from email_setup import documents

        original, values = fixtures.fixture(fixtures.CLIENT)
        before = deepcopy(original)
        alias = (
            f"arn:aws:lambda:{fixtures.CLIENT['region']}:{fixtures.CLIENT['account']}:"
            "function:client-prod-staff-api:live"
        )
        result = documents(fixtures.CLIENT, binding(fixtures.CLIENT), original, None, None, alias)
        self.assertEqual(original, before)
        self.assertEqual(
            result["worker"]["Resources"]["Schedule"]["Properties"]["State"], "DISABLED"
        )
        self.assertFalse(
            any(
                r["Type"].startswith("AWS::Cognito::")
                for r in result["worker"]["Resources"].values()
            )
        )
        changed = {
            key
            for key in original["Resources"]
            if original["Resources"][key] != result["hosting-preview"]["Resources"][key]
        }
        self.assertEqual(changed, {"ApiRole", "ApiFunction", "RuntimeBoundary"})
        self.assertIsNone(result["boundary"])

    def test_workflow_omission_preserves_existing_email_without_new_activation(self):
        from email_deployment import rollout_arguments

        original, values = fixtures.fixture(fixtures.CLIENT)
        args, review = rollout_arguments({}, original, fixtures.CLIENT, Mock())
        self.assertEqual((args, review), ({}, {}))

    def test_workflow_freezes_external_owner_and_requires_installed_boundary(self):
        from email_deployment import rollout_arguments
        from release_observation import digest

        original, values = fixtures.fixture(fixtures.CLIENT)
        resource = original["Resources"].pop("RuntimeBoundary")
        original["Resources"]["ApiRole"]["Properties"]["PermissionsBoundary"] = (
            f"arn:aws:iam::{fixtures.CLIENT['account']}:policy/client-prod-hosting-api-boundary"
        )
        boundary = {"Resources": {"ApiBoundary": resource}}
        desired = prepare(
            original,
            {
                **values,
                "features": dict.fromkeys(values["features"], False),
                "email": binding(fixtures.CLIENT),
            },
            profile=fixtures.CLIENT,
            boundary_template=boundary,
            boundary_template_sha256=digest(boundary),
        )["boundary_candidate_template"]
        owner = {
            "stack_arn": (
                f"arn:aws:cloudformation:{fixtures.CLIENT['region']}:{fixtures.CLIENT['account']}:"
                "stack/client-prod-github-hosting/abc123"
            ),
            "logical_id": "ApiBoundary",
            "template_sha256": digest(desired),
        }
        config = {"email": binding(fixtures.CLIENT), "email_boundary": owner}
        call = Mock(return_value={"TemplateBody": desired})
        args, review = rollout_arguments(config, original, fixtures.CLIENT, call)
        self.assertEqual(review["external_boundary"], owner)
        self.assertEqual(review["feature_values"]["email"], binding(fixtures.CLIENT))
        planned = prepare(
            original,
            args["feature_values"],
            profile=fixtures.CLIENT,
            boundary_template=args["boundary_template"],
            boundary_template_sha256=args["boundary_template_sha256"],
        )
        self.assertFalse(planned["boundary_update_required"])
        with self.assertRaisesRegex(RuntimeError, "boundary template changed"):
            rollout_arguments(
                config, original, fixtures.CLIENT, Mock(return_value={"TemplateBody": boundary})
            )

    def test_manual_email_review_cannot_drift_from_configuration(self):
        from email_deployment import verify_review

        email = binding(fixtures.CLIENT)
        verify_review({"email": email}, {"feature_values": {"email": email}}, fixtures.CLIENT)
        for config, review in (({}, {"feature_values": {"email": email}}), ({"email": email}, {})):
            with self.subTest(config=config), self.assertRaises(RuntimeError):
                verify_review(config, review, fixtures.CLIENT)

    def test_coordinator_setup_only_adds_exact_boundary_read(self):
        from email_setup import coordinator_read
        from journal_setup import coordinator_template

        original = coordinator_template(fixtures.CLIENT)
        root = (
            f"arn:aws:cloudformation:{fixtures.CLIENT['region']}:{fixtures.CLIENT['account']}:"
            "stack/"
        )
        documents = [
            original["Resources"]["CoordinatorBoundary"]["Properties"]["PolicyDocument"],
            original["Resources"]["CoordinatorRole"]["Properties"]["Policies"][0]["PolicyDocument"],
        ]
        for document in documents:
            for statement in document["Statement"]:
                if statement["Action"] == "cloudformation:GetTemplate":
                    statement["Resource"] = root + "client-prod-login/*"
        candidate = coordinator_read(original, identities(fixtures.CLIENT))
        self.assertEqual(candidate, coordinator_template(fixtures.CLIENT))
        self.assertNotEqual(candidate, original)
        self.assertEqual(coordinator_read(candidate, identities(fixtures.CLIENT)), candidate)

    def test_partial_recovery_binding_is_rejected(self):
        env = email_runtime.environment(identities(fixtures.CLIENT), binding(fixtures.CLIENT))
        for key in env:
            partial = deepcopy(env)
            del partial[key]
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                email_runtime.from_environment(identities(fixtures.CLIENT), partial)

    def test_scheduler_is_disabled_and_only_invokes_exact_alias(self):
        p = fixtures.CLIENT
        arn = f"arn:aws:lambda:{p['region']}:{p['account']}:function:client-prod-staff-api:live"
        value = template(
            p["account"],
            p["region"],
            p["resource_prefix"],
            arn,
            binding(p)["dispatch_secret"],
            p["secret_prefix"],
        )
        resources = value["Resources"]
        # Execute the emitted worker with synthetic clients; verify the actual
        # request signature and disposal, not only the template's role shape.
        secret = Mock()
        secret.get_secret_value.return_value = {
            "SecretString": json.dumps({"dispatch_key": "01" * 32})
        }
        invocation = Mock()
        stream = io.BytesIO(b'{"statusCode":200}')
        invocation.invoke.return_value = {"Payload": stream}
        with (
            patch("boto3.client", side_effect=[secret, invocation]),
            patch.dict(
                os.environ, {"DISPATCH_SECRET": binding(p)["dispatch_secret"], "API_FUNCTION": arn}
            ),
        ):
            worker = {}
            exec(
                compile(
                    resources["Worker"]["Properties"]["Code"]["ZipFile"], "email-worker", "exec"
                ),
                worker,
            )
            self.assertEqual(worker["handler"]({}, None), {"dispatched": True})
        sent = invocation.invoke.call_args.kwargs
        self.assertEqual(sent["FunctionName"], arn)
        request = json.loads(sent["Payload"])
        self.assertEqual(request["path"], "/internal/email-dispatch")
        expected = hmac.new(
            bytes.fromhex("01" * 32),
            b"fitfinity.email.dispatch.v1\n" + request["body"].encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(request["headers"]["x-fitfinity-email-signature"], expected)
        self.assertEqual(set(json.loads(request["body"])), {"at", "id"})
        secret.close.assert_called_once()
        invocation.close.assert_called_once()
        self.assertTrue(stream.closed)

        self.assertEqual(resources["Schedule"]["Properties"]["State"], "DISABLED")
        access = resources["Role"]["Properties"]["Policies"][0]["PolicyDocument"]
        self.assertEqual(access, resources["Boundary"]["Properties"]["PolicyDocument"])
        self.assertEqual(access["Statement"][0]["Resource"], arn)
        self.assertEqual(resources["Worker"]["Properties"]["ReservedConcurrentExecutions"], 1)
        with self.assertRaises(ValueError):
            template(
                p["account"],
                p["region"],
                p["resource_prefix"],
                arn,
                binding(p)["dispatch_secret"] + "*",
                p["secret_prefix"],
            )


if __name__ == "__main__":
    unittest.main()
