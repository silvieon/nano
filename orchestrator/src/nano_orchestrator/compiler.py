from __future__ import annotations

from .models import ExecutionGraph, RuntimePlan, RuntimeTask


class PlanCompileError(ValueError):
    pass


def compile_execution_graph(graph: ExecutionGraph) -> RuntimePlan:
    """Lower semantic execution graph into deterministic scheduler IR."""
    ids = [node.id for node in graph.nodes]
    if len(ids) != len(set(ids)):
        raise PlanCompileError("execution graph contains duplicate node IDs")

    known = set(ids)
    for node in graph.nodes:
        missing = set(node.depends_on) - known
        if missing:
            raise PlanCompileError(
                f"node {node.id!r} depends on unknown nodes: {sorted(missing)}"
            )
        if node.id in node.depends_on:
            raise PlanCompileError(f"node {node.id!r} depends on itself")

    # Kahn's algorithm catches dependency cycles before the plan reaches Rust.
    remaining = {node.id: set(node.depends_on) for node in graph.nodes}
    ready = [node_id for node_id, deps in remaining.items() if not deps]
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
        raise PlanCompileError("execution graph contains a dependency cycle")

    return RuntimePlan(
        version=1,
        tasks=[
            RuntimeTask(
                id=node.id,
                service=node.service,
                operation=node.operation,
                arguments=node.arguments,
                depends_on=node.depends_on,
                timeout_ms=node.timeout_ms,
                retry_limit=node.retry_limit,
            )
            for node in graph.nodes
        ],
    )