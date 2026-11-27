"""Retain durable local intent and outcomes for protected cloud operations."""

import json
import os
from pathlib import Path

from deployment_journal import configured


class Journal:
    """Create an exclusive receipt and atomically persist each replacement before effects."""

    def __init__(self, path, *, remote=None):
        self.path = Path(path)
        self.remote = remote if remote is not None else configured(self.path.name)
        self.value = {"state": "not_started", "deployment_decision": "HOLD"}
        with self.path.open("x") as stream:
            stream.write(json.dumps(self.value))
            stream.flush()
            os.fsync(stream.fileno())
        if self.remote is not None:
            self.remote.save(self.value)

    def save(self, value):
        temporary = self.path.with_suffix(self.path.suffix + ".pending")
        with temporary.open("x") as stream:
            stream.write(json.dumps(value, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.value = dict(value)
        if self.remote is not None:
            self.remote.save(self.value)
