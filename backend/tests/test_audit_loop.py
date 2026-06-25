import pytest

from app.agents.audit_loop import createFixedCriteria, selectWorstCriterion
from app.schemas import AuditEvaluation, AuditIteration, AuditReport, CriterionEvaluation
from app.services.consume import _audit_loop_details


def test_fixed_criteria_include_required_rubric_items() -> None:
    criteria = createFixedCriteria()
    ids = {criterion.id for criterion in criteria}

    assert {
        "coverage",
        "hallucination",
        "fluff",
        "structure",
        "specificity",
    }.issubset(ids)
    assert all(criterion.weight > 0 for criterion in criteria)


def test_select_worst_criterion_uses_weighted_deficit() -> None:
    evaluation = AuditEvaluation(
        weighted_score=80,
        criteria=[
            CriterionEvaluation(
                criterion_id="low_weight_low_score",
                weight=0.5,
                score=50,
                weighted_deficit=25,
            ),
            CriterionEvaluation(
                criterion_id="high_weight_mid_score",
                weight=1.5,
                score=70,
                weighted_deficit=45,
            ),
        ],
    )

    assert selectWorstCriterion(evaluation).criterion_id == "high_weight_mid_score"


def test_select_worst_criterion_rejects_empty_evaluation() -> None:
    with pytest.raises(Exception):
        selectWorstCriterion(AuditEvaluation(weighted_score=0, criteria=[]))


def test_audit_loop_details_show_call_counts_and_iteration_deltas() -> None:
    report = AuditReport(
        initial_score=70,
        final_score=88,
        target_score=85,
        iterations=[
            AuditIteration(
                iteration=1,
                criterion_id="coverage",
                before_score=70,
                after_score=82,
                improvement=12,
                issues=["Missed the named three-step process."],
                smallest_repair="Add the missing process steps.",
            ),
            AuditIteration(
                iteration=2,
                criterion_id="specificity",
                before_score=82,
                after_score=88,
                improvement=6,
            ),
        ],
        final_evaluation=AuditEvaluation(
            weighted_score=88,
            criteria=[
                CriterionEvaluation(
                    criterion_id="coverage",
                    score=90,
                    weighted_deficit=10,
                )
            ],
        ),
        stopped_reason="target_score",
    )

    details = _audit_loop_details(report)

    assert "Planner ran 1x: built 0 total criteria." in details
    assert "Evaluator ran 3x: initial evaluation plus one re-check per patch." in details
    assert "Patcher ran 2x." in details
    assert (
        "Iteration 1: patched coverage; 70.0 -> 82.0 (+12.0). "
        "Issue: Missed the named three-step process. "
        "Repair: Add the missing process steps."
    ) in details
    assert (
        "Iteration 2: patched specificity; 82.0 -> 88.0 (+6.0). "
        "Issue: No issue text returned. Repair: No repair text returned."
    ) in details
