"""Load each canonical operator into an isolated state namespace."""

import importlib.util
from pathlib import Path


def load_operator(filename):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_operator() if hasattr(module, "create_operator") else module
