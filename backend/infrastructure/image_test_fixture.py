"""Temporary image bytes and contracts for offline runtime tests only."""

import copy
import hashlib
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def image_fixture(source, pinned_contract):
    """Snapshot test inputs once; never rewrite the historical deployment contract.

    A current checkout is not the previously published image. Tests exercise the
    canonical loader/runtime against this separate, immutable-at-capture manifest.
    Later file changes must still fail the runtime's real SHA-256 comparisons.
    """
    contract = copy.deepcopy(pinned_contract)
    with TemporaryDirectory(prefix="fitfinity-offline-image-") as directory:
        root = Path(directory)
        files = set(contract["files"]) | {"app/certificates/ap-southeast-1-bundle.pem"}
        for relative in sorted(files):
            data = (source / relative).read_bytes()
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            if relative in contract["files"]:
                contract["files"][relative] = hashlib.sha256(data).hexdigest()
        yield root, contract
