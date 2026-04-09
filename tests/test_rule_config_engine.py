from astock_engine.rules import RuleEngine
from astock_engine.rules import RuleResultType
from astock_engine.rules import load_rule_set_from_mapping


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