import os
import shutil
import subprocess
from pathlib import Path

import pytest

from nano_orchestrator.compiler import compile_execution_graph
from nano_orchestrator.llm import JsonLLMClient


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "scheduling"


SUPPORTED_NOW = {
    "01_basic/sequential_chain",
    "01_basic/wide_parallel",
}


IMPLEMENTED_FAILURE_BEHAVIOR = {
    "04_retries/retry_once",
    "04_retries/retry_exhaustion",
}


FUTURE_BEHAVIOR = {
    "02_dependencies/required_optional",
    "02_dependencies/any_of",
    "03_failures/branch_failure",
    "03_failures/failure_propagation",
    "05_recovery/fallback_after_retry",
    "05_recovery/fallback_failure",
    "06_time/timeout_fallback",
    "06_time/deadline_chain",
    "07_control/cancellation_propagation",
    "07_control/pause_resume",
    "08_resources/concurrency_limit",
    "08_resources/deduplicate_shared_work",
    "09_artifacts/multi_artifact",
    "09_artifacts/artifact_validation",
    "10_agentic/discovered_fact_replan",
    "10_agentic/mid_execution_replan",
}


def all_cases():
    for md in sorted(
        FIXTURES.glob("[0-9][0-9]_*/**/*.md")
    ):
        if md.name == "README.md":
            continue

        relative = md.relative_to(FIXTURES).with_suffix("")
        yield str(relative).replace("\\", "/")


def build_scheduler():
    cargo = shutil.which("cargo")

    if cargo is None:
        pytest.skip(
            "cargo is not installed; Rust scheduler tests skipped"
        )

    manifest = ROOT / "scheduler" / "Cargo.toml"
    binary_name = "nano-scheduler.exe" if os.name == "nt" else "nano-scheduler"

    binary = (
        ROOT
        / "scheduler"
        / "target"
        / "debug"
        / binary_name
    )

    build = subprocess.run(
        [
            cargo,
            "build",
            "--quiet",
            "--manifest-path",
            str(manifest),
        ],
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )

    if build.returncode != 0:
        raise AssertionError(
            "Rust scheduler build failed\n"
            f"stdout:\n{build.stdout}\n"
            f"stderr:\n{build.stderr}"
        )

    assert binary.is_file(), (
        f"scheduler binary was not produced: {binary}"
    )

    return binary


def run_scheduler(plan_json: str):
    binary = build_scheduler()

    return subprocess.run(
        [str(binary)],
        input=plan_json + "\n",
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
        timeout=15,
    )


@pytest.mark.parametrize("case", list(all_cases()))
def test_horizon_fixture_is_valid_execution_graph(case):
    fixture = FIXTURES / f"{case}.json"

    assert fixture.is_file(), (
        f"missing JSON sidecar for {case}"
    )

    response = fixture.read_text()

    graph = JsonLLMClient().generate_execution_graph(
        response
    )

    plan = compile_execution_graph(graph)

    assert plan.version == 1
    assert plan.tasks


@pytest.mark.parametrize(
    "case",
    sorted(SUPPORTED_NOW),
)
def test_currently_supported_scenarios_are_classified_as_supported(
    case,
):
    assert case not in FUTURE_BEHAVIOR


@pytest.mark.parametrize(
    "case",
    sorted(IMPLEMENTED_FAILURE_BEHAVIOR),
)
def test_retry_scenarios_are_no_longer_future_behavior(case):
    assert case not in FUTURE_BEHAVIOR


def load_plan(case: str):
    response = (
        FIXTURES / f"{case}.json"
    ).read_text()

    graph = JsonLLMClient().generate_execution_graph(
        response
    )

    return compile_execution_graph(graph)


def test_retry_once_transitions_ready_running_retry_and_success():
    plan = load_plan("04_retries/retry_once")

    result = run_scheduler(
        plan.model_dump_json()
    )

    assert result.returncode == 0, result.stderr

    trace = result.stdout

    assert "READY    status" in trace
    assert "START    status" in trace
    assert "ATTEMPT  status  #1" in trace
    assert (
        "FAIL     status  attempt=1 class=transient"
        in trace
    )
    assert (
        "RETRY    status  next_attempt=2"
        in trace
    )
    assert "ATTEMPT  status  #2" in trace
    assert "DONE     status" in trace
    assert "READY    save" in trace
    assert "DONE     save" in trace
    assert "scheduler: plan complete" in trace


def test_retry_exhaustion_fails_plan_after_retry_budget():
    plan = load_plan(
        "04_retries/retry_exhaustion"
    )

    result = run_scheduler(
        plan.model_dump_json()
    )

    assert result.returncode != 0

    trace = result.stdout

    assert "ATTEMPT  status  #1" in trace
    assert "ATTEMPT  status  #2" in trace
    assert "ATTEMPT  status  #3" in trace
    assert trace.count("RETRY    status") == 2
    assert "FAILED   status" in trace
    assert (
        "scheduler: stopping because a task failed"
        in trace
    )
    assert "READY    save" not in trace


@pytest.mark.parametrize(
    "case",
    sorted(FUTURE_BEHAVIOR),
)
def test_future_scheduler_behavior_is_explicitly_tracked(case):
    """These are valid plan fixtures, but their advanced semantics need
    scheduler support before they become end-to-end execution assertions.
    """
    pytest.xfail(
        f"future scheduler semantics: {case}"
    )