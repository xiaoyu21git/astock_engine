from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .selector import RuleTemplateMatch
from .selector import RuleTemplateSelector
from .selector import load_default_rule_template_selector
from .selector import load_rule_template_selector_from_files


@dataclass(slots=True)
class RuleTemplateSuggestionRequest:
    text: str
    phase: str = ""
    action: str = ""
    tags: list[str] = field(default_factory=list)
    available_features: list[str] = field(default_factory=list)
    only_ready: bool = False
    limit: int = 5


@dataclass(slots=True)
class RuleTemplateSuggestion:
    term_id: str
    term_display_name: str
    template_id: str
    template_display_name: str
    file_name: str
    file_path: str
    phase: str
    category: str
    summary: str
    file_modified_at: str = ""
    template_actions: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    required_features: list[str] = field(default_factory=list)
    missing_features: list[str] = field(default_factory=list)
    missing_feature_labels: list[str] = field(default_factory=list)
    matched_aliases: list[str] = field(default_factory=list)
    score: int = 0
    is_ready: bool = False
    is_default_template: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RuleTemplateSuggestionResponse:
    query: str
    resolved_term_id: str = ""
    resolved_term_display_name: str = ""
    suggestions: list[RuleTemplateSuggestion] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "resolved_term_id": self.resolved_term_id,
            "resolved_term_display_name": self.resolved_term_display_name,
            "suggestions": [item.to_dict() for item in self.suggestions],
        }


class RuleTemplateAdvisor:
    def __init__(self, selector: RuleTemplateSelector, *, rules_root: str | Path | None = None):
        self.selector = selector
        self.rules_root = Path(rules_root) if rules_root is not None else Path(__file__).resolve().parent

    def suggest_templates(
        self,
        request: RuleTemplateSuggestionRequest,
    ) -> RuleTemplateSuggestionResponse:
        matches = self.selector.search_templates(
            text=request.text,
            phase=request.phase,
            action=request.action,
            tags=request.tags,
            available_features=request.available_features,
            only_ready=request.only_ready,
            limit=request.limit,
        )

        resolved_term = self.selector.resolve_term(request.text)
        suggestions = [self._build_suggestion(item) for item in matches]
        return RuleTemplateSuggestionResponse(
            query=request.text,
            resolved_term_id=resolved_term.term_id if resolved_term is not None else "",
            resolved_term_display_name=resolved_term.display_name if resolved_term is not None else "",
            suggestions=suggestions,
        )

    def suggest_from_text(
        self,
        text: str,
        *,
        phase: str = "",
        action: str = "",
        tags: Iterable[str] | None = None,
        available_features: Iterable[str] | None = None,
        only_ready: bool = False,
        limit: int = 5,
    ) -> RuleTemplateSuggestionResponse:
        request = RuleTemplateSuggestionRequest(
            text=text,
            phase=phase,
            action=action,
            tags=list(tags or []),
            available_features=list(available_features or []),
            only_ready=only_ready,
            limit=limit,
        )
        return self.suggest_templates(request)

    def _build_suggestion(self, match: RuleTemplateMatch) -> RuleTemplateSuggestion:
        template = self.selector.get_template(match.template_id)
        summary = template.summary if template is not None else ""
        file_path_obj = (self.rules_root / "examples" / match.file_name).resolve()
        file_path = str(file_path_obj)
        file_modified_at = ""
        if file_path_obj.exists():
            file_modified_at = datetime.fromtimestamp(file_path_obj.stat().st_mtime).isoformat()
        missing_feature_labels = self.selector.get_feature_labels(match.missing_features)

        return RuleTemplateSuggestion(
            term_id=match.term_id,
            term_display_name=match.term_display_name,
            template_id=match.template_id,
            template_display_name=match.template_display_name,
            file_name=match.file_name,
            file_path=file_path,
            file_modified_at=file_modified_at,
            phase=match.phase,
            category=match.category,
            summary=summary,
            template_actions=list(match.template_actions),
            recommended_actions=list(match.recommended_actions),
            tags=list(match.tags),
            required_features=list(match.required_features),
            missing_features=list(match.missing_features),
            missing_feature_labels=missing_feature_labels,
            matched_aliases=list(match.matched_aliases),
            score=match.score,
            is_ready=match.is_ready,
            is_default_template=match.is_default_template,
        )


def load_rule_template_advisor_from_files(
    term_catalog_path: str | Path,
    feature_catalog_path: str | Path,
) -> RuleTemplateAdvisor:
    selector = load_rule_template_selector_from_files(term_catalog_path, feature_catalog_path)
    rules_root = Path(term_catalog_path).resolve().parent.parent
    return RuleTemplateAdvisor(selector, rules_root=rules_root)


def load_default_rule_template_advisor() -> RuleTemplateAdvisor:
    selector = load_default_rule_template_selector()
    return RuleTemplateAdvisor(selector)


__all__ = [
    "RuleTemplateAdvisor",
    "RuleTemplateSuggestion",
    "RuleTemplateSuggestionRequest",
    "RuleTemplateSuggestionResponse",
    "load_default_rule_template_advisor",
    "load_rule_template_advisor_from_files",
]