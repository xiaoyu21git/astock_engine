from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RuleSetDefinition

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency guard
    yaml = None


def load_rule_set_from_mapping(payload: dict[str, Any]) -> RuleSetDefinition:
    return RuleSetDefinition.from_dict(payload)


def load_rule_set_from_file(file_path: str | Path) -> RuleSetDefinition:
    path = Path(file_path)
    suffix = path.suffix.lower()
    raw_text = path.read_text(encoding="utf-8")

    if suffix == ".json":
        return load_rule_set_from_mapping(json.loads(raw_text))

    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to load YAML rule files")
        payload = yaml.safe_load(raw_text) or {}
        return load_rule_set_from_mapping(payload)

    raise ValueError(f"Unsupported rule file extension: {suffix}")