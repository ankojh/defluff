"""Planner -> evaluator -> patcher loop for improving distilled outputs."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.base import BaseLLMAgent
from app.agents.errors import AnalysisError
from app.agents.parsing import _load_ollama_json
from app.agents.prompts.audit import (
    AUDIT_EVALUATOR_SYSTEM,
    AUDIT_PATCHER_SYSTEM,
    AUDIT_PLANNER_SYSTEM,
    audit_evaluator_prompt,
    audit_patcher_prompt,
    audit_planner_prompt,
)
from app.core.config import settings
from app.schemas.analysis import (
    AuditCriterion,
    AuditEvaluation,
    AuditIteration,
    AuditLoopResult,
    AuditReport,
    AuditScoreSnapshot,
    CriterionEvaluation,
    LocalModelUsage,
    LocalModelUsageByPurpose,
)

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)
AuditProgressCallback = Callable[[str, str, list[str]], Awaitable[None]]
AuditOutputCallback = Callable[[str, AuditEvaluation], Awaitable[None]]


class _DynamicCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    weight: float = Field(ge=0.6, le=1.4)


class _DynamicCriteriaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[_DynamicCriterion] = Field(min_length=3, max_length=6)


class _EvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[CriterionEvaluation] = Field(min_length=1)
    weighted_score: float = Field(ge=0.0, le=100.0)


class _PatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patched_output: str = Field(min_length=1)


class AuditLoopOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_score: float = Field(default=90.0, ge=0.0, le=100.0)
    min_improvement: float = Field(default=2.0, ge=0.0, le=100.0)
    max_iterations: int = Field(default=3, ge=0, le=8)
    num_predict: int | None = Field(default=None, ge=256)
    planner_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    evaluator_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    patcher_temperature: float = Field(default=0.1, ge=0.0, le=1.0)


class AuditLoopAgent(BaseLLMAgent):
    async def plan_dynamic_criteria(
        self,
        source_text: str,
        user_goal: str,
        options: AuditLoopOptions | None = None,
    ) -> list[AuditCriterion]:
        return await planDynamicCriteria(source_text, user_goal, self, options)

    async def evaluate_output(
        self,
        source_text: str,
        user_goal: str,
        output: str,
        criteria: list[AuditCriterion],
        options: AuditLoopOptions | None = None,
    ) -> AuditEvaluation:
        return await evaluateOutput(source_text, user_goal, output, criteria, self, options)

    async def patch_output(
        self,
        source_text: str,
        user_goal: str,
        output: str,
        failed_criterion: CriterionEvaluation,
        options: AuditLoopOptions | None = None,
    ) -> str:
        return await patchOutput(source_text, user_goal, output, failed_criterion, self, options)

    async def run(
        self,
        source_text: str,
        user_goal: str,
        initial_output: str,
        options: AuditLoopOptions | None = None,
        progress: AuditProgressCallback | None = None,
        output_progress: AuditOutputCallback | None = None,
    ) -> AuditLoopResult:
        return await runAuditLoop(
            source_text,
            user_goal,
            initial_output,
            options,
            self,
            progress,
            output_progress,
        )


def createFixedCriteria() -> list[AuditCriterion]:
    """Create Defluff's stable rubric for every distillation audit."""
    return [
        AuditCriterion(
            id="coverage",
            name="Coverage",
            description="Important source claims, distinctions, examples, counts, and conclusions are preserved.",
            weight=1.25,
            source="fixed",
        ),
        AuditCriterion(
            id="hallucination",
            name="Hallucination",
            description="The output does not invent claims, causal links, numbers, sources, or advice unsupported by the source text.",
            weight=1.45,
            source="fixed",
        ),
        AuditCriterion(
            id="fluff",
            name="Fluff",
            description="Low-value, repetitive, teaser-like, or generic sentences are removed.",
            weight=1.0,
            source="fixed",
        ),
        AuditCriterion(
            id="structure",
            name="Structure",
            description="The output is logically ordered, easy to scan, and uses the right fields for summary, flow, context, and takeaways.",
            weight=1.0,
            source="fixed",
        ),
        AuditCriterion(
            id="specificity",
            name="Specificity",
            description="The output uses concrete nouns, mechanisms, examples, and source terms instead of vague generic statements.",
            weight=1.1,
            source="fixed",
        ),
        AuditCriterion(
            id="density",
            name="Information density",
            description="Each sentence or bullet earns its place by carrying distinct meaning without bloating the output.",
            weight=0.9,
            source="fixed",
        ),
        AuditCriterion(
            id="goal_fit",
            name="Goal fit",
            description="The output serves the user's requested distillation goal and suppresses details that do not help that goal.",
            weight=1.0,
            source="fixed",
        ),
        AuditCriterion(
            id="reader_utility",
            name="Reader utility",
            description="The result gives a reader useful recall handles: key takeaways, caveats, definitions, or next questions where appropriate.",
            weight=0.85,
            source="fixed",
        ),
        AuditCriterion(
            id="chapter_quality",
            name="Chapter quality",
            description="Chapters have useful titles, grounded summaries, sensible granularity, and preserve the source order.",
            weight=0.95,
            source="fixed",
        ),
        AuditCriterion(
            id="highlight_quality",
            name="Highlight quality",
            description="Highlights capture distinct, useful revisit moments with specific labels, grounded summaries, and clear reasons.",
            weight=1.05,
            source="fixed",
        ),
        AuditCriterion(
            id="timestamp_integrity",
            name="Timestamp integrity",
            description="Timed chapters and highlights use valid source-supported ranges, remain ordered, and avoid contradictory or overlapping navigation.",
            weight=1.15,
            source="fixed",
        ),
    ]


async def planDynamicCriteria(
    sourceText: str,
    userGoal: str,
    agent: BaseLLMAgent | None = None,
    options: AuditLoopOptions | None = None,
) -> list[AuditCriterion]:
    """Ask the LLM planner for source-specific criteria."""
    agent = agent or AuditLoopAgent()
    options = options or AuditLoopOptions()
    response = await _chat_validated(
        agent,
        model=_DynamicCriteriaResponse,
        system=AUDIT_PLANNER_SYSTEM,
        prompt=audit_planner_prompt(sourceText, userGoal),
        purpose="audit dynamic criteria",
        num_predict=options.num_predict or min(settings.analysis_num_predict, 2048),
        temperature=options.planner_temperature,
    )

    criteria: list[AuditCriterion] = []
    seen = {criterion.id for criterion in createFixedCriteria()}
    for item in response.criteria:
        if item.id in seen:
            continue
        seen.add(item.id)
        criteria.append(
            AuditCriterion(
                id=item.id,
                name=item.name,
                description=item.description,
                weight=item.weight,
                source="dynamic",
            )
        )

    if len(criteria) < 3:
        raise AnalysisError("Audit planner returned fewer than 3 non-duplicate criteria")
    return criteria[:6]


async def evaluateOutput(
    sourceText: str,
    userGoal: str,
    output: str,
    criteria: list[AuditCriterion],
    agent: BaseLLMAgent | None = None,
    options: AuditLoopOptions | None = None,
) -> AuditEvaluation:
    """Evaluate one output against the merged rubric."""
    if not criteria:
        raise AnalysisError("Audit evaluation requires at least one criterion")

    agent = agent or AuditLoopAgent()
    options = options or AuditLoopOptions()
    response = await _chat_validated(
        agent,
        model=_EvaluationResponse,
        system=AUDIT_EVALUATOR_SYSTEM,
        prompt=audit_evaluator_prompt(sourceText, userGoal, output, criteria),
        purpose="audit evaluation",
        num_predict=options.num_predict or settings.analysis_num_predict,
        temperature=options.evaluator_temperature,
    )
    return _normalize_evaluation(response, criteria)


def selectWorstCriterion(evaluation: AuditEvaluation) -> CriterionEvaluation:
    """Pick the criterion with the largest weighted deficit."""
    if not evaluation.criteria:
        raise AnalysisError("Cannot select a failed criterion from an empty evaluation")

    return max(
        evaluation.criteria,
        key=lambda item: (item.weighted_deficit, 100.0 - item.score, item.weight),
    )


async def patchOutput(
    sourceText: str,
    userGoal: str,
    output: str,
    failedCriterion: CriterionEvaluation,
    agent: BaseLLMAgent | None = None,
    options: AuditLoopOptions | None = None,
) -> str:
    """Ask the LLM patcher for the smallest edit targeting one failed criterion."""
    agent = agent or AuditLoopAgent()
    options = options or AuditLoopOptions()
    response = await _chat_validated(
        agent,
        model=_PatchResponse,
        system=AUDIT_PATCHER_SYSTEM,
        prompt=audit_patcher_prompt(sourceText, userGoal, output, failedCriterion),
        purpose="audit patch",
        num_predict=options.num_predict or settings.analysis_num_predict,
        temperature=options.patcher_temperature,
    )
    return response.patched_output.strip()


async def runAuditLoop(
    sourceText: str,
    userGoal: str,
    initialOutput: str,
    options: AuditLoopOptions | None = None,
    agent: BaseLLMAgent | None = None,
    progress: AuditProgressCallback | None = None,
    output_progress: AuditOutputCallback | None = None,
) -> AuditLoopResult:
    """Run planner -> evaluator -> patcher until target, stall, or iteration cap."""
    agent = agent or AuditLoopAgent()
    options = options or AuditLoopOptions()

    logger.info(
        "audit.loop_start source_chars=%d output_chars=%d max_iterations=%d target_score=%.1f",
        len(sourceText),
        len(initialOutput),
        options.max_iterations,
        options.target_score,
    )
    await _emit_progress(
        progress,
        "running",
        "Planning source-specific audit criteria.",
        [f"Target score: {options.target_score:.0f}", f"Max iterations: {options.max_iterations}"],
    )
    fixed_criteria = createFixedCriteria()
    dynamic_criteria = await planDynamicCriteria(sourceText, userGoal, agent, options)
    criteria = _dedupe_criteria([*fixed_criteria, *dynamic_criteria])

    output = initialOutput
    await _emit_progress(
        progress,
        "running",
        "Evaluating the current distillation against the rubric.",
        [
            f"{len(fixed_criteria)} fixed criteria",
            f"{len(dynamic_criteria)} dynamic criteria",
        ],
    )
    evaluation = await evaluateOutput(sourceText, userGoal, output, criteria, agent, options)
    initial_score = evaluation.weighted_score
    iterations: list[AuditIteration] = []
    evaluations = [_score_snapshot("Initial evaluation", evaluation)]
    stopped_reason = "target_score"

    for iteration in range(1, options.max_iterations + 1):
        if evaluation.weighted_score >= options.target_score:
            stopped_reason = "target_score"
            break

        failed = selectWorstCriterion(evaluation)
        logger.info(
            "audit.iteration_start iteration=%d score=%.2f criterion=%s criterion_score=%.2f",
            iteration,
            evaluation.weighted_score,
            failed.criterion_id,
            failed.score,
        )
        await _emit_progress(
            progress,
            "running",
            f"Audit iteration {iteration}: patching {failed.name or failed.criterion_id}.",
            [
                f"Current weighted score: {evaluation.weighted_score:.1f}",
                f"Criterion score: {failed.score:.0f}",
                *(failed.issues[:2] or [failed.smallest_repair]),
            ],
        )
        patched_output = await patchOutput(sourceText, userGoal, output, failed, agent, options)
        await _emit_progress(
            progress,
            "running",
            f"Audit iteration {iteration}: re-evaluating the patch.",
            [f"Patched criterion: {failed.name or failed.criterion_id}"],
        )
        next_evaluation = await evaluateOutput(
            sourceText,
            userGoal,
            patched_output,
            criteria,
            agent,
            options,
        )
        await _emit_output_progress(output_progress, patched_output, next_evaluation)
        evaluations.append(_score_snapshot(f"After iteration {iteration}", next_evaluation))
        improvement = next_evaluation.weighted_score - evaluation.weighted_score
        iterations.append(
            AuditIteration(
                iteration=iteration,
                criterion_id=failed.criterion_id,
                before_score=evaluation.weighted_score,
                after_score=next_evaluation.weighted_score,
                improvement=improvement,
                issues=failed.issues,
                smallest_repair=failed.smallest_repair,
            )
        )

        output = patched_output
        evaluation = next_evaluation
        logger.info(
            "audit.iteration_complete iteration=%d score=%.2f improvement=%.2f",
            iteration,
            evaluation.weighted_score,
            improvement,
        )
        if evaluation.weighted_score >= options.target_score:
            stopped_reason = "target_score"
            break
        if improvement < options.min_improvement:
            stopped_reason = "insufficient_improvement"
            break
    else:
        stopped_reason = "max_iterations"

    await _emit_progress(
        progress,
        "complete",
        f"Audit complete: score {evaluation.weighted_score:.1f}.",
        [
            f"Started at {initial_score:.1f}",
            f"Stopped: {stopped_reason.replace('_', ' ')}",
            f"{len(iterations)} iteration(s)",
        ],
    )
    logger.info(
        "audit.loop_complete initial_score=%.2f final_score=%.2f iterations=%d reason=%s",
        initial_score,
        evaluation.weighted_score,
        len(iterations),
        stopped_reason,
    )
    return AuditLoopResult(
        final_output=output,
        audit_report=AuditReport(
            initial_score=initial_score,
            final_score=evaluation.weighted_score,
            target_score=options.target_score,
            iterations=iterations,
            criteria=criteria,
            evaluations=evaluations,
            final_evaluation=evaluation,
            local_model_usage=_usage_total(agent),
            local_model_usage_by_purpose=_usage_by_purpose(agent),
            stopped_reason=stopped_reason,
        ),
    )


def _dedupe_criteria(criteria: list[AuditCriterion]) -> list[AuditCriterion]:
    deduped: list[AuditCriterion] = []
    seen: set[str] = set()
    for criterion in criteria:
        if criterion.id in seen:
            continue
        seen.add(criterion.id)
        deduped.append(criterion)
    return deduped


def _normalize_evaluation(
    response: _EvaluationResponse,
    criteria: list[AuditCriterion],
) -> AuditEvaluation:
    by_id = {criterion.id: criterion for criterion in criteria}
    found: dict[str, CriterionEvaluation] = {}
    for item in response.criteria:
        criterion = by_id.get(item.criterion_id)
        if criterion is None:
            continue

        found[item.criterion_id] = item.model_copy(
            update={
                "name": criterion.name,
                "description": criterion.description,
                "weight": criterion.weight,
                "issues": _clean_string_list(item.issues),
                "smallest_repair": item.smallest_repair.strip(),
                "weighted_deficit": (100.0 - item.score) * criterion.weight,
            }
        )

    missing = [criterion.id for criterion in criteria if criterion.id not in found]
    if missing:
        raise AnalysisError(f"Audit evaluation omitted criteria: {', '.join(missing)}")

    normalized_score = _weighted_average(list(found.values()))
    return AuditEvaluation(
        criteria=[found[criterion.id] for criterion in criteria],
        weighted_score=normalized_score,
    )


def _weighted_average(criteria: list[CriterionEvaluation]) -> float:
    total_weight = sum(item.weight for item in criteria)
    if total_weight <= 0:
        return 0.0
    return round(sum(item.score * item.weight for item in criteria) / total_weight, 2)


def _score_snapshot(label: str, evaluation: AuditEvaluation) -> AuditScoreSnapshot:
    return AuditScoreSnapshot(
        label=label,
        weighted_score=evaluation.weighted_score,
        criteria=evaluation.criteria,
    )


def _usage_total(agent: BaseLLMAgent) -> LocalModelUsage:
    prompt_tokens = sum(item.prompt_tokens for item in agent.usage)
    completion_tokens = sum(item.completion_tokens for item in agent.usage)
    total_duration_ms = sum(item.total_duration_ms for item in agent.usage)
    return LocalModelUsage(
        calls=len(agent.usage),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        total_duration_ms=round(total_duration_ms, 2),
    )


def _usage_by_purpose(agent: BaseLLMAgent) -> list[LocalModelUsageByPurpose]:
    grouped: dict[str, LocalModelUsageByPurpose] = {}
    for item in agent.usage:
        usage = grouped.setdefault(item.purpose, LocalModelUsageByPurpose(purpose=item.purpose))
        usage.calls += 1
        usage.prompt_tokens += item.prompt_tokens
        usage.completion_tokens += item.completion_tokens
        usage.total_tokens += item.total_tokens
        usage.total_duration_ms = round(usage.total_duration_ms + item.total_duration_ms, 2)
    return list(grouped.values())


async def _chat_validated(
    agent: BaseLLMAgent,
    *,
    model: type[TModel],
    system: str,
    prompt: str,
    purpose: str,
    num_predict: int,
    temperature: float,
) -> TModel:
    raw = ""
    last_error: Exception | None = None
    for attempt in range(2):
        if attempt == 0:
            request_prompt = prompt
        else:
            request_prompt = _json_repair_prompt(model, raw, last_error)

        raw, _ = await agent.chat_json(
            system=system,
            prompt=request_prompt,
            num_predict=num_predict,
            temperature=temperature,
            purpose=purpose,
            think=False,
        )
        try:
            data = _load_ollama_json(raw, purpose=purpose)
            return model.model_validate(data)
        except (AnalysisError, ValidationError) as error:
            last_error = error
            logger.info("%s_json_retry attempt=%d error=%s", purpose, attempt + 1, error)

    raise AnalysisError(f"Ollama returned invalid JSON schema for {purpose}: {last_error}")


def _json_repair_prompt(model: type[BaseModel], raw: str, error: Exception | None) -> str:
    payload = {
        "schema": model.model_json_schema(),
        "invalid_response": raw,
        "error": str(error) if error else "",
    }
    return (
        "Repair the invalid JSON response so it matches the schema exactly. "
        "Keep the intended content. Return strict JSON only.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _clean_string_list(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item.strip()]


async def _emit_progress(
    progress: AuditProgressCallback | None,
    status: str,
    summary: str,
    details: list[str] | None = None,
) -> None:
    if progress is not None:
        await progress(status, summary, details or [])


async def _emit_output_progress(
    output_progress: AuditOutputCallback | None,
    output: str,
    evaluation: AuditEvaluation,
) -> None:
    if output_progress is not None:
        await output_progress(output, evaluation)


# Snake-case aliases for Python callers.
create_fixed_criteria = createFixedCriteria
plan_dynamic_criteria = planDynamicCriteria
evaluate_output = evaluateOutput
select_worst_criterion = selectWorstCriterion
patch_output = patchOutput
run_audit_loop = runAuditLoop
