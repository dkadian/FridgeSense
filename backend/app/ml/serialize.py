"""JSON persistence for trained artifacts.

Deliberately plain JSON rather than pickle: the file is human-inspectable,
version-controllable, safe to load from untrusted paths, and portable across
Python versions - which matters because the API loads the artifact at start-up.
"""
from __future__ import annotations

import json
import os
from typing import Any

SCHEMA_VERSION = 1


def save_json(obj: dict, path: str, *, indent: int | None = None) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload = dict(obj)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh, indent=indent)
    os.replace(tmp, path)  # atomic, so a crash never leaves a half-written model
    return path


def load_json(path: str) -> dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


def artifact_path(*parts: str) -> str:
    """Resolve a path inside the repository's ml/artifacts directory."""
    here = os.path.dirname(os.path.abspath(__file__))          # backend/app/ml
    repo = os.path.abspath(os.path.join(here, "..", "..", "..")) # repo root
    return os.path.join(repo, "ml", "artifacts", *parts)


def data_path(*parts: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(repo, "data", *parts)
