"""Prompt builders for the distillation audit loop."""

import json

from app.schemas.analysis import AuditCriterion, CriterionEvaluation


AUDIT_PLANNER_SYSTEM = (
    "You plan compact evaluation rubrics for source-grounded distillation. "
    "Return strict JSON only."
)

AUDIT_EVALUATOR_SYSTEM = (
    "You are an evaluator. Do not rewrite the output. Be strict, concrete, "
    "and source-grounded. Return strict JSON only."
)

AUDIT_PATCHER_SYSTEM = (
    "You are a patcher. Make the smallest useful edit for one failed criterion. "
    "Preserve good parts and never add unsupported claims. Return strict JSON only."
)


def audit_planner_prompt(source_text: str, user_goal: str) -> str:
    payload = {
        "source_text": source_text,
        "user_goal": user_goal,
    }
    return (
        "Create 3 to 6 dynamic criteria for evaluating this specific distillation task.\n"
        "Use criteria that complement coverage, hallucination, fluff, structure, "
        "specificity, chapter quality, highlight quality, and timestamp integrity. "
        "Prefer source-specific needs: named entities, counts/lists, technical precision, "
        "audience fit, caveats, chronology, or actionability.\n"
        "Return exactly this JSON shape:\n"
        "{\n"
        '  "criteria": [\n'
        "    {\n"
        '      "id": "short_snake_case_id",\n'
        '      "name": "Short name",\n'
        '      "description": "what this output must do for this source and goal",\n'
        '      "weight": 1.0\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Weights must be between 0.6 and 1.4. Do not repeat fixed criteria.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def audit_evaluator_prompt(
    source_text: str,
    user_goal: str,
    output: str,
    criteria: list[AuditCriterion],
) -> str:
    payload = {
        "source_text": source_text,
        "user_goal": user_goal,
        "current_output": output,
        "criteria": [
            {
                "criterion_id": criterion.id,
                "name": criterion.name,
                "description": criterion.description,
                "weight": criterion.weight,
            }
            for criterion in criteria
        ],
    }
    return (
        "Score the current output against every criterion from 0 to 100.\n"
        "For each criterion return exact problems and the smallest repair. "
        "If a criterion is strong, issues may be empty and smallest_repair can be empty.\n"
        "weighted_score must be the weighted average of criterion scores.\n"
        "Return exactly this JSON shape:\n"
        "{\n"
        '  "criteria": [\n'
        "    {\n"
        '      "criterion_id": "id from rubric",\n'
        '      "score": 82,\n'
        '      "issues": ["exact problem grounded in source/output"],\n'
        '      "smallest_repair": "smallest useful edit"\n'
        "    }\n"
        "  ],\n"
        '  "weighted_score": 82\n'
        "}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def audit_patcher_prompt(
    source_text: str,
    user_goal: str,
    output: str,
    failed_criterion: CriterionEvaluation,
) -> str:
    payload = {
        "source_text": source_text,
        "user_goal": user_goal,
        "current_output": output,
        "failed_criterion": {
            "criterion_id": failed_criterion.criterion_id,
            "name": failed_criterion.name,
            "description": failed_criterion.description,
            "score": failed_criterion.score,
            "issues": failed_criterion.issues,
            "smallest_repair": failed_criterion.smallest_repair,
        },
    }
    return (
        "Patch only the failed criterion. Do not rewrite everything. Preserve good parts, "
        "format, order, and supported claims unless they directly cause the failure.\n"
        "Return exactly this JSON shape:\n"
        "{\n"
        '  "patched_output": "the patched output only"\n'
        "}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )
