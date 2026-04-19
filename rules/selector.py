from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .loader import load_trading_feature_catalog_from_file
from .loader import load_trading_term_catalog_from_file
from .models import RuleTemplateCatalogEntry
from .models import TradingFeatureCatalog
from .models import TradingTermCatalog
from .models import TradingTermDefinition


def _normalize_search_text(raw_value: str) -> str:
    value = str(raw_value or "").strip().lower()
    return "".join(char for char in value if not char.isspace() and char not in {"_", "-"})


_QUERY_VARIANT_REPLACEMENTS: dict[str, tuple[str, ...]] = {
    "走弱": ("转弱", "弱化"),
    "转弱": ("走弱", "弱化"),
    "弱化": ("走弱", "转弱"),
    "杀跌": ("反杀", "回落"),
    "反杀": ("杀跌",),
    "低预期": ("低于预期",),
    "低于预期": ("低预期",),
    "无承接": ("承接不足", "承接消失", "承接塌陷"),
    "承接不足": ("无承接",),
}


def _expand_search_variants(raw_value: str) -> set[str]:
    normalized = _normalize_search_text(raw_value)
    if not normalized:
        return set()

    variants = {normalized}
    frontier = [normalized]
    while frontier and len(variants) < 16:
        current = frontier.pop()
        for source, replacements in _QUERY_VARIANT_REPLACEMENTS.items():
            if source not in current:
                continue
            for replacement in replacements:
                candidate = current.replace(source, replacement)
                if candidate and candidate not in variants:
                    variants.add(candidate)
                    frontier.append(candidate)
    return variants


def _collect_search_ngrams(normalized_value: str) -> set[str]:
    value = _normalize_search_text(normalized_value)
    if not value:
        return set()
    if len(value) < 2:
        return {value}

    ngrams: set[str] = set()
    max_n = 3 if len(value) >= 3 else 2
    for n in range(2, max_n + 1):
        for index in range(0, len(value) - n + 1):
            ngrams.add(value[index:index + n])
    return ngrams


def _fuzzy_overlap_bonus(query_value: str, candidate_value: str) -> int:
    query_ngrams = _collect_search_ngrams(query_value)
    candidate_ngrams = _collect_search_ngrams(candidate_value)
    if not query_ngrams or not candidate_ngrams:
        return 0

    overlap_count = len(query_ngrams & candidate_ngrams)
    if overlap_count == 0:
        return 0

    coverage = overlap_count / len(query_ngrams)
    if coverage < 0.45 and overlap_count < 3:
        return 0
    if overlap_count < 2 and coverage < 0.95:
        return 0

    return int(coverage * 24) + min(overlap_count, 8)


def _normalize_optional_values(values: Iterable[str] | None) -> set[str]:
    if values is None:
        return set()
    return {_normalize_search_text(value) for value in values if _normalize_search_text(value)}


@dataclass(slots=True)
class RuleTemplateMatch:
    term_id: str
    term_display_name: str
    template_id: str
    template_display_name: str
    file_name: str
    phase: str
    category: str
    template_actions: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    required_features: list[str] = field(default_factory=list)
    missing_features: list[str] = field(default_factory=list)
    matched_aliases: list[str] = field(default_factory=list)
    score: int = 0
    is_default_template: bool = False

    @property
    def is_ready(self) -> bool:
        return not self.missing_features


class RuleTemplateSelector:
    def __init__(self, term_catalog: TradingTermCatalog, feature_catalog: TradingFeatureCatalog):
        self.term_catalog = term_catalog
        self.feature_catalog = feature_catalog
        self.term_by_id = {term.term_id: term for term in term_catalog.terms}
        self.template_by_id = {template.template_id: template for template in term_catalog.templates}
        self.feature_by_id = {feature.feature_id: feature for feature in feature_catalog.features}

    def resolve_term(self, query: str) -> TradingTermDefinition | None:
        query_variants = _expand_search_variants(query)
        if not query_variants:
            return None

        normalized_query = next(iter(query_variants))

        exact_match = self.term_by_id.get(query)
        if exact_match is not None:
            return exact_match

        for term in self.term_catalog.terms:
            candidates = [term.term_id, term.display_name, *term.aliases]
            normalized_candidates = {_normalize_search_text(candidate) for candidate in candidates}
            if normalized_candidates & query_variants:
                return term

        ranked_matches = self.search_templates(text=query, limit=1)
        if not ranked_matches:
            return None

        return self.term_by_id[ranked_matches[0].term_id]

    def search_templates(
        self,
        *,
        text: str = "",
        phase: str = "",
        category: str = "",
        action: str = "",
        tags: Iterable[str] | None = None,
        available_features: Iterable[str] | None = None,
        only_ready: bool = False,
        limit: int | None = None,
    ) -> list[RuleTemplateMatch]:
        query_variants = _expand_search_variants(text)
        normalized_phase = _normalize_search_text(phase)
        normalized_category = _normalize_search_text(category)
        normalized_action = _normalize_search_text(action)
        normalized_tags = _normalize_optional_values(tags)
        available_feature_ids = set(available_features or [])

        matches: list[RuleTemplateMatch] = []
        for term in self.term_catalog.terms:
            score, matched_aliases = self._score_term(term, query_variants)
            if query_variants and score == 0:
                continue

            if normalized_category and _normalize_search_text(term.category) != normalized_category:
                continue

            for template_id in term.template_ids:
                template = self.template_by_id[template_id]
                if normalized_phase and _normalize_search_text(template.phase) != normalized_phase:
                    continue

                template_action_tokens = {_normalize_search_text(item) for item in template.actions}
                recommended_action_tokens = {_normalize_search_text(item) for item in term.recommended_actions}
                if normalized_action and normalized_action not in template_action_tokens.union(recommended_action_tokens):
                    continue

                tag_tokens = {_normalize_search_text(item) for item in template.tags}
                if normalized_tags and not normalized_tags.issubset(tag_tokens):
                    continue

                missing_features = [
                    feature_id for feature_id in term.required_features if feature_id not in available_feature_ids
                ] if available_features is not None else []
                if only_ready and missing_features:
                    continue

                matches.append(
                    RuleTemplateMatch(
                        term_id=term.term_id,
                        term_display_name=term.display_name,
                        template_id=template.template_id,
                        template_display_name=template.display_name,
                        file_name=template.file_name,
                        phase=template.phase,
                        category=term.category,
                        template_actions=list(template.actions),
                        recommended_actions=list(term.recommended_actions),
                        tags=list(template.tags),
                        required_features=list(term.required_features),
                        missing_features=missing_features,
                        matched_aliases=matched_aliases,
                        score=score + (5 if term.default_template_id == template.template_id else 0),
                        is_default_template=term.default_template_id == template.template_id,
                    )
                )

        matches.sort(
            key=lambda item: (
                -item.score,
                len(item.missing_features),
                item.term_display_name,
                item.template_display_name,
            )
        )
        if limit is not None:
            return matches[:limit]
        return matches

    def get_template(self, template_id: str) -> RuleTemplateCatalogEntry | None:
        return self.template_by_id.get(template_id)

    def get_feature_labels(self, feature_ids: Iterable[str]) -> list[str]:
        labels: list[str] = []
        for feature_id in feature_ids:
            feature = self.feature_by_id.get(feature_id)
            labels.append(feature.display_name if feature is not None else feature_id)
        return labels

    def _score_term(self, term: TradingTermDefinition, query_variants: set[str]) -> tuple[int, list[str]]:
        if not query_variants:
            return 1, []

        matched_aliases: list[str] = []
        score = 0

        def apply_candidate(candidate_text: str, *, exact_score: int, contains_score: int, fuzzy_base: int, alias_label: str = ""):
            nonlocal score
            normalized_candidate = _normalize_search_text(candidate_text)
            if not normalized_candidate:
                return

            best_local_score = 0
            matched = False
            for query_value in query_variants:
                if normalized_candidate == query_value:
                    best_local_score = max(best_local_score, exact_score)
                    matched = True
                    continue
                if query_value in normalized_candidate:
                    best_local_score = max(best_local_score, contains_score)
                    matched = True
                    continue

                fuzzy_bonus = _fuzzy_overlap_bonus(query_value, normalized_candidate)
                if fuzzy_bonus > 0:
                    best_local_score = max(best_local_score, fuzzy_base + fuzzy_bonus)
                    matched = True

            if best_local_score > score:
                score = best_local_score
            if matched and alias_label:
                matched_aliases.append(alias_label)

        apply_candidate(term.term_id, exact_score=100, contains_score=60, fuzzy_base=24)
        apply_candidate(
            term.display_name,
            exact_score=110,
            contains_score=70,
            fuzzy_base=40,
            alias_label=term.display_name,
        )

        for alias in term.aliases:
            apply_candidate(alias, exact_score=105, contains_score=65, fuzzy_base=36, alias_label=alias)

        apply_candidate(term.description, exact_score=42, contains_score=35, fuzzy_base=18)

        for template_id in term.template_ids:
            template = self.template_by_id.get(template_id)
            if template is None:
                continue
            apply_candidate(
                template.display_name,
                exact_score=96,
                contains_score=58,
                fuzzy_base=34,
                alias_label=template.display_name,
            )
            apply_candidate(template.summary, exact_score=48, contains_score=38, fuzzy_base=22)

        deduped_aliases = list(dict.fromkeys(matched_aliases))
        return score, deduped_aliases


def load_rule_template_selector_from_files(
    term_catalog_path: str | Path,
    feature_catalog_path: str | Path,
) -> RuleTemplateSelector:
    return RuleTemplateSelector(
        term_catalog=load_trading_term_catalog_from_file(term_catalog_path),
        feature_catalog=load_trading_feature_catalog_from_file(feature_catalog_path),
    )


def load_default_rule_template_selector() -> RuleTemplateSelector:
    catalog_dir = Path(__file__).resolve().parent / "catalogs"
    return load_rule_template_selector_from_files(
        catalog_dir / "trading_term_catalog.yaml",
        catalog_dir / "trading_feature_catalog.yaml",
    )


__all__ = [
    "RuleTemplateMatch",
    "RuleTemplateSelector",
    "load_default_rule_template_selector",
    "load_rule_template_selector_from_files",
]