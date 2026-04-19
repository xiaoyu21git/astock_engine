from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RuleSetDefinition
from .models import TradingFeatureCatalog
from .models import TradingTermCatalog

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency guard
    yaml = None


def load_rule_set_from_mapping(payload: dict[str, Any]) -> RuleSetDefinition:
    return RuleSetDefinition.from_dict(payload)


def load_trading_term_catalog_from_mapping(payload: dict[str, Any]) -> TradingTermCatalog:
    return TradingTermCatalog.from_dict(payload)


def load_trading_feature_catalog_from_mapping(payload: dict[str, Any]) -> TradingFeatureCatalog:
    return TradingFeatureCatalog.from_dict(payload)


def _load_mapping_from_file(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    raw_text = path.read_text(encoding="utf-8")

    if suffix == ".json":
        payload = json.loads(raw_text)
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise TypeError(f"Expected mapping payload in {path.name}")
        return payload

    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to load YAML rule files")
        payload = yaml.safe_load(raw_text) or {}
        if not isinstance(payload, dict):
            raise TypeError(f"Expected mapping payload in {path.name}")
        return payload

    raise ValueError(f"Unsupported rule file extension: {suffix}")


def load_rule_set_from_file(file_path: str | Path) -> RuleSetDefinition:
    return load_rule_set_from_mapping(_load_mapping_from_file(file_path))


def load_trading_term_catalog_from_file(file_path: str | Path) -> TradingTermCatalog:
    return load_trading_term_catalog_from_mapping(_load_mapping_from_file(file_path))


def load_trading_feature_catalog_from_file(file_path: str | Path) -> TradingFeatureCatalog:
    return load_trading_feature_catalog_from_mapping(_load_mapping_from_file(file_path))