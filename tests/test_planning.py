from __future__ import annotations

import pytest

from nano_orchestrator.models import ExecutionGraph
from nano_orchestrator.planning import (
    PlanningError,
    plan_request,
)
from nano_orchestrator.validation import (
    ValidationCode,
    validate_execution_graph,
)


class SequenceLLM:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate_execution_graph(self, prompt: str) -> ExecutionGraph:
        self.prompts.append(prompt)

        if not self.responses:
            raise AssertionError("test LLM ran out of responses")

        return ExecutionGraph.model_validate(
            self.responses.pop(0)
        )


def graph(node_id: str = "task") -> dict:
    return {
        "version": 1,
        "nodes": [
            {
                "id": node_id,
                "service": "test",
                "operation": "run",
            }
        ],
    }


def test_valid_graph_never_enters_repair_loop():
    client = SequenceLLM([graph()])

    result = plan_request("run the task", client)

    assert result.graph.nodes[0].id == "task"
    assert result.plan.tasks[0].id == "task"
    assert result.context.attempts == 1
    assert result.context.failures == []
    assert len(client.prompts) == 1
    assert client.prompts[0] == "run the task"

def test_validation_codes_are_explicit():
    assert ValidationCode.UNSUPPORTED_GRAPH_VERSION.value == (
        "UNSUPPORTED_GRAPH_VERSION"
    )
    assert ValidationCode.EMPTY_GRAPH.value == "EMPTY_GRAPH"
    assert ValidationCode.DUPLICATE_NODE_ID.value == (
        "DUPLICATE_NODE_ID"
    )
    assert ValidationCode.EMPTY_NODE_ID.value == "EMPTY_NODE_ID"
    assert ValidationCode.EMPTY_SERVICE.value == "EMPTY_SERVICE"
    assert ValidationCode.EMPTY_OPERATION.value == "EMPTY_OPERATION"
    assert ValidationCode.INVALID_TIMEOUT.value == "INVALID_TIMEOUT"
    assert ValidationCode.INVALID_RETRY_LIMIT.value == (
        "INVALID_RETRY_LIMIT"
    )
    assert ValidationCode.DUPLICATE_DEPENDENCY.value == (
        "DUPLICATE_DEPENDENCY"
    )
    assert ValidationCode.UNKNOWN_DEPENDENCY.value == (
        "UNKNOWN_DEPENDENCY"
    )
    assert ValidationCode.SELF_DEPENDENCY.value == "SELF_DEPENDENCY"
    assert ValidationCode.UNKNOWN_STRUCTURED_REF.value == (
        "UNKNOWN_STRUCTURED_REF"
    )
    assert ValidationCode.SELF_STRUCTURED_REF.value == (
        "SELF_STRUCTURED_REF"
    )
    assert ValidationCode.REF_MISSING_DEPENDENCY.value == (
        "REF_MISSING_DEPENDENCY"
    )
    assert ValidationCode.DEPENDENCY_CYCLE.value == "DEPENDENCY_CYCLE"


def test_deterministic_failure_is_repaired_with_accumulated_history():
    bad = {
        "version": 1,
        "nodes": [
            {
                "id": "consumer",
                "service": "test",
                "operation": "run",
                "arguments": {
                    "input": {
                        "ref": "missing",
                    }
                },
            }
        ],
    }

    fixed = {
        "version": 1,
        "nodes": [
            {
                "id": "producer",
                "service": "test",
                "operation": "run",
            },
            {
                "id": "consumer",
                "service": "test",
                "operation": "run",
                "arguments": {
                    "input": {
                        "ref": "producer",
                    }
                },
                "depends_on": ["producer"],
            },
        ],
    }

    client = SequenceLLM([bad, fixed])

    result = plan_request(
        "produce something and consume it",
        client,
    )

    assert result.context.attempts == 2
    assert len(result.context.failures) == 1
    assert result.context.failures[0].code == ValidationCode.UNKNOWN_STRUCTURED_REF
    assert result.plan.tasks[1].depends_on == ["producer"]

    assert "CURRENT VALIDATION FAILURES" in client.prompts[1]
    assert "UNKNOWN_STRUCTURED_REF" in client.prompts[1]
    assert "node_id: consumer" in client.prompts[1]


def test_multiple_failures_are_all_passed_to_later_repair():
    bad = {
        "version": 1,
        "nodes": [
            {
                "id": "broken",
                "service": "",
                "operation": "",
                "timeout_ms": 0,
                "retry_limit": -1,
                "depends_on": [
                    "missing",
                    "missing",
                ],
            }
        ],
    }

    fixed = graph("fixed")
    client = SequenceLLM([bad, fixed])

    result = plan_request("do the thing", client)

    assert result.context.attempts == 2

    codes = [
        failure.code
        for failure in result.context.failures
    ]

    assert ValidationCode.EMPTY_SERVICE in codes
    assert ValidationCode.EMPTY_OPERATION in codes
    assert ValidationCode.INVALID_TIMEOUT in codes
    assert ValidationCode.INVALID_RETRY_LIMIT in codes
    assert ValidationCode.UNKNOWN_DEPENDENCY in codes
    assert ValidationCode.DUPLICATE_DEPENDENCY in codes

    repair_prompt = client.prompts[1]

    for code in codes:
        assert code.value in repair_prompt


def test_repair_history_is_per_request():
    client = SequenceLLM(
        [
            graph("first"),
            graph("second"),
        ]
    )

    first = plan_request("first request", client)
    second = plan_request("second request", client)

    assert first.context.failures == []
    assert second.context.failures == []
    assert second.context.request == "second request"
    assert len(client.prompts) == 2
    assert "first request" not in client.prompts[1]


def test_exhausting_repairs_raises_with_context():
    bad = {
        "version": 1,
        "nodes": [
            {
                "id": "consumer",
                "service": "test",
                "operation": "run",
                "arguments": {
                    "input": {
                        "ref": "missing",
                    }
                },
            }
        ],
    }

    client = SequenceLLM(
        [
            bad,
            bad,
            bad,
        ]
    )

    with pytest.raises(PlanningError) as exc_info:
        plan_request(
            "do it",
            client,
            max_repairs=2,
        )

    error = exc_info.value

    assert error.context.attempts == 3
    assert len(error.context.failures) == 3

    assert all(
        failure.code == ValidationCode.UNKNOWN_STRUCTURED_REF
        for failure in error.context.failures
    )

def make_valid_graph() -> ExecutionGraph:
    return ExecutionGraph.model_validate(
        {
            "version": 1,
            "nodes": [
                {
                    "id": "source",
                    "service": "search",
                    "operation": "search",
                    "arguments": {},
                    "depends_on": [],
                    "timeout_ms": 30000,
                    "retry_limit": 0,
                },
                {
                    "id": "report",
                    "service": "writer",
                    "operation": "write",
                    "arguments": {
                        "input": {
                            "ref": "source",
                        }
                    },
                    "depends_on": ["source"],
                    "timeout_ms": 30000,
                    "retry_limit": 0,
                },
            ],
        }
    )


def make_missing_dependency_graph() -> ExecutionGraph:
    return ExecutionGraph.model_validate(
        {
            "version": 1,
            "nodes": [
                {
                    "id": "source",
                    "service": "search",
                    "operation": "search",
                    "arguments": {},
                    "depends_on": [],
                    "timeout_ms": 30000,
                    "retry_limit": 0,
                },
                {
                    "id": "report",
                    "service": "writer",
                    "operation": "write",
                    "arguments": {
                        "input": {
                            "ref": "source",
                        }
                    },
                    "depends_on": [],
                    "timeout_ms": 30000,
                    "retry_limit": 0,
                },
            ],
        }
    )


class RepairClient:
    def __init__(
        self,
        initial: ExecutionGraph,
        repaired: ExecutionGraph,
    ) -> None:
        self.initial = initial
        self.repaired = repaired
        self.prompts: list[str] = []

    def generate_execution_graph(
        self,
        prompt: str,
    ) -> ExecutionGraph:
        self.prompts.append(prompt)

        if len(self.prompts) == 1:
            return self.initial

        return self.repaired


def test_ref_missing_dependency_is_reported():
    graph = make_missing_dependency_graph()

    result = validate_execution_graph(graph)

    assert result.status == "fail"

    failures = [
        failure
        for failure in result.failures
        if failure.code == ValidationCode.REF_MISSING_DEPENDENCY
    ]

    assert len(failures) == 1
    assert failures[0].node_id == "report"
    assert "source" in failures[0].message


def test_repair_prompt_contains_structured_failure():
    broken = make_missing_dependency_graph()
    repaired = make_valid_graph()

    client = RepairClient(
        initial=broken,
        repaired=repaired,
    )

    result = plan_request(
        "Find the source and write a report.",
        client,
    )

    assert result.graph == repaired
    assert result.context.attempts == 2
    assert len(client.prompts) == 2

    repair_prompt = client.prompts[1]

    assert "CURRENT VALIDATION FAILURES" in repair_prompt
    assert "REF_MISSING_DEPENDENCY" in repair_prompt
    assert "node_id: report" in repair_prompt
    assert "source" in repair_prompt
    assert "Every structured" in repair_prompt


def test_repair_history_is_preserved():
    broken = make_missing_dependency_graph()
    repaired = make_valid_graph()

    client = RepairClient(
        initial=broken,
        repaired=repaired,
    )

    result = plan_request(
        "Find the source and write a report.",
        client,
    )

    # The real validator contributes the first failure.
    # Verify that the resulting context is cumulative.
    assert result.context.failures
    assert any(
        failure.code == ValidationCode.REF_MISSING_DEPENDENCY
        for failure in result.context.failures
    )


def test_exhausting_repair_budget_raises_planning_error():
    broken = make_missing_dependency_graph()

    class AlwaysBrokenClient:
        def generate_execution_graph(
            self,
            _prompt: str,
        ) -> ExecutionGraph:
            return broken

    with pytest.raises(PlanningError) as exc_info:
        plan_request(
            "Find the source and write a report.",
            AlwaysBrokenClient(),
            max_repairs=2,
        )

    error = exc_info.value

    assert error.context.attempts == 3
    assert error.context.failures

    assert all(
        failure.code == ValidationCode.REF_MISSING_DEPENDENCY
        for failure in error.context.failures
    )


def test_previous_failure_history_is_in_repair_prompt():
    broken = make_missing_dependency_graph()
    repaired = make_valid_graph()

    client = RepairClient(
        initial=broken,
        repaired=repaired,
    )

    plan_request(
        "Find the source and write a report.",
        client,
    )

    repair_prompt = client.prompts[1]

    assert "PREVIOUS REPAIR HISTORY" in repair_prompt
    assert "REF_MISSING_DEPENDENCY" in repair_prompt
    assert "report" in repair_prompt


@pytest.mark.parametrize(
    ("graph_payload", "expected_code"),
    [
        (
            {
                "version": 2,
                "nodes": [
                    {
                        "id": "task",
                        "service": "svc",
                        "operation": "run",
                        "arguments": {},
                        "depends_on": [],
                        "timeout_ms": 30000,
                        "retry_limit": 0,
                    }
                ],
            },
            ValidationCode.UNSUPPORTED_GRAPH_VERSION,
        ),
        (
            {
                "version": 1,
                "nodes": [
                    {
                        "id": "task",
                        "service": "",
                        "operation": "run",
                        "arguments": {},
                        "depends_on": [],
                        "timeout_ms": 30000,
                        "retry_limit": 0,
                    }
                ],
            },
            ValidationCode.EMPTY_SERVICE,
        ),
        (
            {
                "version": 1,
                "nodes": [
                    {
                        "id": "task",
                        "service": "svc",
                        "operation": "run",
                        "arguments": {},
                        "depends_on": ["missing"],
                        "timeout_ms": 30000,
                        "retry_limit": 0,
                    }
                ],
            },
            ValidationCode.UNKNOWN_DEPENDENCY,
        ),
    ],
)

def test_validation_failure_codes(
    graph_payload: dict,
    expected_code: ValidationCode,
):
    graph = ExecutionGraph.model_validate(graph_payload)

    result = validate_execution_graph(graph)

    assert result.status == "fail"
    assert expected_code in {
        failure.code
        for failure in result.failures
    }