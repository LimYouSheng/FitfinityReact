"Offline infrastructure regression gate; no AWS, Docker, SQL or network access."

import importlib.util
import os
import socket
import subprocess
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "infrastructure")]
SUITES = {
    "verify-db-access.py": 151,
    "verify-db-migrations.py": 41,
    "verify-auth-secrets.py": 37,
    "verify-foundation-plan.py": 9,
    "verify-foundation-execute.py": 12,
    "verify-egress-preflight.py": 10,
    "verify-egress-execute.py": 22,
    "verify-cognito.py": 16,
    "verify-private-egress.py": 15,
    "verify-image.py": 35,
    "verify-deployment.py": 30,
    "verify-release-image.py": 30,
    "verify-image-acceptance.py": 26,
    "verify-private-runtime.py": 52,
    "verify-hosting.py": 61,
}


class FixtureClock(datetime):
    "Historical acceptance fixtures use a fixed clock; live operators never do."

    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 25, 14, 0, tzinfo=UTC)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def forbidden(*args, **kwargs):
    raise AssertionError("Offline infrastructure tests attempted an unstubbed external operation")


def main():
    if sys.flags.optimize:
        raise RuntimeError("Assertions must be enabled for infrastructure verification")
    discovered = {path.name for path in (ROOT / "infrastructure").glob("verify-*.py")}
    if discovered != set(SUITES):
        raise RuntimeError(f"Infrastructure suite inventory mismatch: {discovered ^ set(SUITES)}")
    combined = unittest.TestSuite()
    # Overrides are scoped to this process and never carried into a cloud command.
    with (
        patch.dict(os.environ, {"AWS_EC2_METADATA_DISABLED": "true"}),
        patch("datetime.datetime", FixtureClock),
        patch.object(socket.socket, "connect", forbidden),
        patch.object(socket, "create_connection", forbidden),
        patch.object(subprocess, "run", forbidden),
        patch.object(subprocess, "Popen", forbidden),
    ):
        for filename, expected in SUITES.items():
            spec = importlib.util.spec_from_file_location(
                filename[:-3], ROOT / "infrastructure" / filename
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            if suite.countTestCases() != expected:
                raise RuntimeError(
                    f"{filename}: expected {expected}, found {suite.countTestCases()}"
                )
            print(f"Infrastructure suite: {filename} — {expected} cases", flush=True)
            combined.addTests(suite)
        result = unittest.TextTestRunner(verbosity=2).run(combined)
    expected = sum(SUITES.values())
    if (
        not result.wasSuccessful()
        or result.skipped
        or result.expectedFailures
        or result.testsRun != expected
    ):
        raise RuntimeError(
            f"Infrastructure gate failed: ran {result.testsRun}/{expected}; "
            f"failures={len(result.failures)}, errors={len(result.errors)}, "
            f"skipped={len(result.skipped)}, expected_failures={len(result.expectedFailures)}, "
            f"unexpected_successes={len(result.unexpectedSuccesses)}; "
            "no skipped/expected-failure cases accepted"
        )
    print(
        f"\033[32mPASS — {expected}/{expected} offline infrastructure tests. "
        "AWS and database operations were simulated.\033[0m"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\033[31mFAIL — infrastructure gate: {error}\033[0m", file=sys.stderr)
        raise SystemExit(1) from None
