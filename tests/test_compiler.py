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

def test_ref_id_arguments_become_runtime_dependencies():
    graph = ExecutionGraph.model_validate({
        "version": 1,
        "nodes": [
            {
                "id": "search",
                "service": "web",
                "operation": "search",
            },
            {
                "id": "summary",
                "service": "nlp",
                "operation": "summarize",
                "arguments": {
                    "text": {
                        "ref_id": "search",
                    }
                },
            },
        ],
    })

    plan = compile_execution_graph(graph)

    assert next(
        t for t in plan.tasks if t.id == "summary"
    ).depends_on == ["search"]


def test_nested_source_references_become_fanin_dependencies():
    graph = ExecutionGraph.model_validate({
        "version": 1,
        "nodes": [
            {
                "id": "python",
                "service": "web",
                "operation": "search",
            },
            {
                "id": "rust",
                "service": "web",
                "operation": "search",
            },
            {
                "id": "synthesize",
                "service": "nlp",
                "operation": "summarize",
                "arguments": {
                    "texts": [
                        {
                            "id": "python_results",
                            "source": "python",
                        },
                        {
                            "id": "rust_results",
                            "source": "rust",
                        },
                    ]
                },
            },
        ],
    })

    plan = compile_execution_graph(graph)

    assert next(
        t for t in plan.tasks if t.id == "synthesize"
    ).depends_on == ["python", "rust"]


def test_bare_task_ids_and_templates_become_dependencies():
    graph = ExecutionGraph.model_validate({
        "version": 1,
        "nodes": [
            {
                "id": "read_a",
                "service": "file",
                "operation": "read",
            },
            {
                "id": "read_b",
                "service": "file",
                "operation": "read",
            },
            {
                "id": "compare",
                "service": "compare",
                "operation": "run",
                "arguments": {
                    "data1": "read_a",
                    "data2": "read_b",
                },
            },
            {
                "id": "report",
                "service": "report",
                "operation": "run",
                "arguments": {
                    "content": "{compare}",
                },
            },
        ],
    })

    plan = compile_execution_graph(graph)

    assert next(
        t for t in plan.tasks if t.id == "compare"
    ).depends_on == ["read_a", "read_b"]

    assert next(
        t for t in plan.tasks if t.id == "report"
    ).depends_on == ["compare"]


def test_arbitrary_strings_are_not_dependencies():
    graph = ExecutionGraph.model_validate({
        "version": 1,
        "nodes": [
            {
                "id": "search",
                "service": "web",
                "operation": "search",
            },
            {
                "id": "report",
                "service": "report",
                "operation": "write",
                "arguments": {
                    "question": "search the internet",
                },
            },
        ],
    })

    plan = compile_execution_graph(graph)

    assert next(
        t for t in plan.tasks if t.id == "report"
    ).depends_on == []