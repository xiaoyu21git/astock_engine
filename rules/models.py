from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RuleStage(str, Enum):
    MARKET = "market"
    ELIGIBILITY = "eligibility"
    SIGNAL = "signal"
    PORTFOLIO = "portfolio"
    REBALANCE = "rebalance"
    EXECUTION = "execution"
    ACCOUNT_RISK = "account_risk"


class RuleResultType(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    LIMIT = "limit"
    REWRITE = "rewrite"
    SCORE = "score"
    STATE_SWITCH = "state_switch"


def _coerce_stage(raw_value: str) -> RuleStage:
    try:
        return RuleStage(str(raw_value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported rule stage: {raw_value}") from exc


def _coerce_result_type(raw_value: str) -> RuleResultType:
    try:
        return RuleResultType(str(raw_value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported rule result type: {raw_value}") from exc


@dataclass(slots=True)
class RuleActionSpec:
    result_type: RuleResultType
    reason_code: str = ""
    message: str = ""
    payload: Any = field(default_factory=dict)
    score: Any = None
    state: Any = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleActionSpec":
        if not isinstance(payload, dict):
            raise TypeError("Rule action must be a mapping")

        result_key = payload.get("result", payload.get("type"))
        if not result_key:
            raise ValueError("Rule action requires a result field")

        return cls(
            result_type=_coerce_result_type(result_key),
            reason_code=str(payload.get("reason_code", payload.get("reasonCode", ""))).strip(),
            message=str(payload.get("message", "")).strip(),
            payload=payload.get("payload", {}),
            score=payload.get("score"),
            state=payload.get("state"),
        )


@dataclass(slots=True)
class RuleDefinition:
    rule_id: str
    name: str
    stage: RuleStage
    priority: int = 0
    enabled: bool = True
    when: Any = None
    action: RuleActionSpec = field(default_factory=lambda: RuleActionSpec(result_type=RuleResultType.PASS))
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleDefinition":
        if not isinstance(payload, dict):
            raise TypeError("Rule definition must be a mapping")

        rule_id = str(payload.get("id", payload.get("rule_id", ""))).strip()
        if not rule_id:
            raise ValueError("Rule definition requires an id")

        stage = payload.get("stage")
        if not stage:
            raise ValueError(f"Rule {rule_id} requires a stage")

        name = str(payload.get("name", rule_id)).strip() or rule_id
        action_payload = payload.get("then", payload.get("action", {}))

        tags = payload.get("tags", [])
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            raise TypeError(f"Rule {rule_id} tags must be a list")

        return cls(
            rule_id=rule_id,
            name=name,
            stage=_coerce_stage(stage),
            priority=int(payload.get("priority", 0)),
            enabled=bool(payload.get("enabled", True)),
            when=payload.get("when"),
            action=RuleActionSpec.from_dict(action_payload),
            description=str(payload.get("description", "")).strip(),
            tags=[str(tag).strip() for tag in tags if str(tag).strip()],
        )


@dataclass(slots=True)
class RuleEvaluation:
    rule_id: str
    stage: RuleStage
    priority: int
    matched: bool
    enabled: bool
    result_type: RuleResultType | None = None
    reason_code: str = ""
    message: str = ""
    payload: Any = None
    score: Any = None
    state: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "stage": self.stage.value,
            "priority": self.priority,
            "matched": self.matched,
            "enabled": self.enabled,
            "result_type": self.result_type.value if self.result_type else None,
            "reason_code": self.reason_code,
            "message": self.message,
            "payload": self.payload,
            "score": self.score,
            "state": self.state,
        }


@dataclass(slots=True)
class RuleSetDefinition:
    version: int
    namespace: str
    rules: list[RuleDefinition]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleSetDefinition":
        if not isinstance(payload, dict):
            raise TypeError("Rule set payload must be a mapping")

        raw_rules = payload.get("rules", [])
        if not isinstance(raw_rules, list):
            raise TypeError("Rule set rules must be a list")

        return cls(
            version=int(payload.get("version", 1)),
            namespace=str(payload.get("namespace", "default")).strip() or "default",
            rules=[RuleDefinition.from_dict(rule_payload) for rule_payload in raw_rules],
        )