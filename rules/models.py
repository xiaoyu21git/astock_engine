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
    WARN = "warn"
    LIMIT = "limit"
    REWRITE = "rewrite"
    SCORE = "score"
    STATE_SWITCH = "state_switch"
    WATCH = "watch"
    UNWATCH = "unwatch"
    CANDIDATE_ENTRY = "candidate_entry"
    CANDIDATE_EXIT = "candidate_exit"
    OPEN = "open"
    ADD = "add"
    REDUCE = "reduce"
    EXIT = "exit"
    COOLDOWN = "cooldown"
    FREEZE = "freeze"
    HALT = "halt"


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


def _normalize_string_list(raw_value: Any, *, field_name: str) -> list[str]:
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise TypeError(f"{field_name} must be a list")
    return [str(item).strip() for item in raw_value if str(item).strip()]


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


@dataclass(slots=True)
class RuleTemplateCatalogEntry:
    template_id: str
    display_name: str
    file_name: str
    phase: str = ""
    summary: str = ""
    actions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleTemplateCatalogEntry":
        if not isinstance(payload, dict):
            raise TypeError("Template catalog entry must be a mapping")

        template_id = str(payload.get("template_id", payload.get("id", ""))).strip()
        if not template_id:
            raise ValueError("Template catalog entry requires template_id")

        file_name = str(payload.get("file_name", payload.get("file", ""))).strip()
        if not file_name:
            raise ValueError(f"Template catalog entry {template_id} requires file_name")

        return cls(
            template_id=template_id,
            display_name=str(payload.get("display_name", payload.get("name", template_id))).strip() or template_id,
            file_name=file_name,
            phase=str(payload.get("phase", "")).strip(),
            summary=str(payload.get("summary", "")).strip(),
            actions=_normalize_string_list(payload.get("actions"), field_name=f"template {template_id} actions"),
            tags=_normalize_string_list(payload.get("tags"), field_name=f"template {template_id} tags"),
        )


@dataclass(slots=True)
class TradingTermDefinition:
    term_id: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    domain: str = ""
    category: str = ""
    description: str = ""
    recommended_rule_types: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    required_features: list[str] = field(default_factory=list)
    default_template_id: str = ""
    template_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TradingTermDefinition":
        if not isinstance(payload, dict):
            raise TypeError("Trading term definition must be a mapping")

        term_id = str(payload.get("term_id", payload.get("id", ""))).strip()
        if not term_id:
            raise ValueError("Trading term definition requires term_id")

        template_ids = _normalize_string_list(payload.get("template_ids"), field_name=f"term {term_id} template_ids")
        default_template_id = str(payload.get("default_template_id", "")).strip()
        if default_template_id and default_template_id not in template_ids:
            template_ids = [default_template_id, *template_ids]

        return cls(
            term_id=term_id,
            display_name=str(payload.get("display_name", payload.get("name", term_id))).strip() or term_id,
            aliases=_normalize_string_list(payload.get("aliases"), field_name=f"term {term_id} aliases"),
            domain=str(payload.get("domain", "")).strip(),
            category=str(payload.get("category", "")).strip(),
            description=str(payload.get("description", "")).strip(),
            recommended_rule_types=_normalize_string_list(
                payload.get("recommended_rule_types"),
                field_name=f"term {term_id} recommended_rule_types",
            ),
            recommended_actions=_normalize_string_list(
                payload.get("recommended_actions"),
                field_name=f"term {term_id} recommended_actions",
            ),
            required_features=_normalize_string_list(
                payload.get("required_features"),
                field_name=f"term {term_id} required_features",
            ),
            default_template_id=default_template_id,
            template_ids=template_ids,
        )


@dataclass(slots=True)
class TradingTermCatalog:
    version: int
    namespace: str
    templates: list[RuleTemplateCatalogEntry]
    terms: list[TradingTermDefinition]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TradingTermCatalog":
        if not isinstance(payload, dict):
            raise TypeError("Trading term catalog payload must be a mapping")

        raw_templates = payload.get("templates", [])
        raw_terms = payload.get("terms", [])
        if not isinstance(raw_templates, list):
            raise TypeError("Trading term catalog templates must be a list")
        if not isinstance(raw_terms, list):
            raise TypeError("Trading term catalog terms must be a list")

        templates = [RuleTemplateCatalogEntry.from_dict(item) for item in raw_templates]
        template_ids = {item.template_id for item in templates}
        terms = [TradingTermDefinition.from_dict(item) for item in raw_terms]

        missing_default_templates = sorted(
            {
                term.default_template_id
                for term in terms
                if term.default_template_id and term.default_template_id not in template_ids
            }
        )
        if missing_default_templates:
            raise ValueError(
                "Trading term catalog references unknown default templates: "
                + ", ".join(missing_default_templates)
            )

        missing_linked_templates = sorted(
            {
                template_id
                for term in terms
                for template_id in term.template_ids
                if template_id not in template_ids
            }
        )
        if missing_linked_templates:
            raise ValueError(
                "Trading term catalog references unknown template_ids: "
                + ", ".join(missing_linked_templates)
            )

        return cls(
            version=int(payload.get("version", 1)),
            namespace=str(payload.get("namespace", "default")).strip() or "default",
            templates=templates,
            terms=terms,
        )


@dataclass(slots=True)
class TradingFeatureDefinition:
    feature_id: str
    display_name: str
    scope: str = ""
    category: str = ""
    value_type: str = ""
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    related_terms: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TradingFeatureDefinition":
        if not isinstance(payload, dict):
            raise TypeError("Trading feature definition must be a mapping")

        feature_id = str(payload.get("feature_id", payload.get("id", ""))).strip()
        if not feature_id:
            raise ValueError("Trading feature definition requires feature_id")

        return cls(
            feature_id=feature_id,
            display_name=str(payload.get("display_name", payload.get("name", feature_id))).strip() or feature_id,
            scope=str(payload.get("scope", "")).strip(),
            category=str(payload.get("category", "")).strip(),
            value_type=str(payload.get("value_type", payload.get("type", ""))).strip(),
            description=str(payload.get("description", "")).strip(),
            aliases=_normalize_string_list(payload.get("aliases"), field_name=f"feature {feature_id} aliases"),
            examples=_normalize_string_list(payload.get("examples"), field_name=f"feature {feature_id} examples"),
            related_terms=_normalize_string_list(
                payload.get("related_terms"),
                field_name=f"feature {feature_id} related_terms",
            ),
        )


@dataclass(slots=True)
class TradingFeatureCatalog:
    version: int
    namespace: str
    features: list[TradingFeatureDefinition]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TradingFeatureCatalog":
        if not isinstance(payload, dict):
            raise TypeError("Trading feature catalog payload must be a mapping")

        raw_features = payload.get("features", [])
        if not isinstance(raw_features, list):
            raise TypeError("Trading feature catalog features must be a list")

        return cls(
            version=int(payload.get("version", 1)),
            namespace=str(payload.get("namespace", "default")).strip() or "default",
            features=[TradingFeatureDefinition.from_dict(item) for item in raw_features],
        )