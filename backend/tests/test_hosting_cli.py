"""Exercise the real CLI process; a stopped operator must not make Actions green."""

import json
import os
import subprocess
import sys
from pathlib import Path


def run_hosting(directory, mode):
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "infrastructure" / "deploy.py"),
            "hosting",
            "--mode",
            mode,
            "--operation-id",
            "a" * 32,
            "--directory",
            str(directory),
        ],
        env={**os.environ, "GITHUB_ACTIONS": "false", "AWS_EC2_METADATA_DISABLED": "true"},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_hosting_operational_stop_exits_nonzero_and_preserves_receipt(tmp_path):
    directory = tmp_path / "stopped"
    result = run_hosting(directory, "prepare")
    assert result.returncode == 1
    receipt = json.loads((directory / "receipt.json").read_text())
    assert receipt["status"] == "stopped"
    assert receipt["error"] == "Runtime requires manual reviewed-main Actions execution"
    assert receipt["mode"] == "prepare"
    assert receipt["cloud_writes"] == []
    assert receipt["application_deployed"] is False
    assert receipt["completed_at"]


def test_hosting_offline_plan_exits_zero_and_preserves_receipt(tmp_path):
    directory = tmp_path / "plan"
    result = run_hosting(directory, "plan")
    assert result.returncode == 0, result.stderr
    receipt = json.loads((directory / "receipt.json").read_text())
    assert receipt["status"] == "offline_plan"
    assert receipt["cloud_writes"] == []
    assert (directory / "edge-template.json").is_file()
