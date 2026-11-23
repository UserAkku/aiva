"""Tiny JSON store for connector settings/credentials (``data/connectors/*.json``, mode 0600)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        os.chmod(self.folder, 0o700)

    def load(self, name: str, default: Any = None) -> Any:
        path = self.folder / f"{name}.json"
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def save(self, name: str, data: Any) -> None:
        path = self.folder / f"{name}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    def delete(self, name: str) -> None:
        (self.folder / f"{name}.json").unlink(missing_ok=True)
