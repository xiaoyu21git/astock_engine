from __future__ import annotations

from typing import Any

from .models import RuleDefinition
from .models import RuleEvaluation
from .models import RuleResultType
from .models import RuleSetDefinition
from .models import RuleStage
from .operators import ExpressionEvaluator


TERMINAL_RESULTS = {RuleResultType.BLOCK, RuleResultType.STATE_SWITCH}


class RuleEngine:
    def __init__(self, operators: dict[str, Any] | None = None) -> None:
        self._evaluator = ExpressionEvaluator(operators)

    def evaluate_rule(self, rule: RuleDefinition, context: dict[str, Any]) -> RuleEvaluation:
        if not rule.enabled:
            return RuleEvaluation(
                rule_id=rule.rule_id,
                stage=rule.stage,
                priority=rule.priority,
                matched=False,
                enabled=False,
            )

        matched = True if rule.when is None else bool(self._evaluator.evaluate(rule.when, context))
        if not matched:
            return RuleEvaluation(
                rule_id=rule.rule_id,
                stage=rule.stage,
                priority=rule.priority,
                matched=False,
                enabled=True,
            )

        return RuleEvaluation(
            rule_id=rule.rule_id,
            stage=rule.stage,
            priority=rule.priority,
            matched=True,
            enabled=True,
            result_type=rule.action.result_type,
            reason_code=rule.action.reason_code,
            message=rule.action.message,
            payload=self._evaluator.render(rule.action.payload, context),
            score=self._evaluator.render(rule.action.score, context) if rule.action.score is not None else None,
            state=self._evaluator.render(rule.action.state, context) if rule.action.state is not None else None,
        )

    def evaluate_stage(
        self,
        rule_set: RuleSetDefinition,
        stage: RuleStage | str,
        context: dict[str, Any],
        stop_on_terminal: bool = True,
    ) -> list[RuleEvaluation]:
        stage_enum = stage if isinstance(stage, RuleStage) else RuleStage(str(stage).strip().lower())
        evaluations: list[RuleEvaluation] = []

        stage_rules = sorted(
            (rule for rule in rule_set.rules if rule.stage == stage_enum),
            key=lambda item: item.priority,
            reverse=True,
        )

        for rule in stage_rules:
            evaluation = self.evaluate_rule(rule, context)
            evaluations.append(evaluation)
            if stop_on_terminal and evaluation.matched and evaluation.result_type in TERMINAL_RESULTS:
                break

        return evaluations

    def evaluate_pipeline(
        self,
        rule_set: RuleSetDefinition,
        context: dict[str, Any],
        stages: list[RuleStage | str] | None = None,
        stop_on_terminal: bool = True,
    ) -> dict[str, list[RuleEvaluation]]:
        ordered_stages = stages or [
            RuleStage.MARKET,
            RuleStage.ELIGIBILITY,
            RuleStage.SIGNAL,
            RuleStage.PORTFOLIO,
            RuleStage.REBALANCE,
            RuleStage.EXECUTION,
            RuleStage.ACCOUNT_RISK,
        ]

        results: dict[str, list[RuleEvaluation]] = {}
        for stage in ordered_stages:
            stage_enum = stage if isinstance(stage, RuleStage) else RuleStage(str(stage).strip().lower())
            stage_results = self.evaluate_stage(rule_set, stage_enum, context, stop_on_terminal=stop_on_terminal)
            results[stage_enum.value] = stage_results
            if stop_on_terminal and any(item.matched and item.result_type in TERMINAL_RESULTS for item in stage_results):
                break

        return results