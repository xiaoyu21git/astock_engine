from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .quant_data_manager import QuantDataManager


_bridge_manager: QuantDataManager | None = None


def _get_bridge_manager() -> QuantDataManager:
    global _bridge_manager
    if _bridge_manager is None:
        _bridge_manager = QuantDataManager()
    return _bridge_manager


def configure_rule_template_bridge(
    term_catalog_path: str | Path | None = None,
    feature_catalog_path: str | Path | None = None,
) -> None:
    manager = _get_bridge_manager()
    manager.configure_rule_template_advisor(term_catalog_path, feature_catalog_path)


def suggest_rule_templates_for_bridge(
    text: str,
    phase: str = "",
    action: str = "",
    tags: Iterable[str] | None = None,
    available_features: Iterable[str] | None = None,
    only_ready: bool = False,
    limit: int = 5,
) -> dict[str, object]:
    manager = _get_bridge_manager()
    return manager.suggest_rule_templates(
        text,
        phase=phase,
        action=action,
        tags=list(tags or []),
        available_features=list(available_features or []),
        only_ready=only_ready,
        limit=limit,
        as_dict=True,
    )


def suggest_rule_templates_from_json(request_json: str) -> str:
    payload = json.loads(request_json) if request_json else {}
    response = suggest_rule_templates_for_bridge(
        text=str(payload.get("text", "")),
        phase=str(payload.get("phase", "")),
        action=str(payload.get("action", "")),
        tags=payload.get("tags") or [],
        available_features=payload.get("available_features") or payload.get("availableFeatures") or [],
        only_ready=bool(payload.get("only_ready", payload.get("onlyReady", False))),
        limit=int(payload.get("limit", 5)),
    )
    return json.dumps(response, ensure_ascii=False)


__all__ = [
    "configure_rule_template_bridge",
    "suggest_rule_templates_for_bridge",
    "suggest_rule_templates_from_json",
]