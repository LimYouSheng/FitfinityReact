"""Complete backend gate. Docker owns the separate test database lifecycle."""

import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree


def main() -> None:
    mode = os.getenv("FITFINITY_TEST_GROUP", "all")
    from ci_groups import GROUPS

    if mode not in ["all", "checks", *GROUPS]:
        raise RuntimeError("Unknown backend verification group")
    if mode != "checks" and not os.getenv("FITFINITY_TEST_DATABASE_URL"):
        raise RuntimeError("A dedicated test PostgreSQL URL is required; no skipped DB tests")
    for args in (
        [
            ["ruff", "check", "."],
            ["ruff", "format", "--check", "."],
            ["app.api.contract"],
        ]
        if mode in ["all", "checks"]
        else []
    ):
        print("Running backend gate: " + " ".join(args), flush=True)
        subprocess.run([sys.executable, "-m", *args], check=True)
    if mode in ["all", "checks"]:
        subprocess.run([sys.executable, "scripts/test-ci-groups.py"], check=True)
    if mode == "checks":
        return
    if mode == "all":
        subprocess.run(
            [sys.executable, str(Path(__file__).with_name("verify-infrastructure.py"))], check=True
        )
    else:
        env = {**os.environ, "PYTHONPATH": str(Path("scripts").resolve())}
        subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "ci_groups", "-vv", "-rA"], env=env, check=True
        )
        return
    args = ["pytest", "--color=yes", "-vv", "-rA", "--junitxml=/tmp/fitfinity-backend.xml"]
    print("Running backend gate: " + " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m", *args], check=True)
    suites = ElementTree.parse(Path("/tmp/fitfinity-backend.xml")).getroot()
    cases = suites.findall(".//testcase")
    if (
        not cases
        or suites.findall(".//skipped")
        or suites.findall(".//failure")
        or suites.findall(".//error")
    ):
        raise RuntimeError("Backend receipt must contain complete passing tests without skips")
    expected = 1445
    if len(cases) != expected:
        raise RuntimeError(f"Backend receipt must contain exactly {expected} passing cases")
    print(f"\033[32mPASS — {expected}/{expected} backend tests, including real PostgreSQL.\033[0m")


if __name__ == "__main__":
    main()
