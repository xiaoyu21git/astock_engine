from __future__ import annotations

import uuid
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from .quant_data_manager import QuantDataManager


RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC = "rules.template.suggest.request"
RULE_TEMPLATE_SUGGEST_RESPONSE_TOPIC = "rules.template.suggest.response"
RULE_TEMPLATE_SUGGEST_ERROR_TOPIC = "rules.template.suggest.error"


def _coerce_bool(raw_value: Any) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(raw_value)


def _coerce_int(raw_value: Any, default: int) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class RuleTemplateSuggestionEventBridge:
    event_bus: Any | None = None
    manager: QuantDataManager | None = None
    _subscription: Any | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.manager is None:
            self.manager = QuantDataManager()

    def initialize(self, event_bus: Any) -> bool:
        self.event_bus = event_bus
        self._subscription = event_bus.subscribe(RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC, self.handle_request)
        return True

    def handle_request(self, event: Any) -> None:
        payload = getattr(event, "data", None)
        if not isinstance(payload, dict):
            payload = {}

        request_id = self._resolve_request_id(payload)
        correlation_id = self._resolve_correlation_id(payload, request_id)

        try:
            text = str(payload.get("text", "")).strip()
            if not text:
                raise ValueError("text is required")

            response = self.manager.suggest_rule_templates(
                text,
                phase=str(payload.get("phase", "")),
                action=str(payload.get("action", "")),
                tags=list(payload.get("tags") or []),
                available_features=list(
                    payload.get("available_features")
                    or payload.get("availableFeatures")
                    or []
                ),
                only_ready=_coerce_bool(payload.get("only_ready", payload.get("onlyReady", False))),
                limit=_coerce_int(payload.get("limit", 5), 5),
                as_dict=True,
            )
            self._publish_response(request_id, correlation_id, response)
        except Exception as exc:
            self._publish_error(request_id, correlation_id, str(exc))

    def stop(self) -> None:
        if self.event_bus is None or self._subscription is None:
            return

        try:
            self.event_bus.unsubscribe(self._subscription)
        except TypeError:
            try:
                self.event_bus.unsubscribe(RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC, self.handle_request)
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self._subscription = None

    def _publish_response(self, request_id: str, correlation_id: str, response: dict[str, Any]) -> None:
        self.event_bus.publish(
            RULE_TEMPLATE_SUGGEST_RESPONSE_TOPIC,
            {
                "requestId": request_id,
                "correlationId": correlation_id,
                "success": True,
                "query": response.get("query", ""),
                "resolvedTermId": response.get("resolved_term_id", ""),
                "resolvedTermDisplayName": response.get("resolved_term_display_name", ""),
                "suggestions": response.get("suggestions", []),
            },
        )

    def _publish_error(self, request_id: str, correlation_id: str, message: str) -> None:
        self.event_bus.publish(
            RULE_TEMPLATE_SUGGEST_ERROR_TOPIC,
            {
                "requestId": request_id,
                "correlationId": correlation_id,
                "success": False,
                "errorCode": "rule_template_suggest_failed",
                "error": message,
            },
        )

    @staticmethod
    def _resolve_request_id(payload: dict[str, Any]) -> str:
        raw_value = payload.get("requestId") or payload.get("request_id")
        return str(raw_value).strip() if raw_value else str(uuid.uuid4())

    @staticmethod
    def _resolve_correlation_id(payload: dict[str, Any], request_id: str) -> str:
        raw_value = (
            payload.get("correlationId")
            or payload.get("correlation_id")
            or payload.get("requestId")
            or payload.get("request_id")
        )
        return str(raw_value).strip() if raw_value else request_id


def start_rule_template_suggestion_event_bridge(event_bus: Any, manager: QuantDataManager | None = None):
    bridge = RuleTemplateSuggestionEventBridge(event_bus=event_bus, manager=manager)
    bridge.initialize(event_bus)
    return bridge


__all__ = [
    "RULE_TEMPLATE_SUGGEST_ERROR_TOPIC",
    "RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC",
    "RULE_TEMPLATE_SUGGEST_RESPONSE_TOPIC",
    "RuleTemplateSuggestionEventBridge",
    "start_rule_template_suggestion_event_bridge",
]