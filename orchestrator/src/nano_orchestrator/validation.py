from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from .models import ExecutionGraph


ValidationSource = Literal["deterministic", "probabilistic"]
ValidationStatus = Literal["pass", "fail", "unknown"]


class ValidationCode(StrEnum):
    UNSUPPORTED_GRAPH_VERSION = "UNSUPPORTED_GRAPH_VERSION"
    EMPTY_GRAPH = "EMPTY_GRAPH"
    DUPLICATE_NODE_ID = "DUPLICATE_NODE_ID"
    EMPTY_NODE_ID = "EMPTY_NODE_ID"
    EMPTY_SERVICE = "EMPTY_SERVICE"
    EMPTY_OPERATION = "EMPTY_OPERATION"
    INVALID_TIMEOUT = "INVALID_TIMEOUT"
    INVALID_RETRY_LIMIT = "INVALID_RETRY_LIMIT"
    DUPLICATE_DEPENDENCY = "DUPLICATE_DEPENDENCY"
    UNKNOWN_DEPENDENCY = "UNKNOWN_DEPENDENCY"
    SELF_DEPENDENCY = "SELF_DEPENDENCY"
    UNKNOWN_STRUCTURED_REF = "UNKNOWN_STRUCTURED_REF"
    SELF_STRUCTURED_REF = "SELF_STRUCTURED_REF"
    REF_MISSING_DEPENDENCY = "REF_MISSING_DEPENDENCY"
    DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"


@dataclass(frozen=True)
class ValidationFailure:
    source: ValidationSource
    code: ValidationCode
    message: str
    node_id: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    checked: tuple[str, ...] = ()
    failures: tuple[ValidationFailure, ...] = ()


def _collect_task_refs(
    value: object,
    known: set[str],
) -> list[tuple[str, str]]:
    """Collect canonical structured task references.

    Only this form represents a task dependency:

        {"ref": "<task_id>"}

    Returns (ref, error) pairs for malformed references.
    """
    refs: list[tuple[str, str]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            if key == "ref":
                if not isinstance(child, str):
                    refs.append(
                        (
                            "",
                            "structured task reference field 'ref' "
                            "must contain a string",
                        )
                    )
                elif child not in known:
                    refs.append(
                        (
                            child,
                            f"structured task reference points to "
                            f"unknown node {child!r}",
                        )
                    )
                else:
                    refs.append((child, ""))

            refs.extend(_collect_task_refs(child, known))

    elif isinstance(value, list):
        for child in value:
            refs.extend(_collect_task_refs(child, known))

    return refs


def validate_execution_graph(
    graph: ExecutionGraph,
) -> ValidationResult:
    """Prove deterministic structural properties of an ExecutionGraph."""

    failures: list[ValidationFailure] = []
    checked: list[str] = []

    # Graph version.
    checked.append("supported_graph_version")

    if graph.version != 1:
        failures.append(
            ValidationFailure(
                source="deterministic",
                code=ValidationCode.UNSUPPORTED_GRAPH_VERSION,
                message=(
                    "execution graph version must be 1, "
                    f"got {graph.version!r}"
                ),
            )
        )

    # Non-empty graph.
    checked.append("nonempty_graph")

    if not graph.nodes:
        failures.append(
            ValidationFailure(
                source="deterministic",
                code=ValidationCode.EMPTY_GRAPH,
                message="execution graph must contain at least one node",
            )
        )

        return ValidationResult(
            status="fail",
            checked=tuple(checked),
            failures=tuple(failures),
        )

    # Unique node IDs.
    checked.append("unique_node_ids")

    ids = [node.id for node in graph.nodes]
    known = set(ids)

    seen: set[str] = set()

    for node_id in ids:
        if node_id in seen:
            failures.append(
                ValidationFailure(
                    source="deterministic",
                    code=ValidationCode.DUPLICATE_NODE_ID,
                    message=(
                        f"node ID {node_id!r} appears more than once"
                    ),
                    node_id=node_id,
                )
            )

        seen.add(node_id)

    # Node-level structural properties.
    checked.extend(
        [
            "nonempty_node_ids",
            "nonempty_services",
            "nonempty_operations",
            "valid_timeouts",
            "valid_retry_limits",
        ]
    )

    for node in graph.nodes:
        if not node.id.strip():
            failures.append(
                ValidationFailure(
                    source="deterministic",
                    code=ValidationCode.EMPTY_NODE_ID,
                    message="node ID must not be empty",
                    node_id=node.id,
                )
            )

        if not node.service.strip():
            failures.append(
                ValidationFailure(
                    source="deterministic",
                    code=ValidationCode.EMPTY_SERVICE,
                    message=(
                        f"node {node.id!r} must have a nonempty service"
                    ),
                    node_id=node.id,
                )
            )

        if not node.operation.strip():
            failures.append(
                ValidationFailure(
                    source="deterministic",
                    code=ValidationCode.EMPTY_OPERATION,
                    message=(
                        f"node {node.id!r} must have a nonempty operation"
                    ),
                    node_id=node.id,
                )
            )

        if node.timeout_ms <= 0:
            failures.append(
                ValidationFailure(
                    source="deterministic",
                    code=ValidationCode.INVALID_TIMEOUT,
                    message=(
                        f"node {node.id!r} timeout_ms must be greater "
                        f"than zero, got {node.timeout_ms}"
                    ),
                    node_id=node.id,
                )
            )

        if node.retry_limit < 0:
            failures.append(
                ValidationFailure(
                    source="deterministic",
                    code=ValidationCode.INVALID_RETRY_LIMIT,
                    message=(
                        f"node {node.id!r} retry_limit must be "
                        f"nonnegative, got {node.retry_limit}"
                    ),
                    node_id=node.id,
                )
            )

    # Dependencies.
    checked.extend(
        [
            "dependency_uniqueness",
            "known_dependencies",
            "no_self_dependencies",
        ]
    )

    dependencies: dict[str, set[str]] = {}

    for node in graph.nodes:
        dependency_set: set[str] = set()

        for dependency in node.depends_on:
            if dependency in dependency_set:
                failures.append(
                    ValidationFailure(
                        source="deterministic",
                        code=ValidationCode.DUPLICATE_DEPENDENCY,
                        message=(
                            f"node {node.id!r} lists dependency "
                            f"{dependency!r} more than once"
                        ),
                        node_id=node.id,
                    )
                )

            dependency_set.add(dependency)

            if dependency not in known:
                failures.append(
                    ValidationFailure(
                        source="deterministic",
                        code=ValidationCode.UNKNOWN_DEPENDENCY,
                        message=(
                            f"node {node.id!r} depends on unknown "
                            f"node {dependency!r}"
                        ),
                        node_id=node.id,
                    )
                )

            if dependency == node.id:
                failures.append(
                    ValidationFailure(
                        source="deterministic",
                        code=ValidationCode.SELF_DEPENDENCY,
                        message=(
                            f"node {node.id!r} depends on itself"
                        ),
                        node_id=node.id,
                    )
                )

        dependencies[node.id] = dependency_set

    # Structured refs.
    checked.extend(
        [
            "structured_refs_exist",
            "structured_refs_not_self",
            "structured_refs_have_dependencies",
        ]
    )

    for node in graph.nodes:
        refs = _collect_task_refs(node.arguments, known)

        for ref, error in refs:
            if error:
                if ref:
                    failures.append(
                        ValidationFailure(
                            source="deterministic",
                            code=ValidationCode.UNKNOWN_STRUCTURED_REF,
                            message=error,
                            node_id=node.id,
                        )
                    )
                else:
                    failures.append(
                        ValidationFailure(
                            source="deterministic",
                            code=ValidationCode.UNKNOWN_STRUCTURED_REF,
                            message=error,
                            node_id=node.id,
                        )
                    )

                continue

            if ref == node.id:
                failures.append(
                    ValidationFailure(
                        source="deterministic",
                        code=ValidationCode.SELF_STRUCTURED_REF,
                        message=(
                            f"node {node.id!r} contains a structured "
                            f"reference to itself"
                        ),
                        node_id=node.id,
                    )
                )
                continue

            if ref not in dependencies[node.id]:
                failures.append(
                    ValidationFailure(
                        source="deterministic",
                        code=ValidationCode.REF_MISSING_DEPENDENCY,
                        message=(
                            f"node {node.id!r} references task {ref!r} "
                            f'using {{"ref": "{ref}"}} but does not '
                            f"list {ref!r} in depends_on"
                        ),
                        node_id=node.id,
                    )
                )

    # Dependency acyclicity.
    checked.append("dependency_acyclicity")

    remaining = {
        node_id: set(deps)
        for node_id, deps in dependencies.items()
    }

    ready = [
        node_id
        for node_id, deps in remaining.items()
        if not deps
    ]

    visited: set[str] = set()

    while ready:
        current = ready.pop()

        if current in visited:
            continue

        visited.add(current)

        for node_id, deps in remaining.items():
            if current in deps:
                deps.remove(current)

                if not deps:
                    ready.append(node_id)

    if len(visited) != len(graph.nodes):
        failures.append(
            ValidationFailure(
                source="deterministic",
                code=ValidationCode.DEPENDENCY_CYCLE,
                message="execution graph contains a dependency cycle",
            )
        )

    return ValidationResult(
        status="fail" if failures else "pass",
        checked=tuple(checked),
        failures=tuple(failures),
    )