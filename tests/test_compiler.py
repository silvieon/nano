import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nano_orchestrator.compiler import PlanCompileError, compile_execution_graph
from nano_orchestrator.models import ExecutionGraph

FIXTURES = Path(__file__).parent / "fixtures" / "scheduling"


def load_graph(name: str) -> ExecutionGraph:
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    return ExecutionGraph.model_validate(data)


def test_parallel_research_compiles_to_five_tasks():
    plan = compile_execution_graph(load_graph("01_parallel_research"))
    assert len(plan.tasks) == 5
    assert plan.tasks[0].id == "filesystem-search"
    reconcile = next(t for t in plan.tasks if t.id == "reconcile")
    assert set(reconcile.depends_on) == {"filesystem-search", "web-search", "service-search"}


def test_fanout_fanin_dependencies_survive_compilation():
    plan = compile_execution_graph(load_graph("03_fanout_fanin"))
    inventory = next(t for t in plan.tasks if t.id == "inventory")
    usage = next(t for t in plan.tasks if t.id == "disk-usage")
    thumbnails = next(t for t in plan.tasks if t.id == "contact-sheet")
    combine = next(t for t in plan.tasks if t.id == "combine-report")

    assert inventory.depends_on == ["discover-backup"]
    assert usage.depends_on == ["discover-backup"]
    assert thumbnails.depends_on == ["discover-backup"]
    assert set(combine.depends_on) == {"inventory", "disk-usage", "contact-sheet"}


def test_unknown_dependency_is_rejected():
    graph = ExecutionGraph.model_validate({
        "version": 1,
        "nodes": [{
            "id": "a",
            "service": "test",
            "operation": "run",
            "depends_on": ["missing"],
        }],
    })
    with pytest.raises(PlanCompileError, match="unknown nodes"):
        compile_execution_graph(graph)


def test_dependency_cycle_is_rejected():
    graph = ExecutionGraph.model_validate({
        "version": 1,
        "nodes": [
            {"id": "a", "service": "test", "operation": "run", "depends_on": ["b"]},
            {"id": "b", "service": "test", "operation": "run", "depends_on": ["a"]},
        ],
    })
    with pytest.raises(PlanCompileError, match="dependency cycle"):
        compile_execution_graph(graph)


def test_llm_graph_schema_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ExecutionGraph.model_validate({
            "version": 1,
            "nodes": [{
                "id": "a",
                "service": "test",
                "operation": "run",
                "depends_on": [],
                "invented_scheduler_magic": True,
            }],
        })
