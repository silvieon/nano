from __future__ import annotations

import re
from typing import Any

from .models import ExecutionGraph, RuntimePlan, RuntimeTask


class PlanCompileError(ValueError):
    pass


_TEMPLATE_REF = re.compile(
    r"^\{(?P<id>[^{}]+?)(?:\.[^{}]+)?\}$"
)


def _collect_task_refs(value: Any, known: set[str]) -> set[str]:
    """Collect explicit and unambiguous task references from semantic arguments.

    Supported reference forms:
      {"ref": "task"}
      {"ref_id": "task"}
      {"source": "task"}
      "task"                  when it exactly matches a known node ID
      "{task}"                template form
      "{node_4}"              legacy numeric-node template form

    Arbitrary strings are not treated as dependencies unless they resolve to
    a known task ID.
    """
    refs: set[str] = set()

    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"ref", "ref_id", "source"}:
                if not isinstance(child, str):
                    raise PlanCompileError(
                        f"task reference field {key!r} must contain a string"
                    )

                ref = child.split(".", 1)[0]

                if ref not in known and ref.startswith("node_"):
                    candidate = ref.removeprefix("node_")
                    if candidate in known:
                        ref = candidate

                if ref not in known:
                    raise PlanCompileError(
                        f"task reference {child!r} in field {key!r} "
                        "points to an unknown node"
                    )

                refs.add(ref)

            refs.update(_collect_task_refs(child, known))

        return refs

    if isinstance(value, list):
        for child in value:
            refs.update(_collect_task_refs(child, known))

        return refs

    if isinstance(value, str):
        if value in known:
            refs.add(value)
            return refs

        match = _TEMPLATE_REF.fullmatch(value)
        if match:
            ref = match.group("id")

            if ref.startswith("output_of_"):
                ref = ref.removeprefix("output_of_")

            elif ref.startswith("output_from_"):
                ref = ref.removeprefix("output_from_")

            elif "." in ref:
                ref = ref.split(".", 1)[0]

            if ref not in known and ref.startswith("node_"):
                candidate = ref.removeprefix("node_")
                if candidate in known:
                    ref = candidate

            if ref not in known:
                raise PlanCompileError(
                    f"task reference {match.group('id')!r} in template "
                    "points to an unknown node"
                )

            refs.add(ref)

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

    # Kahn's algorithm catches dependency cycles before the plan reaches Rust.
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