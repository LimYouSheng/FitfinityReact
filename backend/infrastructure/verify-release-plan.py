"""Offline rollout/rollback preservation probes using synthetic deployment templates."""

import unittest
from copy import deepcopy

import hosting_design as design
from release_image import URI
from release_observation import digest
from release_plan import prepare


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.template = design.app_template(
            "releases/" + "a" * 40 + "/" + "b" * 64,
            "arn:aws:wafv2:us-east-1:418638389566:global/webacl/"
            "fitfinity-test-login-cloudfront/00000000-0000-0000-0000-000000000000",
        )
        self.arguments = dict(
            observed_template_sha256=digest(self.template),
            source_sha="c" * 40,
            image_digest="sha256:" + "d" * 64,
            frontend_sha256="e" * 64,
        )

    def test_only_reviewed_targets_change_and_original_is_untouched(self):
        original = deepcopy(self.template)
        result = prepare(self.template, **self.arguments)
        self.assertEqual(self.template, original)
        candidate = result["candidate_template"]["Resources"]
        self.assertEqual(result["deployment_decision"], "HOLD")
        self.assertEqual(set(candidate) - set(original["Resources"]), {"ReleaseVersion" + "c" * 40})
        for name, resource in original["Resources"].items():
            if name not in {"ApiFunction", "ApiAlias", "Distribution"}:
                self.assertEqual(candidate[name], resource)
        before = original["Resources"]["ApiFunction"]["Properties"]
        after = candidate["ApiFunction"]["Properties"]
        self.assertEqual(
            {k: v for k, v in before.items() if k != "Code"},
            {k: v for k, v in after.items() if k != "Code"},
        )
        self.assertEqual(after["Code"]["ImageUri"], URI + "@sha256:" + "d" * 64)

    def test_rollback_keeps_all_versions_and_original_alias_assets(self):
        result = prepare(self.template, **self.arguments)
        rollback = result["rollback_template"]["Resources"]
        for name, resource in self.template["Resources"].items():
            self.assertEqual(rollback[name], resource)
        self.assertEqual(set(rollback), set(result["candidate_template"]["Resources"]))
        self.assertEqual(rollback["ReleaseVersion" + "c" * 40]["DeletionPolicy"], "Retain")
        self.assertIn("no downgrade", result["migration"])

    def test_stale_observation_refused(self):
        self.template["Description"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "template changed"):
            prepare(self.template, **self.arguments)

    def test_floating_or_invalid_artifact_rejected(self):
        for field, value in (
            ("source_sha", "main"),
            ("image_digest", "latest"),
            ("frontend_sha256", "unknown"),
        ):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                prepare(self.template, **{**self.arguments, field: value})

    def test_wrong_target_or_weighted_routing_rejected(self):
        for change in ("function", "image", "routing"):
            template = deepcopy(self.template)
            resources = template["Resources"]
            if change == "function":
                resources["ApiFunction"]["Properties"]["FunctionName"] = "other"
            elif change == "image":
                resources["ApiFunction"]["Properties"]["Code"]["ImageUri"] = "other:latest"
            else:
                resources["ApiAlias"]["Properties"]["RoutingConfig"] = {"weighted": True}
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                prepare(
                    template, **{**self.arguments, "observed_template_sha256": digest(template)}
                )

    def test_repeat_candidate_refused_without_deleting_retained_versions(self):
        template = prepare(self.template, **self.arguments)["candidate_template"]
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            prepare(template, **{**self.arguments, "observed_template_sha256": digest(template)})


if __name__ == "__main__":
    unittest.main()
