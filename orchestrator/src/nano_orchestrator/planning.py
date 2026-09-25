from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from .compiler import PlanCompileError, compile_execution_graph
from .llm import LLMClient
from .models import ExecutionGraph, RuntimePlan
from .validation import (
    ValidationFailure,
    validate_execution_graph,
)


class PlanningError(RuntimeError):
    def __init__(
        self,
        message: str,
        context: "RepairContext",
    ) -> None:
        super().__init__(message)
        self.context = context


@dataclass
class RepairContext:
    request: str
    failures: list[ValidationFailure] = field(
        default_factory=list
    )
    attempts: int = 0


@dataclass(frozen=True)
class PlanningResult:
    graph: ExecutionGraph
    plan: RuntimePlan
    context: RepairContext


def _format_repair_failures(
    failures: list[ValidationFailure] | tuple[ValidationFailure, ...],
) -> str:
    if not failures:
        return "None"

    sections: list[str] = []

    for index, failure in enumerate(failures, start=1):
        sections.append(
            "\n".join(
                [
                    f"FAILURE {index}",
                    f"source: {failure.source}",
                    f"code: {failure.code}",
                    f"node_id: {failure.node_id or 'none'}",
                    f"message: {failure.message}",
                ]
            )
        )

    return "\n\n".join(sections)


def _format_repair_history(
    failures: list[ValidationFailure],
) -> str:
    if not failures:
        return "None"

    return "\n".join(
        [
            (
                f"- [{failure.code}] "
                f"{failure.node_id or 'graph'}: "
                f"{failure.message}"
            )
            for failure in failures
        ]
    )


def _build_repair_prompt(
    context: RepairContext,
    graph: ExecutionGraph,
    current_failures: tuple[ValidationFailure, ...],
) -> str:
    current_graph = graph.model_dump_json(indent=2)

    return f"""
You are repairing an ExecutionGraph generated for Nano.

ORIGINAL USER REQUEST

{context.request}

CURRENT EXECUTION GRAPH

{current_graph}

CURRENT VALIDATION FAILURES

{_format_repair_failures(current_failures)}

PREVIOUS REPAIR HISTORY

{_format_repair_history(context.failures)}

REPAIR REQUIREMENTS

- Fix every current validation failure.
- Preserve valid portions of the current graph.
- Make the smallest necessary changes.
- Do not introduce unrelated changes.
- Do not invent resources, services, or operations.
- Do not add dependencies merely because nodes are related.
- Every dependency in depends_on must name an existing node.
- Every structured {{"ref": "<node_id>"}} must reference an existing node.
- Every structured ref must also list that node in depends_on.
- Ordinary strings are data, not task references.
- Do not use ref_id or source to represent task dependencies.
- Do not use templates or interpolation to represent task dependencies.
- The graph version must remain 1.
- Every node must have a nonempty service and operation.
- Return only valid ExecutionGraph JSON.
""".strip()


def _schema_failure(exc: ValidationError) -> ValidationFailure:
    return ValidationFailure(
        source="deterministic",
        code="SCHEMA_VALIDATION_ERROR",
        message=str(exc),
    )


def _llm_output_failure(exc: Exception) -> ValidationFailure:
    return ValidationFailure(
        source="deterministic",
        code="LLM_OUTPUT_ERROR",
        message=str(exc),
    )


def _compiler_failure(exc: PlanCompileError) -> ValidationFailure:
    return ValidationFailure(
        source="deterministic",
        code="COMPILER_ERROR",
        message=str(exc),
    )


def plan_request(
    request: str,
    llm_client: LLMClient,
    max_repairs: int = 2,
) -> PlanningResult:
    """Generate, validate, compile, and repair an execution graph."""

    context = RepairContext(request=request)

    graph: ExecutionGraph | None = None

    for attempt in range(max_repairs + 1):
        context.attempts = attempt + 1

        if attempt == 0:
            prompt = request
        else:
            assert graph is not None

            current_validation = validate_execution_graph(graph)

            prompt = _build_repair_prompt(
                context,
                graph,
                current_validation.failures,
            )

        try:
            graph = llm_client.generate_execution_graph(prompt)

        except ValidationError as exc:
            failure = _schema_failure(exc)
            context.failures.append(failure)

            if attempt >= max_repairs:
                raise PlanningError(
                    "LLM failed ExecutionGraph schema validation "
                    "after repair budget was exhausted",
                    context,
                ) from exc

            graph = None
            continue

        except (ValueError, TypeError) as exc:
            failure = _llm_output_failure(exc)
            context.failures.append(failure)

            if attempt >= max_repairs:
                raise PlanningError(
                    "LLM returned invalid ExecutionGraph output "
                    "after repair budget was exhausted",
                    context,
                ) from exc

            graph = None
            continue

        validation = validate_execution_graph(graph)

        if validation.status == "fail":
            context.failures.extend(validation.failures)

            if attempt >= max_repairs:
                raise PlanningError(
                    "ExecutionGraph failed deterministic validation "
                    "after repair budget was exhausted",
                    context,
                )

            continue

        try:
            plan = compile_execution_graph(graph)

        except PlanCompileError as exc:
            failure = _compiler_failure(exc)
            context.failures.append(failure)

            if attempt >= max_repairs:
                raise PlanningError(
                    "ExecutionGraph compilation failed "
                    "after repair budget was exhausted",
                    context,
                ) from exc

            continue

        return PlanningResult(
            graph=graph,
            plan=plan,
            context=context,
        )

    raise AssertionError("planning loop exited unexpectedly")