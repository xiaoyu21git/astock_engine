from __future__ import annotations

import json
import sys
import threading
from typing import Any

from astock_engine.core.eventbus_simple import EventBus
from astock_engine.rule_template_event_bridge import RULE_TEMPLATE_SUGGEST_ERROR_TOPIC
from astock_engine.rule_template_event_bridge import RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC
from astock_engine.rule_template_event_bridge import RULE_TEMPLATE_SUGGEST_RESPONSE_TOPIC
from astock_engine.rule_template_event_bridge import RuleTemplateSuggestionEventBridge


def _emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _request_id(payload: dict[str, Any]) -> str:
    raw_value = payload.get("requestId") or payload.get("request_id")
    return str(raw_value).strip() if raw_value else ""


def _correlation_id(payload: dict[str, Any], request_id: str) -> str:
    raw_value = (
        payload.get("correlationId")
        or payload.get("correlation_id")
        or payload.get("requestId")
        or payload.get("request_id")
    )
    return str(raw_value).strip() if raw_value else request_id


def _process_request(event_bus: EventBus, payload: dict[str, Any]) -> dict[str, Any]:
    request_id = _request_id(payload)
    correlation_id = _correlation_id(payload, request_id)
    ready = threading.Event()
    result: dict[str, Any] = {}

    def on_response(event: Any) -> None:
        event_payload = getattr(event, "data", None)
        if not isinstance(event_payload, dict):
            return
        if request_id and str(event_payload.get("requestId", "")).strip() != request_id:
            return
        result["kind"] = "response"
        result["payload"] = event_payload
        ready.set()

    def on_error(event: Any) -> None:
        event_payload = getattr(event, "data", None)
        if not isinstance(event_payload, dict):
            return
        if request_id and str(event_payload.get("requestId", "")).strip() != request_id:
            return
        result["kind"] = "error"
        result["payload"] = event_payload
        ready.set()

    event_bus.subscribe(RULE_TEMPLATE_SUGGEST_RESPONSE_TOPIC, on_response)
    event_bus.subscribe(RULE_TEMPLATE_SUGGEST_ERROR_TOPIC, on_error)
    try:
        event_bus.publish(RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC, payload)
        if not ready.wait(1.5):
            return {
                "kind": "error",
                "payload": {
                    "requestId": request_id,
                    "correlationId": correlation_id,
                    "success": False,
                    "errorCode": "rule_template_suggest_timeout",
                    "error": "timeout",
                },
            }
        return result
    finally:
        event_bus.unsubscribe(RULE_TEMPLATE_SUGGEST_RESPONSE_TOPIC, on_response)
        event_bus.unsubscribe(RULE_TEMPLATE_SUGGEST_ERROR_TOPIC, on_error)


def main(argv: list[str]) -> int:
    repo_root = argv[1] if len(argv) > 1 else ""
    if repo_root and repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    event_bus = EventBus()
    bridge = RuleTemplateSuggestionEventBridge()
    bridge.initialize(event_bus)
    _emit({"kind": "ready"})

    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                _emit(
                    {
                        "kind": "error",
                        "payload": {
                            "success": False,
                            "errorCode": "rule_template_bridge_parse_error",
                            "error": str(exc),
                        },
                    }
                )
                continue

            if not isinstance(message, dict):
                _emit(
                    {
                        "kind": "error",
                        "payload": {
                            "success": False,
                            "errorCode": "rule_template_bridge_invalid_request",
                            "error": "request must be a JSON object",
                        },
                    }
                )
                continue

            if message.get("command") == "shutdown":
                break

            _emit(_process_request(event_bus, message))
    finally:
        bridge.stop()
        event_bus.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))