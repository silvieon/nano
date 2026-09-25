from __future__ import annotations

from typing import Any

from .models import ExecutionGraph, RuntimePlan, RuntimeTask


class PlanCompileError(ValueError):
    pass


def _collect_task_refs(value: Any, known: set[str]) -> set[str]:
    """Collect canonical semantic task references from arguments.

    Nano has exactly one dependency-bearing argument form:

        {"ref": "task_id"}

    Everything else is ordinary argument data. In particular, bare strings,
    ``source`` fields, nested ``id`` fields, and template/interpolation syntax
    are never interpreted as task references.
    """
    refs: set[str] = set()

    if isinstance(value, dict):
        if "ref" in value:
            ref = value["ref"]

            if not isinstance(ref, str):
                raise PlanCompileError(
                    "task reference field 'ref' must contain a string"
                )

            if ref not in known:
                raise PlanCompileError(
                    f"task reference {ref!r} points to an unknown node"
                )

            refs.add(ref)

        for child in value.values():
            refs.update(_collect_task_refs(child, known))

        return refs

    if isinstance(value, list):
        for child in value:
            refs.update(_collect_task_refs(child, known))

    return refs


def compile_execution_graph(graph: ExecutionGraph) -> RuntimePlan:
    """Lower semantic execution graph into deterministic scheduler IR."""
    ids = [node.id for node in graph.nodes]

    if len(ids) != len(set(ids)):
        raise PlanCompileError(
            "execution graph contains duplicate node IDs"
        )

    known = set(ids)
    dependencies: dict[str, set[str]] = {}

    for node in graph.nodes:
        explicit = set(node.depends_on)

        missing = explicit - known
        if missing:
            raise PlanCompileError(
                f"node {node.id!r} depends on unknown nodes: "
                f"{sorted(missing)}"
            )

        if node.id in explicit:
            raise PlanCompileError(
                f"node {node.id!r} depends on itself"
            )

        referenced = _collect_task_refs(node.arguments, known)
        deps = explicit | referenced

        if node.id in deps:
            raise PlanCompileError(
                f"node {node.id!r} depends on itself"
            )

        dependencies[node.id] = deps

    remaining = {
        node_id: set(deps)
        for node_id, deps in dependencies.items()
    }

    ready = [
        node_id
        for node_id, deps in remaining.items()
        if not deps
    ]

    visited: list[str] = []

    while ready:
        current = ready.pop()
        visited.append(current)

        for node_id, deps in remaining.items():
            if current in deps:
                deps.remove(current)

                if not deps:
                    ready.append(node_id)

    if len(visited) != len(graph.nodes):
        raise PlanCompileError(
            "execution graph contains a dependency cycle"
        )

    return RuntimePlan(
        version=1,
        tasks=[
            RuntimeTask(
                id=node.id,
                service=node.service,
                operation=node.operation,
                arguments=node.arguments,
                depends_on=sorted(dependencies[node.id]),
                timeout_ms=node.timeout_ms,
                retry_limit=node.retry_limit,
            )
            for node in graph.nodes
        ],
    )