from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from nano_orchestrator.llm import JsonLLMClient
from nano_orchestrator.planning import plan_request

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_ROOT = ROOT / "orchestrator"
FIXTURES = ROOT / "tests" / "fixtures" / "scheduling"

CASES = [
    "01_parallel_research",
    "02_print_pipeline",
    "03_fanout_fanin",
]


def run_scheduler(plan_json: str) -> str:
    """Build the scheduler, then execute the binary directly.

    Keeping Cargo out of the actual scheduler subprocess makes stdin/stdout
    behavior deterministic and avoids testing Cargo's process wrapper.
    """
    cargo = shutil.which("cargo")

    if cargo is None:
        pytest.skip(
            "cargo is not installed; Python graph/compiler tests still run"
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

    if not binary.is_file():
        raise AssertionError(
            f"Rust scheduler binary was not produced: {binary}"
        )

    result = subprocess.run(
        [str(binary)],
        input=plan_json + "\n",
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
        timeout=15,
    )

    if result.returncode != 0:
        raise AssertionError(
            "Rust scheduler failed\n"
            f"exit code: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return result.stdout


@pytest.mark.parametrize("case", CASES)
def test_human_request_compiles_and_produces_scheduler_trace(
    case,
    capsys,
):
    """Exercise the intended vertical slice using a deterministic LLM fixture.

    The .md file is the human-readable request. Its .json sidecar stands in for
    the schema-constrained LLM response until a real model adapter is connected.
    """
    prompt = (
        FIXTURES / f"{case}.md"
    ).read_text().strip()

    expected_llm_response = (
        FIXTURES / f"{case}.json"
    ).read_text()

    class FixtureLLM:
        def generate_execution_graph(self, _prompt):
            return JsonLLMClient().generate_execution_graph(
                expected_llm_response
            )

    result = plan_request(prompt, FixtureLLM())

    graph = result.graph
    plan = result.plan

    trace = run_scheduler(
        plan.model_dump_json()
    )

    print(f"\n=== HUMAN REQUEST: {case} ===")
    print(prompt)

    print("\n=== RUST SCHEDULER TRACE ===")
    print(trace, end="")

    assert "=== nano scheduler ===" in trace
    assert "scheduler: plan complete" in trace
    assert "START" in trace
    assert "DONE" in trace

    captured = capsys.readouterr().out

    assert prompt in captured
    assert "RUST SCHEDULER TRACE" in captured