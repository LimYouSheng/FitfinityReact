"""Offline sender isolation, closed scheduler and release-recovery evidence."""

import hashlib
import hmac
import io
import json
import os
import unittest
from copy import deepcopy
from importlib import import_module
from pathlib import Path
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

    def test_cognito_sender_change_preserves_pool_security_and_invitation_placeholders(self):
        original = json.loads(Path(__file__).with_name("cognito.json").read_text())
        candidate = email_runtime.cognito_template(
            original, identities(fixtures.CLIENT), binding(fixtures.CLIENT)
        )
        configuration = candidate["Resources"]["StaffPool"]["Properties"].pop("EmailConfiguration")
        self.assertEqual(candidate, original)
        self.assertEqual(configuration["EmailSendingAccount"], "DEVELOPER")
        self.assertEqual(configuration["From"], "sender@example.test")
        self.assertIn("{username}", json.dumps(candidate))
        self.assertIn("{####}", json.dumps(candidate))

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
