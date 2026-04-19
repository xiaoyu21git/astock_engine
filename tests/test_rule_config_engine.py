import json
from pathlib import Path
import re
import threading

from astock_engine import QuantDataManager
from astock_engine.rules import RuleEngine
from astock_engine.rules import RuleResultType
from astock_engine.rules import RuleTemplateSuggestionRequest
from astock_engine.rules import load_default_rule_template_advisor
from astock_engine.rules import load_default_rule_template_selector
from astock_engine.rules import load_trading_feature_catalog_from_file
from astock_engine.rules import load_rule_set_from_file
from astock_engine.rules import load_rule_set_from_mapping
from astock_engine.rules import load_rule_template_advisor_from_files
from astock_engine.rules import load_rule_template_selector_from_files
from astock_engine.rules import load_trading_term_catalog_from_file
from astock_engine.rule_template_bridge import suggest_rule_templates_for_bridge
from astock_engine.rule_template_bridge import suggest_rule_templates_from_json
from astock_engine.rule_template_event_bridge import RULE_TEMPLATE_SUGGEST_ERROR_TOPIC
from astock_engine.rule_template_event_bridge import RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC
from astock_engine.rule_template_event_bridge import RULE_TEMPLATE_SUGGEST_RESPONSE_TOPIC
from astock_engine.rule_template_event_bridge import RuleTemplateSuggestionEventBridge
from astock_engine.core.eventbus_simple import EventBus as SimpleEventBus


def test_rule_engine_blocks_symbol_outside_pool():
    rule_set = load_rule_set_from_mapping(
        {
            "version": 1,
            "namespace": "trading",
            "rules": [
                {
                    "id": "symbol-outside-pool",
                    "stage": "eligibility",
                    "priority": 90,
                    "when": {
                        "op": "not",
                        "value": {
                            "op": "symbol_in_pool",
                            "symbol": {"var": "candidate.symbol"},
                            "pool": {"var": "strategy.symbol_pool"},
                        },
                    },
                    "then": {
                        "result": "block",
                        "reason_code": "symbol_outside_scope",
                        "message": "Candidate symbol is outside the configured pool",
                    },
                }
            ],
        }
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "eligibility",
        {
            "candidate": {"symbol": "600000.SH"},
            "strategy": {"symbol_pool": ["000001.SZ", "600519.SH"]},
        },
    )

    assert len(results) == 1
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "symbol_outside_scope"


def test_rule_engine_renders_limit_payload_and_score_expression():
    rule_set = load_rule_set_from_mapping(
        {
            "version": 1,
            "namespace": "trading",
            "rules": [
                {
                    "id": "exposure-limit",
                    "stage": "portfolio",
                    "priority": 80,
                    "when": {
                        "op": "gt",
                        "left": {"var": "portfolio.projected_exposure"},
                        "right": {"var": "rule_limits.max_exposure"},
                    },
                    "then": {
                        "result": "limit",
                        "reason_code": "portfolio_exposure_limit",
                        "message": "Projected exposure exceeds configured cap",
                        "payload": {
                            "max_exposure": {"var": "rule_limits.max_exposure"},
                            "projected_exposure": {"var": "portfolio.projected_exposure"},
                        },
                    },
                },
                {
                    "id": "momentum-score",
                    "stage": "signal",
                    "priority": 40,
                    "when": {
                        "op": "gt",
                        "left": {"var": "candidate.momentum"},
                        "right": 0,
                    },
                    "then": {
                        "result": "score",
                        "reason_code": "positive_momentum",
                        "message": "Momentum contributes to candidate ranking",
                        "score": {"var": "candidate.momentum"},
                    },
                },
            ],
        }
    )

    engine = RuleEngine()

    portfolio_results = engine.evaluate_stage(
        rule_set,
        "portfolio",
        {
            "portfolio": {"projected_exposure": 0.82},
            "rule_limits": {"max_exposure": 0.65},
        },
    )
    assert portfolio_results[0].result_type == RuleResultType.LIMIT
    assert portfolio_results[0].payload == {
        "max_exposure": 0.65,
        "projected_exposure": 0.82,
    }

    signal_results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {"momentum": 1.75},
        },
    )
    assert signal_results[0].result_type == RuleResultType.SCORE
    assert signal_results[0].score == 1.75


def test_rule_engine_detects_open_trading_session():
    rule_set = load_rule_set_from_mapping(
        {
            "version": 1,
            "namespace": "trading",
            "rules": [
                {
                    "id": "market-session-open",
                    "stage": "market",
                    "priority": 100,
                    "when": {
                        "op": "is_trading_session",
                        "session": {"var": "market.session"},
                    },
                    "then": {
                        "result": "pass",
                        "reason_code": "market_session_open",
                        "message": "Market session is open",
                    },
                }
            ],
        }
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {"session": {"sessionOpen": True}},
        },
    )

    assert len(results) == 1
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.PASS
    assert results[0].reason_code == "market_session_open"


def test_rule_template_examples_are_loadable():
    examples_dir = Path(__file__).resolve().parents[1] / "rules" / "examples"
    yaml_files = sorted(path for path in examples_dir.glob("*.yaml") if path.name != "trading_rules.example.yaml")

    assert yaml_files, "Expected at least one YAML rule template example"

    for file_path in yaml_files:
        rule_set = load_rule_set_from_file(file_path)
        assert rule_set.namespace
        assert rule_set.rules, f"Expected rules in template {file_path.name}"


def test_weak_to_strong_template_produces_candidate_entry():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "entry_weak_to_strong.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "previous_weakness_confirmed": True,
                "reclaim_reference_ratio": 1.02,
                "volume_ratio_to_5d_avg": 2.1,
                "change_percent": 7.2,
                "reclaim_reference_strength": 86,
            },
            "market": {
                "emotion_cycle": "repair",
            },
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].reason_code == "weak_to_strong_candidate"
    assert matched[0].payload["entry_style"] == "weak_to_strong"


def test_market_emotion_cooling_template_switches_to_frozen_state():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "risk_market_emotion_cooling_freeze.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {
                "emotion_cycle": "cooling",
                "high_level_open_board_rate": 0.34,
                "limit_up_reseal_rate": 0.56,
                "theme_breadth": 0.38,
            }
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].result_type == RuleResultType.STATE_SWITCH
    assert matched[0].state["market_state"] == "frozen"
    assert matched[0].payload["gate_level"] == "market_defense_freeze"


def test_market_emotion_cooling_template_repairs_to_cautious_state():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "risk_market_emotion_cooling_freeze.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {
                "emotion_cycle": "repair",
                "high_level_open_board_rate": 0.22,
                "limit_up_reseal_rate": 0.64,
                "theme_breadth": 0.58,
            }
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].state["market_state"] == "cautious"
    assert matched[0].payload["gate_level"] == "cautious_watch"


def test_market_high_level_open_board_deterioration_template_switches_to_frozen_state():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1]
        / "rules"
        / "examples"
        / "risk_market_high_level_open_board_deterioration_freeze.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {
                "emotion_cycle": "cooling",
                "high_level_open_board_rate": 0.46,
                "limit_up_reseal_rate": 0.49,
                "theme_breadth": 0.41,
            }
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].result_type == RuleResultType.STATE_SWITCH
    assert matched[0].state["market_state"] == "frozen"
    assert matched[0].payload["gate_level"] == "high_level_break_freeze"


def test_market_high_level_open_board_deterioration_template_repairs_to_cautious_state():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1]
        / "rules"
        / "examples"
        / "risk_market_high_level_open_board_deterioration_freeze.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {
                "emotion_cycle": "repair",
                "high_level_open_board_rate": 0.21,
                "limit_up_reseal_rate": 0.66,
                "theme_breadth": 0.54,
            }
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].state["market_state"] == "cautious"
    assert matched[0].payload["gate_level"] == "cautious_watch"


def test_market_reseal_rate_drop_template_switches_to_frozen_state():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "risk_market_reseal_rate_drop_freeze.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {
                "emotion_cycle": "panic",
                "high_level_open_board_rate": 0.26,
                "limit_up_reseal_rate": 0.42,
                "theme_breadth": 0.33,
            }
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].state["market_state"] == "frozen"
    assert matched[0].payload["gate_level"] == "reseal_failure_freeze"


def test_market_reseal_rate_drop_template_repairs_to_cautious_state():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "risk_market_reseal_rate_drop_freeze.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {
                "emotion_cycle": "repair",
                "high_level_open_board_rate": 0.24,
                "limit_up_reseal_rate": 0.65,
                "theme_breadth": 0.51,
            }
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].state["market_state"] == "cautious"
    assert matched[0].payload["gate_level"] == "cautious_watch"


def test_market_theme_cooling_template_switches_to_frozen_state():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "risk_market_theme_cooling_freeze.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {
                "emotion_cycle": "cooling",
                "high_level_open_board_rate": 0.30,
                "limit_up_reseal_rate": 0.50,
                "theme_breadth": 0.28,
            }
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].state["market_state"] == "frozen"
    assert matched[0].payload["gate_level"] == "theme_cooling_freeze"


def test_market_theme_cooling_template_repairs_to_cautious_state():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "risk_market_theme_cooling_freeze.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "market",
        {
            "market": {
                "emotion_cycle": "repair",
                "high_level_open_board_rate": 0.23,
                "limit_up_reseal_rate": 0.63,
                "theme_breadth": 0.61,
            }
        },
    )

    assert results
    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].state["market_state"] == "cautious"
    assert matched[0].payload["gate_level"] == "cautious_watch"


def test_trading_term_catalog_is_loadable_and_has_template_links():
    rules_dir = Path(__file__).resolve().parents[1] / "rules"
    catalog = load_trading_term_catalog_from_file(rules_dir / "catalogs" / "trading_term_catalog.yaml")

    assert catalog.namespace == "a_share_short_term"
    assert catalog.templates
    assert catalog.terms

    template_ids = {template.template_id for template in catalog.templates}
    example_files = {path.name for path in (rules_dir / "examples").glob("*.yaml")}

    for template in catalog.templates:
        assert template.file_name in example_files

    for term in catalog.terms:
        assert term.default_template_id in template_ids
        assert term.default_template_id in term.template_ids
        assert term.required_features


def test_trading_term_catalog_covers_all_example_templates_without_duplicates():
    rules_dir = Path(__file__).resolve().parents[1] / "rules"
    catalog = load_trading_term_catalog_from_file(rules_dir / "catalogs" / "trading_term_catalog.yaml")

    example_files = sorted(
        path.name
        for path in (rules_dir / "examples").glob("*.yaml")
        if path.name != "trading_rules.example.yaml"
    )
    catalog_files = [template.file_name for template in catalog.templates]

    duplicate_catalog_files = sorted(
        {
            file_name
            for file_name in catalog_files
            if catalog_files.count(file_name) > 1
        }
    )
    missing_in_catalog = sorted(set(example_files) - set(catalog_files))
    extra_in_catalog = sorted(set(catalog_files) - set(example_files))

    assert not duplicate_catalog_files, (
        f"Duplicate template file links in trading_term_catalog.yaml: {duplicate_catalog_files}"
    )
    assert not missing_in_catalog, (
        f"Example templates missing from trading_term_catalog.yaml: {missing_in_catalog}"
    )
    assert not extra_in_catalog, (
        f"Catalog template links missing example YAML files: {extra_in_catalog}"
    )
    assert len(catalog_files) == len(example_files)


def test_rule_template_preview_utils_covers_catalog_templates_without_duplicates():
    rules_dir = Path(__file__).resolve().parents[1] / "rules"
    workspace_root = Path(__file__).resolve().parents[2]
    preview_utils_path = workspace_root / "src" / "app" / "Qml" / "utils" / "RuleTemplatePreviewUtils.js"

    assert preview_utils_path.exists(), f"Preview helper not found: {preview_utils_path}"

    catalog = load_trading_term_catalog_from_file(rules_dir / "catalogs" / "trading_term_catalog.yaml")
    catalog_template_ids = sorted(template.template_id for template in catalog.templates)

    preview_text = preview_utils_path.read_text(encoding="utf-8")
    preview_template_ids = re.findall(
        r"^\s*(template_[a-z0-9_]+_v1)\s*:\s*\{",
        preview_text,
        flags=re.MULTILINE,
    )

    duplicate_preview_ids = sorted(
        {
            template_id
            for template_id in preview_template_ids
            if preview_template_ids.count(template_id) > 1
        }
    )
    missing_in_preview = sorted(set(catalog_template_ids) - set(preview_template_ids))
    extra_in_preview = sorted(set(preview_template_ids) - set(catalog_template_ids))

    assert preview_template_ids, "Expected RuleTemplatePreviewUtils.js to define specialized preview entries"
    assert not duplicate_preview_ids, (
        f"Duplicate preview template IDs in RuleTemplatePreviewUtils.js: {duplicate_preview_ids}"
    )
    assert not missing_in_preview, (
        f"Catalog templates missing specialized preview entries: {missing_in_preview}"
    )
    assert not extra_in_preview, (
        f"Preview helper contains template IDs missing from trading_term_catalog.yaml: {extra_in_preview}"
    )
    assert len(preview_template_ids) == len(catalog_template_ids)


def test_rule_template_examples_readme_lists_all_example_templates():
    rules_dir = Path(__file__).resolve().parents[1] / "rules"
    readme_text = (rules_dir / "examples" / "README.md").read_text(encoding="utf-8")

    example_files = sorted(
        path.name
        for path in (rules_dir / "examples").glob("*.yaml")
        if path.name != "trading_rules.example.yaml"
    )
    documented_files = []
    for line in readme_text.splitlines():
        line = line.strip()
        if ".yaml`：" not in line:
            continue
        documented_files.append(line.split("`")[1])

    duplicate_documented_files = sorted(
        {
            file_name
            for file_name in documented_files
            if documented_files.count(file_name) > 1
        }
    )
    missing_in_readme = sorted(set(example_files) - set(documented_files))
    extra_in_readme = sorted(set(documented_files) - set(example_files))

    assert documented_files, "Expected README.md to document rule template YAML files"
    assert not duplicate_documented_files, (
        f"Duplicate template file names in rules/examples/README.md: {duplicate_documented_files}"
    )
    assert not missing_in_readme, (
        f"Example templates missing from rules/examples/README.md: {missing_in_readme}"
    )
    assert not extra_in_readme, (
        f"README.md lists template files that do not exist: {extra_in_readme}"
    )
    assert len(documented_files) == len(example_files)


def test_trading_feature_catalog_covers_term_required_features():
    rules_dir = Path(__file__).resolve().parents[1] / "rules"
    term_catalog = load_trading_term_catalog_from_file(rules_dir / "catalogs" / "trading_term_catalog.yaml")
    feature_catalog = load_trading_feature_catalog_from_file(rules_dir / "catalogs" / "trading_feature_catalog.yaml")

    feature_ids = {feature.feature_id for feature in feature_catalog.features}
    missing_features = sorted(
        {
            feature_id
            for term in term_catalog.terms
            for feature_id in term.required_features
            if feature_id not in feature_ids
        }
    )

    assert not missing_features, f"Missing feature definitions: {missing_features}"


def test_rule_template_selector_can_resolve_term_alias_and_ready_templates():
    selector = load_default_rule_template_selector()

    resolved_term = selector.resolve_term("回流尾盘走弱")

    assert resolved_term is not None
    assert resolved_term.term_id == "consensus_reflow_tail_weakening"

    matches = selector.search_templates(
        text="回流尾盘走弱",
        phase="signal",
        action="block",
        available_features=[
            "candidate.consensus_reflow_confirmed",
            "candidate.tail_weakening_confirmed",
            "candidate.close_below_reflow_tail_pivot_ratio",
            "market.consensus_reflow_hold_rate",
        ],
        only_ready=True,
    )

    assert matches
    assert matches[0].term_id == "consensus_reflow_tail_weakening"
    assert matches[0].template_id == "template_watch_consensus_reflow_tail_weakening_v1"
    assert matches[0].is_ready is True
    assert matches[0].missing_features == []


def test_rule_template_selector_can_resolve_market_risk_term_alias():
    selector = load_default_rule_template_selector()

    resolved_term = selector.resolve_term("高位炸板率恶化")

    assert resolved_term is not None
    assert resolved_term.term_id == "market_high_level_open_board_deterioration_freeze"

    matches = selector.search_templates(
        text="高位炸板率恶化",
        phase="market",
        action="freeze",
        available_features=[
            "market.emotion_cycle",
            "market.high_level_open_board_rate",
            "market.limit_up_reseal_rate",
            "market.theme_breadth",
        ],
        only_ready=True,
    )

    assert matches
    assert matches[0].term_id == "market_high_level_open_board_deterioration_freeze"
    assert matches[0].template_id == "template_risk_market_high_level_open_board_deterioration_freeze_v1"
    assert matches[0].is_ready is True


def test_rule_template_selector_can_resolve_theme_cooling_term_alias():
    selector = load_default_rule_template_selector()

    resolved_term = selector.resolve_term("题材退潮")

    assert resolved_term is not None
    assert resolved_term.term_id == "market_theme_cooling_freeze"

    matches = selector.search_templates(
        text="题材退潮",
        phase="market",
        action="freeze",
        available_features=[
            "market.emotion_cycle",
            "market.high_level_open_board_rate",
            "market.limit_up_reseal_rate",
            "market.theme_breadth",
        ],
        only_ready=True,
    )

    assert matches
    assert matches[0].term_id == "market_theme_cooling_freeze"
    assert matches[0].template_id == "template_risk_market_theme_cooling_freeze_v1"
    assert matches[0].is_ready is True


def test_rule_template_selector_can_resolve_bull_market_gate_term_alias():
    selector = load_default_rule_template_selector()

    resolved_term = selector.resolve_term("牛市放行")

    assert resolved_term is not None
    assert resolved_term.term_id == "market_bull_trend_allow_entry"

    matches = selector.search_templates(
        text="牛市放行",
        phase="market",
        action="state_switch",
        available_features=[
            "market.regime_state",
            "market.breadth_above_ma60_ratio",
            "market.index_above_ma120_ratio",
            "market.trend_strength_score",
        ],
        only_ready=True,
    )

    assert matches
    assert matches[0].term_id == "market_bull_trend_allow_entry"
    assert matches[0].template_id == "template_risk_market_bull_trend_allow_entry_v1"
    assert matches[0].is_ready is True


def test_rule_template_selector_can_resolve_bear_market_risk_term_alias():
    selector = load_default_rule_template_selector()

    resolved_term = selector.resolve_term("熊市冻结")

    assert resolved_term is not None
    assert resolved_term.term_id == "market_bear_freeze_entry"

    matches = selector.search_templates(
        text="熊市冻结",
        phase="market",
        action="freeze",
        available_features=[
            "market.regime_state",
            "market.breadth_above_ma60_ratio",
            "market.drawdown_from_recent_high",
            "market.volatility_shock_score",
        ],
        only_ready=True,
    )

    assert matches
    assert matches[0].term_id == "market_bear_freeze_entry"
    assert matches[0].template_id == "template_risk_market_bear_freeze_entry_v1"
    assert matches[0].is_ready is True



def test_rule_template_selector_reports_missing_features_for_incomplete_context():
    rules_dir = Path(__file__).resolve().parents[1] / "rules"
    selector = load_rule_template_selector_from_files(
        rules_dir / "catalogs" / "trading_term_catalog.yaml",
        rules_dir / "catalogs" / "trading_feature_catalog.yaml",
    )

    matches = selector.search_templates(
        text="弱转强失败后低开无承接",
        phase="rebalance",
        action="exit",
        available_features=[
            "position.weak_to_strong_attempted",
            "position.weak_to_strong_failed_confirmed",
            "position.next_day_gap_down_confirmed",
            "position.close_below_reclaim_pivot_ratio",
        ],
    )

    assert matches
    assert matches[0].term_id == "weak_to_strong_failed_gap_down_no_acceptance"
    assert matches[0].template_id == "template_exit_weak_to_strong_failed_gap_down_no_acceptance_v1"
    assert matches[0].is_ready is False
    assert matches[0].missing_features == ["position.acceptance_strength_score"]


def test_rule_template_selector_filters_by_tag_and_phase():
    selector = load_default_rule_template_selector()

    matches = selector.search_templates(
        text="午后反杀",
        phase="signal",
        tags=["emotion_repair", "afternoon_reversal_kill"],
        available_features=[
            "market.emotion_repair_confirmed",
            "candidate.afternoon_reversal_kill_confirmed",
            "candidate.close_below_afternoon_repair_pivot_ratio",
            "candidate.repair_follow_strength_score",
        ],
        only_ready=True,
    )

    assert matches
    assert matches[0].template_id == "template_watch_emotion_repair_afternoon_reversal_kill_v1"
    assert matches[0].file_name == "watch_emotion_repair_afternoon_reversal_kill.yaml"


def test_rule_template_selector_can_resolve_natural_language_variant_for_watch_term():
    selector = load_default_rule_template_selector()

    resolved_term = selector.resolve_term("修复日午后杀跌")

    assert resolved_term is not None
    assert resolved_term.term_id == "emotion_repair_afternoon_reversal_kill"

    matches = selector.search_templates(
        text="修复日午后杀跌",
        phase="signal",
        action="block",
        available_features=[
            "market.emotion_repair_confirmed",
            "candidate.afternoon_reversal_kill_confirmed",
            "candidate.close_below_afternoon_repair_pivot_ratio",
            "candidate.repair_follow_strength_score",
        ],
        only_ready=True,
        limit=1,
    )

    assert matches
    assert matches[0].term_id == "emotion_repair_afternoon_reversal_kill"


def test_rule_template_selector_can_match_missing_filler_words_in_exit_phrase():
    selector = load_default_rule_template_selector()

    resolved_term = selector.resolve_term("弱转强低开无承接")

    assert resolved_term is not None
    assert resolved_term.term_id == "weak_to_strong_failed_gap_down_no_acceptance"

    matches = selector.search_templates(
        text="弱转强低开无承接",
        phase="rebalance",
        action="exit",
        available_features=[
            "position.weak_to_strong_attempted",
            "position.weak_to_strong_failed_confirmed",
            "position.next_day_gap_down_confirmed",
            "position.close_below_reclaim_pivot_ratio",
            "position.acceptance_strength_score",
        ],
        only_ready=True,
        limit=1,
    )

    assert matches
    assert matches[0].template_id == "template_exit_weak_to_strong_failed_gap_down_no_acceptance_v1"


def test_rule_template_advisor_returns_ready_suggestion_with_file_path():
    advisor = load_default_rule_template_advisor()

    response = advisor.suggest_from_text(
        "午后反杀",
        phase="signal",
        tags=["emotion_repair", "afternoon_reversal_kill"],
        available_features=[
            "market.emotion_repair_confirmed",
            "candidate.afternoon_reversal_kill_confirmed",
            "candidate.close_below_afternoon_repair_pivot_ratio",
            "candidate.repair_follow_strength_score",
        ],
        only_ready=True,
        limit=1,
    )

    assert response.resolved_term_id == "emotion_repair_afternoon_reversal_kill"
    assert response.suggestions
    suggestion = response.suggestions[0]
    assert suggestion.is_ready is True
    assert suggestion.file_name == "watch_emotion_repair_afternoon_reversal_kill.yaml"
    assert Path(suggestion.file_path).exists()
    assert suggestion.summary


def test_rule_template_advisor_reports_missing_feature_labels():
    rules_dir = Path(__file__).resolve().parents[1] / "rules"
    advisor = load_rule_template_advisor_from_files(
        rules_dir / "catalogs" / "trading_term_catalog.yaml",
        rules_dir / "catalogs" / "trading_feature_catalog.yaml",
    )

    response = advisor.suggest_from_text(
        "弱转强失败后低开无承接",
        phase="rebalance",
        action="exit",
        available_features=[
            "position.weak_to_strong_attempted",
            "position.weak_to_strong_failed_confirmed",
            "position.next_day_gap_down_confirmed",
            "position.close_below_reclaim_pivot_ratio",
        ],
        limit=1,
    )

    assert response.resolved_term_id == "weak_to_strong_failed_gap_down_no_acceptance"
    assert response.suggestions
    suggestion = response.suggestions[0]
    assert suggestion.is_ready is False
    assert suggestion.missing_features == ["position.acceptance_strength_score"]
    assert suggestion.missing_feature_labels == ["承接强度得分"]


def test_rule_template_advisor_request_can_be_serialized_to_dict_response():
    advisor = load_default_rule_template_advisor()
    request = RuleTemplateSuggestionRequest(
        text="回流尾盘走弱",
        phase="signal",
        action="block",
        available_features=[
            "candidate.consensus_reflow_confirmed",
            "candidate.tail_weakening_confirmed",
            "candidate.close_below_reflow_tail_pivot_ratio",
            "market.consensus_reflow_hold_rate",
        ],
        only_ready=True,
        limit=1,
    )

    response = advisor.suggest_templates(request)
    payload = response.to_dict()

    assert payload["query"] == "回流尾盘走弱"
    assert payload["resolved_term_id"] == "consensus_reflow_tail_weakening"
    assert payload["suggestions"]
    assert payload["suggestions"][0]["template_id"] == "template_watch_consensus_reflow_tail_weakening_v1"


def test_quant_data_manager_can_suggest_rule_templates():
    manager = QuantDataManager()

    response = manager.suggest_rule_templates(
        "午后反杀",
        phase="signal",
        tags=["emotion_repair", "afternoon_reversal_kill"],
        available_features=[
            "market.emotion_repair_confirmed",
            "candidate.afternoon_reversal_kill_confirmed",
            "candidate.close_below_afternoon_repair_pivot_ratio",
            "candidate.repair_follow_strength_score",
        ],
        only_ready=True,
        limit=1,
    )

    assert response.resolved_term_id == "emotion_repair_afternoon_reversal_kill"
    assert response.suggestions
    assert response.suggestions[0].template_id == "template_watch_emotion_repair_afternoon_reversal_kill_v1"
    assert response.suggestions[0].is_ready is True


def test_quant_data_manager_can_return_rule_template_suggestions_as_dict():
    manager = QuantDataManager()

    payload = manager.suggest_rule_templates(
        "弱转强失败后低开无承接",
        phase="rebalance",
        action="exit",
        available_features=[
            "position.weak_to_strong_attempted",
            "position.weak_to_strong_failed_confirmed",
            "position.next_day_gap_down_confirmed",
            "position.close_below_reclaim_pivot_ratio",
        ],
        limit=1,
        as_dict=True,
    )

    assert payload["resolved_term_id"] == "weak_to_strong_failed_gap_down_no_acceptance"
    assert payload["suggestions"]
    assert payload["suggestions"][0]["missing_features"] == ["position.acceptance_strength_score"]
    assert payload["suggestions"][0]["missing_feature_labels"] == ["承接强度得分"]


def test_rule_template_bridge_returns_dict_for_cpp_boundary():
    payload = suggest_rule_templates_for_bridge(
        "午后反杀",
        phase="signal",
        tags=["emotion_repair", "afternoon_reversal_kill"],
        available_features=[
            "market.emotion_repair_confirmed",
            "candidate.afternoon_reversal_kill_confirmed",
            "candidate.close_below_afternoon_repair_pivot_ratio",
            "candidate.repair_follow_strength_score",
        ],
        only_ready=True,
        limit=1,
    )

    assert payload["resolved_term_id"] == "emotion_repair_afternoon_reversal_kill"
    assert payload["suggestions"]
    assert payload["suggestions"][0]["template_id"] == "template_watch_emotion_repair_afternoon_reversal_kill_v1"


def test_rule_template_bridge_returns_json_for_cpp_boundary():
    response_json = suggest_rule_templates_from_json(
        json.dumps(
            {
                "text": "弱转强失败后低开无承接",
                "phase": "rebalance",
                "action": "exit",
                "available_features": [
                    "position.weak_to_strong_attempted",
                    "position.weak_to_strong_failed_confirmed",
                    "position.next_day_gap_down_confirmed",
                    "position.close_below_reclaim_pivot_ratio",
                ],
                "limit": 1,
            },
            ensure_ascii=False,
        )
    )
    payload = json.loads(response_json)

    assert payload["resolved_term_id"] == "weak_to_strong_failed_gap_down_no_acceptance"
    assert payload["suggestions"]
    assert payload["suggestions"][0]["missing_feature_labels"] == ["承接强度得分"]


def test_rule_template_event_bridge_publishes_response_event():
    bus = SimpleEventBus()
    bridge = RuleTemplateSuggestionEventBridge()
    bridge.initialize(bus)

    response_ready = threading.Event()
    responses = []

    def on_response(event):
        responses.append(event.data)
        response_ready.set()

    bus.subscribe(RULE_TEMPLATE_SUGGEST_RESPONSE_TOPIC, on_response)

    bus.publish(
        RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC,
        {
            "requestId": "req-001",
            "correlationId": "corr-001",
            "text": "午后反杀",
            "phase": "signal",
            "tags": ["emotion_repair", "afternoon_reversal_kill"],
            "availableFeatures": [
                "market.emotion_repair_confirmed",
                "candidate.afternoon_reversal_kill_confirmed",
                "candidate.close_below_afternoon_repair_pivot_ratio",
                "candidate.repair_follow_strength_score",
            ],
            "onlyReady": True,
            "limit": 1,
        },
    )

    assert response_ready.wait(1.0)
    assert responses
    assert responses[0]["requestId"] == "req-001"
    assert responses[0]["correlationId"] == "corr-001"
    assert responses[0]["resolvedTermId"] == "emotion_repair_afternoon_reversal_kill"
    assert responses[0]["suggestions"][0]["template_id"] == "template_watch_emotion_repair_afternoon_reversal_kill_v1"

    bridge.stop()
    bus.shutdown()


def test_rule_template_event_bridge_publishes_error_event_for_invalid_request():
    bus = SimpleEventBus()
    bridge = RuleTemplateSuggestionEventBridge()
    bridge.initialize(bus)

    error_ready = threading.Event()
    errors = []

    def on_error(event):
        errors.append(event.data)
        error_ready.set()

    bus.subscribe(RULE_TEMPLATE_SUGGEST_ERROR_TOPIC, on_error)

    bus.publish(
        RULE_TEMPLATE_SUGGEST_REQUEST_TOPIC,
        {
            "requestId": "req-err-001",
            "correlationId": "corr-err-001",
            "phase": "signal",
        },
    )

    assert error_ready.wait(1.0)
    assert errors
    assert errors[0]["requestId"] == "req-err-001"
    assert errors[0]["correlationId"] == "corr-err-001"
    assert errors[0]["errorCode"] == "rule_template_suggest_failed"
    assert errors[0]["error"] == "text is required"

    bridge.stop()
    bus.shutdown()


def test_overtake_rotation_template_produces_candidate_entry():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "entry_overtake_rotation.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "overtake_signal_confirmed": True,
                "relative_core_rank": 1,
                "relative_core_strength_score": 88,
            },
            "market": {
                "emotion_cycle": "warm",
            },
        },
    )

    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].reason_code == "overtake_rotation_candidate"
    assert matched[0].payload["entry_style"] == "overtake_rotation"


def test_failed_rebound_engulfing_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_failed_rebound_engulfing.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "failed_engulfing_confirmed": True,
                "acceptance_strength_score": 32,
                "intraday_pullback_percent": 4.6,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "failed_rebound_engulfing_exit"


def test_high_divergence_weakening_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_high_divergence_weakening.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "high_divergence_confirmed": True,
                "relative_core_strength_score": 52,
                "close_below_reference_ratio": 0.985,
            },
            "market": {
                "high_level_divergence_rate": 0.36,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "high_divergence_weakening_block"


def test_broken_board_failed_rebound_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_broken_board_failed_rebound.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "board_break_confirmed": True,
                "rebound_attempt_failed": True,
                "close_below_intraday_reclaim_ratio": 0.97,
                "acceptance_strength_score": 41,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "broken_board_failed_rebound_exit"


def test_emotion_reflow_repair_template_produces_candidate_entry():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "entry_emotion_reflow_repair.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "core_theme_reflow_rank": 2,
                "early_repair_strength_score": 81,
                "breakout_after_repair_ratio": 1.01,
            },
            "market": {
                "repair_reflow_confirmed": True,
                "core_theme_return_rate": 0.51,
            },
        },
    )

    matched = [item for item in results if item.matched]
    assert matched
    assert matched[0].reason_code == "emotion_reflow_repair_candidate"
    assert matched[0].payload["entry_style"] == "emotion_reflow_repair"


def test_consensus_acceleration_exhaustion_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_consensus_acceleration_exhaustion.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "consensus_acceleration_confirmed": True,
                "intraday_chase_saturation_score": 89,
                "first_divergence_pullback_ratio": 0.034,
            },
            "market": {
                "high_consensus_collapse_rate": 0.21,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "consensus_acceleration_exhaustion_block"


def test_floor_to_limit_failed_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_floor_to_limit_failed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "floor_to_limit_attempted": True,
                "limit_reseal_failed": True,
                "close_below_limit_reclaim_ratio": 0.975,
                "acceptance_strength_score": 44,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "floor_to_limit_failed_exit"


def test_tail_ramp_next_day_weakening_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_tail_ramp_next_day_weakening.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "tail_ramp_attack_confirmed": True,
                "next_day_open_strength_ratio": 0.991,
                "next_day_volume_follow_ratio": 0.76,
                "next_day_red_to_black_failed": False,
            },
            "market": {
                "tail_attack_follow_through_rate": 0.41,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "tail_ramp_next_day_weakening_block"


def test_thin_volume_rebound_failed_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_thin_volume_rebound_failed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "thin_volume_rebound_attempted": True,
                "rebound_confirmation_failed": True,
                "close_below_rebound_pivot_ratio": 0.982,
                "volume_recovery_ratio": 0.76,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "thin_volume_rebound_failed_exit"


def test_afternoon_chase_then_fade_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_afternoon_chase_then_fade.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "afternoon_chase_confirmed": True,
                "afternoon_fade_drawdown_ratio": 0.031,
                "close_below_afternoon_attack_ratio": 0.994,
            },
            "market": {
                "afternoon_follow_through_rate": 0.41,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "afternoon_chase_then_fade_block"


def test_counter_nuke_confirmation_failed_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_counter_nuke_confirmation_failed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "counter_nuke_attempted": True,
                "counter_nuke_confirmation_ratio": 0.993,
                "bid_acceptance_score": 48,
            },
            "market": {
                "counter_nuke_success_rate": 0.37,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "counter_nuke_confirmation_failed_block"


def test_afternoon_reseal_failed_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_afternoon_reseal_failed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "afternoon_reseal_attempted": True,
                "reseal_hold_minutes": 12,
                "close_below_reseal_pivot_ratio": 0.996,
            },
            "market": {
                "afternoon_reseal_success_rate": 0.37,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "afternoon_reseal_failed_block"


def test_first_board_next_day_weak_to_weaker_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_first_board_next_day_weak_to_weaker.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "first_board_yesterday_confirmed": True,
                "next_day_open_below_expected_ratio": 0.992,
                "next_day_follow_through_strength_score": 43,
                "next_day_weak_to_weaker_confirmed": False,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "first_board_next_day_weak_to_weaker_block"


def test_low_volume_false_repair_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_low_volume_false_repair.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "low_volume_repair_attempted": True,
                "repair_confirmation_failed": True,
                "repair_breakout_ratio": 0.991,
                "volume_recovery_ratio": 0.78,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "low_volume_false_repair_exit"


def test_one_word_open_board_weakening_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_one_word_open_board_weakening.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "one_word_board_yesterday_confirmed": True,
                "open_board_today_confirmed": True,
                "open_board_acceptance_score": 49,
                "close_below_open_board_pivot_ratio": 0.997,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "one_word_open_board_weakening_block"


def test_engulfing_next_day_fade_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_engulfing_next_day_fade.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "engulfing_yesterday_confirmed": True,
                "next_day_spike_then_fade_confirmed": True,
                "close_below_engulfing_support_ratio": 0.991,
                "acceptance_strength_score": 46,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "engulfing_next_day_fade_exit"


def test_reseal_board_break_loss_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_reseal_board_break_loss.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "reseal_success_confirmed": True,
                "second_board_break_confirmed": True,
                "close_below_reseal_support_ratio": 0.994,
                "acceptance_strength_score": 43,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "reseal_board_break_loss_exit"


def test_engulfing_first_down_day_confirmed_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_engulfing_first_down_day_confirmed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "engulfing_yesterday_confirmed": True,
                "first_down_day_confirmed": True,
                "close_below_engulfing_support_ratio": 0.993,
                "selling_pressure_score": 76,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "engulfing_first_down_day_exit"


def test_gap_up_fade_breakdown_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_gap_up_fade_breakdown.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "gap_up_open_confirmed": True,
                "intraday_fade_from_open_ratio": 0.034,
                "close_below_gap_attack_ratio": 0.996,
            },
            "market": {
                "gap_up_follow_through_rate": 0.41,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "gap_up_fade_breakdown_block"


def test_acceleration_volume_stall_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_acceleration_volume_stall.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "acceleration_phase_confirmed": True,
                "volume_expansion_ratio": 2.1,
                "price_progress_stall_ratio": 0.992,
                "acceptance_strength_score": 47,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "acceleration_volume_stall_exit"


def test_spike_fail_before_limit_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_spike_fail_before_limit.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "intraday_spike_attack_confirmed": True,
                "failed_to_limit_board_confirmed": True,
                "pullback_from_intraday_high_ratio": 0.036,
                "close_below_intraday_attack_ratio": 0.995,
            },
            "market": {
                "spike_to_limit_success_rate": 0.29,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "spike_fail_before_limit_block"


def test_second_wave_repair_failed_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_second_wave_repair_failed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "second_wave_repair_attempted": True,
                "second_wave_breakout_ratio": 0.994,
                "repair_follow_through_failed": True,
                "volume_recovery_ratio": 0.74,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "second_wave_repair_failed_exit"


def test_intraday_break_ma_weakening_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_intraday_break_ma_weakening.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "intraday_ma_break_confirmed": True,
                "intraday_ma_reclaim_failed": True,
                "close_below_intraday_ma_ratio": 0.996,
            },
            "market": {
                "intraday_trend_hold_rate": 0.38,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "intraday_break_ma_weakening_block"


def test_high_level_sideways_flush_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_high_level_sideways_flush.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "high_level_sideways_confirmed": True,
                "intraday_flush_confirmed": True,
                "flush_from_sideways_high_ratio": 0.052,
                "close_below_sideways_pivot_ratio": 0.994,
                "selling_pressure_score": 79,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "high_level_sideways_flush_exit"


def test_low_volume_board_next_day_breakdown_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_low_volume_board_next_day_breakdown.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "low_volume_board_yesterday_confirmed": True,
                "next_day_open_below_board_expectation_ratio": 0.993,
                "close_below_board_support_ratio": 0.996,
            },
            "market": {
                "low_volume_board_follow_through_rate": 0.31,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "low_volume_board_next_day_breakdown_block"


def test_tail_repair_no_follow_through_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_tail_repair_no_follow_through.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "tail_repair_attempt_confirmed": True,
                "next_day_repair_follow_ratio": 0.78,
                "next_day_close_below_repair_pivot_ratio": 0.996,
            },
            "market": {
                "tail_repair_success_rate": 0.34,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "tail_repair_no_follow_through_block"


def test_high_volume_stall_reversal_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_high_volume_stall_reversal.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "high_volume_stall_confirmed": True,
                "price_progress_stall_ratio": 0.993,
                "close_below_stall_pivot_ratio": 0.995,
                "selling_pressure_score": 77,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "high_volume_stall_reversal_exit"


def test_rebound_over_previous_high_failed_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_rebound_over_previous_high_failed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "rebound_over_previous_high_attempted": True,
                "previous_high_breakout_ratio": 0.996,
                "breakout_hold_failed": True,
                "acceptance_strength_score": 45,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "rebound_over_previous_high_failed_exit"


def test_afternoon_reflow_next_day_below_expectation_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_afternoon_reflow_next_day_below_expectation.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "afternoon_reflow_confirmed": True,
                "next_day_open_below_reflow_expectation_ratio": 0.992,
                "next_day_close_below_reflow_pivot_ratio": 0.996,
            },
            "market": {
                "afternoon_reflow_follow_through_rate": 0.35,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "afternoon_reflow_next_day_below_expectation_block"


def test_board_fade_tail_breakdown_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_board_fade_tail_breakdown.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "board_break_after_limit_attempted": True,
                "tail_breakdown_confirmed": True,
                "close_below_board_pivot_ratio": 0.995,
                "acceptance_strength_score": 43,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "board_fade_tail_breakdown_exit"


def test_weak_repair_next_day_gap_down_kill_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_weak_repair_next_day_gap_down_kill.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "weak_repair_confirmed": True,
                "next_day_gap_down_confirmed": True,
                "next_day_close_below_repair_support_ratio": 0.994,
                "selling_pressure_score": 78,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "weak_repair_next_day_gap_down_kill_exit"


def test_sector_reflow_symbol_lagging_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_sector_reflow_symbol_lagging.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "sector_relative_lag_rank": 8,
                "reflow_follow_strength_score": 46,
                "close_below_reflow_reference_ratio": 0.996,
            },
            "market": {
                "sector_reflow_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "sector_reflow_symbol_lagging_block"


def test_gap_up_instant_limit_acceptance_collapse_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_gap_up_instant_limit_acceptance_collapse.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "gap_up_instant_limit_confirmed": True,
                "instant_limit_open_board_confirmed": True,
                "acceptance_collapse_confirmed": True,
                "close_below_instant_limit_pivot_ratio": 0.996,
            },
            "market": {
                "instant_limit_follow_through_rate": 0.28,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "gap_up_instant_limit_acceptance_collapse_block"


def test_low_level_first_board_no_premium_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_low_level_first_board_no_premium.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "low_level_first_board_confirmed": True,
                "next_day_open_premium_ratio": 0.992,
                "next_day_close_below_first_board_support_ratio": 0.996,
            },
            "market": {
                "first_board_premium_rate": 0.33,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "low_level_first_board_no_premium_block"


def test_sector_divergence_leader_follower_split_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_sector_divergence_leader_follower_split.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "leader_follower_divergence_score": 74,
                "follow_strength_vs_leader_ratio": 0.61,
                "close_below_divergence_reference_ratio": 0.996,
            },
            "market": {
                "sector_divergence_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "sector_divergence_leader_follower_split_block"


def test_one_word_turnover_acceptance_decay_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_one_word_turnover_acceptance_decay.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "one_word_turnover_open_confirmed": True,
                "turnover_acceptance_decay_score": 76,
                "close_below_turnover_pivot_ratio": 0.996,
            },
            "market": {
                "one_word_turnover_success_rate": 0.29,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "one_word_turnover_acceptance_decay_block"


def test_board_pullback_next_day_gap_down_confirmed_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_board_pullback_next_day_gap_down_confirmed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "board_pullback_failed_confirmed": True,
                "next_day_gap_down_confirmed": True,
                "close_below_pullback_support_ratio": 0.995,
                "acceptance_strength_score": 44,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "board_pullback_next_day_gap_down_confirmed_exit"


def test_sector_repair_leader_only_followers_stall_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_sector_repair_leader_only_followers_stall.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "leader_only_repair_gap_score": 73,
                "follower_stall_strength_ratio": 0.66,
                "close_below_repair_follow_reference_ratio": 0.996,
            },
            "market": {
                "sector_repair_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "sector_repair_leader_only_followers_stall_block"


def test_high_level_board_break_afternoon_second_kill_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_high_level_board_break_afternoon_second_kill.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "high_level_board_break_confirmed": True,
                "afternoon_second_kill_confirmed": True,
                "close_below_afternoon_second_kill_pivot_ratio": 0.995,
                "selling_pressure_score": 81,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "high_level_board_break_afternoon_second_kill_exit"


def test_weak_to_strong_fail_consensus_take_profit_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_weak_to_strong_fail_consensus_take_profit.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "weak_to_strong_attempted": True,
                "weak_to_strong_failed_confirmed": True,
                "consensus_take_profit_confirmed": True,
                "close_below_reclaim_pivot_ratio": 0.996,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "weak_to_strong_fail_consensus_take_profit_exit"


def test_repair_market_core_secondary_switch_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_repair_market_core_secondary_switch.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "secondary_core_switch_confirmed": True,
                "relative_core_rank": 4,
                "close_below_core_switch_reference_ratio": 0.996,
            },
            "market": {
                "repair_market_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "repair_market_core_secondary_switch_block"


def test_consensus_repair_next_day_acceptance_vanish_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_consensus_repair_next_day_acceptance_vanish.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "consensus_repair_confirmed": True,
                "next_day_acceptance_vanish_confirmed": True,
                "close_below_repair_acceptance_pivot_ratio": 0.996,
            },
            "market": {
                "consensus_repair_follow_through_rate": 0.33,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "consensus_repair_next_day_acceptance_vanish_block"


def test_accelerated_catch_up_afternoon_blowup_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_accelerated_catch_up_afternoon_blowup.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "accelerated_catch_up_confirmed": True,
                "afternoon_blowup_confirmed": True,
                "close_below_catch_up_pivot_ratio": 0.995,
                "acceptance_strength_score": 43,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "accelerated_catch_up_afternoon_blowup_exit"


def test_cooling_end_counter_nuke_failed_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_cooling_end_counter_nuke_failed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "counter_nuke_attempted": True,
                "counter_nuke_confirmation_ratio": 0.994,
                "bid_acceptance_score": 47,
            },
            "market": {
                "cooling_end_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "cooling_end_counter_nuke_failed_block"


def test_engulfing_board_blowup_take_profit_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_engulfing_board_blowup_take_profit.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "engulfing_board_attempt_confirmed": True,
                "board_blowup_take_profit_confirmed": True,
                "close_below_engulfing_board_pivot_ratio": 0.995,
                "selling_pressure_score": 79,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "engulfing_board_blowup_take_profit_exit"


def test_emotion_repair_second_divergence_failed_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_emotion_repair_second_divergence_failed.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "second_divergence_failed_confirmed": True,
                "repair_strength_drop_ratio": 0.68,
                "close_below_repair_divergence_pivot_ratio": 0.996,
            },
            "market": {
                "emotion_repair_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "emotion_repair_second_divergence_failed_block"


def test_cooling_tail_low_level_first_board_follow_insufficient_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_cooling_tail_low_level_first_board_follow_insufficient.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "low_level_first_board_confirmed": True,
                "low_level_first_board_follow_ratio": 0.74,
                "close_below_low_level_first_board_support_ratio": 0.996,
            },
            "market": {
                "cooling_tail_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "cooling_tail_low_level_first_board_follow_insufficient_block"


def test_consensus_reflow_tail_weakening_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_consensus_reflow_tail_weakening.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "consensus_reflow_confirmed": True,
                "tail_weakening_confirmed": True,
                "close_below_reflow_tail_pivot_ratio": 0.996,
            },
            "market": {
                "consensus_reflow_hold_rate": 0.34,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "consensus_reflow_tail_weakening_block"


def test_overtake_success_next_day_no_strengthening_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_overtake_success_next_day_no_strengthening.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "overtake_signal_confirmed": True,
                "next_day_strengthening_ratio": 0.97,
                "close_below_overtake_pivot_ratio": 0.996,
                "relative_core_strength_score": 57,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "overtake_success_next_day_no_strengthening_block"


def test_cooling_mid_weak_repair_rebreak_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_cooling_mid_weak_repair_rebreak.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "weak_repair_confirmed": True,
                "rebreak_after_weak_repair_confirmed": True,
                "close_below_weak_repair_pivot_ratio": 0.995,
            },
            "market": {
                "cooling_mid_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "cooling_mid_weak_repair_rebreak_exit"


def test_high_level_blowup_next_day_thin_volume_drift_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_high_level_blowup_next_day_thin_volume_drift.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "high_level_blowup_confirmed": True,
                "next_day_thin_volume_confirmed": True,
                "close_below_blowup_support_ratio": 0.996,
            },
            "market": {
                "high_level_blowup_repair_rate": 0.31,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "high_level_blowup_next_day_thin_volume_drift_block"


def test_emotion_repair_afternoon_reversal_kill_template_blocks_watch():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "watch_emotion_repair_afternoon_reversal_kill.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "signal",
        {
            "candidate": {
                "afternoon_reversal_kill_confirmed": True,
                "close_below_afternoon_repair_pivot_ratio": 0.996,
                "repair_follow_strength_score": 48,
            },
            "market": {
                "emotion_repair_confirmed": True,
            },
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.BLOCK
    assert results[0].reason_code == "emotion_repair_afternoon_reversal_kill_block"


def test_weak_to_strong_failed_gap_down_no_acceptance_template_produces_exit():
    rule_set = load_rule_set_from_file(
        Path(__file__).resolve().parents[1] / "rules" / "examples" / "exit_weak_to_strong_failed_gap_down_no_acceptance.yaml"
    )

    engine = RuleEngine()
    results = engine.evaluate_stage(
        rule_set,
        "rebalance",
        {
            "position": {
                "weak_to_strong_attempted": True,
                "weak_to_strong_failed_confirmed": True,
                "next_day_gap_down_confirmed": True,
                "close_below_reclaim_pivot_ratio": 0.996,
                "acceptance_strength_score": 46,
            }
        },
    )

    assert results
    assert results[0].matched is True
    assert results[0].result_type == RuleResultType.EXIT
    assert results[0].reason_code == "weak_to_strong_failed_gap_down_no_acceptance_exit"
