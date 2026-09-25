#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from nano_orchestrator.compiler import compile_execution_graph
from nano_orchestrator.llm import JsonLLMClient, load_llm_client


ROOT = Path(__file__).resolve().parents[1]
SCHEDULING_FIXTURES = ROOT / "tests" / "fixtures" / "scheduling"
EXECUTIONGRAPH_FIXTURES = ROOT / "tests" / "fixtures" / "executiongraph"
EXECUTIONGRAPH_RESULTS = ROOT / "tests" / "results" / "executiongraph"


def discover_scheduling_cases() -> list[str]:
    cases = []

    for json_file in sorted(SCHEDULING_FIXTURES.rglob("*.json")):
        md_file = json_file.with_suffix(".md")

        if md_file.is_file():
            cases.append(
                str(json_file.relative_to(SCHEDULING_FIXTURES).with_suffix(""))
            )

    return cases


def discover_executiongraph_cases() -> list[str]:
    return sorted(
        str(path.relative_to(EXECUTIONGRAPH_FIXTURES).with_suffix(""))
        for path in EXECUTIONGRAPH_FIXTURES.rglob("*.md")
        if path.name != "README.md"
    )


def run_scheduler(plan_json: str) -> tuple[int, str, str]:
    cargo = shutil.which("cargo")

    if cargo is None:
        raise RuntimeError("cargo is not installed or not on PATH")

    manifest = ROOT / "scheduler" / "Cargo.toml"
    binary_name = "nano-scheduler.exe" if os.name == "nt" else "nano-scheduler"
    binary = ROOT / "scheduler" / "target" / "debug" / binary_name

    print("Building Rust scheduler...", flush=True)

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
        print(build.stdout, end="")
        print(build.stderr, end="", file=sys.stderr)
        raise RuntimeError("Rust scheduler build failed")

    if not binary.is_file():
        raise RuntimeError(
            f"Rust scheduler binary was not produced: {binary}"
        )

    result = subprocess.run(
        [str(binary)],
        input=plan_json + "\n",
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
        timeout=30,
    )

    return result.returncode, result.stdout, result.stderr


def run_plan(prompt: str, llm_client) -> int:
    print()
    print("=" * 72)
    print("HUMAN INPUT")
    print("=" * 72)
    print(prompt)

    graph = llm_client.generate_execution_graph(prompt)

    print()
    print("=" * 72)
    print("EXECUTION GRAPH")
    print("=" * 72)
    print(json.dumps(graph.model_dump(), indent=2))

    plan = compile_execution_graph(graph)

    print()
    print("=" * 72)
    print("COMPILED RUNTIME PLAN")
    print("=" * 72)
    print(json.dumps(plan.model_dump(), indent=2))

    print()
    print("=" * 72)
    print("RUST SCHEDULER TRACE")
    print("=" * 72)

    try:
        exit_code, stdout, stderr = run_scheduler(
            plan.model_dump_json()
        )
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(stdout, end="")

    if stderr:
        print()
        print("=" * 72)
        print("RUST SCHEDULER STDERR")
        print("=" * 72)
        print(stderr, end="", file=sys.stderr)

    print()
    print("=" * 72)
    print(f"EXIT CODE: {exit_code}")
    print("=" * 72)
    print()

    return exit_code


def run_fixture(case: str) -> int:
    md_path = SCHEDULING_FIXTURES / f"{case}.md"
    json_path = SCHEDULING_FIXTURES / f"{case}.json"

    if not md_path.is_file():
        print(f"ERROR: case not found: {case}", file=sys.stderr)
        return 1

    if not json_path.is_file():
        print(
            f"ERROR: missing JSON fixture: {json_path}",
            file=sys.stderr,
        )
        return 1

    prompt = md_path.read_text().strip()
    llm_response = json_path.read_text()

    print()
    print("=" * 72)
    print(f"FIXTURE: {case}")
    print("=" * 72)

    graph = JsonLLMClient().generate_execution_graph(
        llm_response
    )

    plan = compile_execution_graph(graph)

    print()
    print("=== HUMAN REQUEST ===")
    print(prompt)

    print()
    print("=== EXECUTION GRAPH ===")
    print(json.dumps(graph.model_dump(), indent=2))

    print()
    print("=== COMPILED RUNTIME PLAN ===")
    print(json.dumps(plan.model_dump(), indent=2))

    print()
    print("=== RUST SCHEDULER TRACE ===")

    try:
        exit_code, stdout, stderr = run_scheduler(
            plan.model_dump_json()
        )
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(stdout, end="")

    if stderr:
        print()
        print("=== RUST SCHEDULER STDERR ===")
        print(stderr, end="", file=sys.stderr)

    print()
    print(f"=== EXIT CODE: {exit_code} ===")
    print()

    return exit_code


def run_executiongraph_case(case: str, client, binary: Path) -> dict:
    md_path = EXECUTIONGRAPH_FIXTURES / f"{case}.md"

    if not md_path.is_file():
        raise ValueError(f"case not found: {case}")

    prompt = md_path.read_text(encoding="utf-8").strip()
    output_dir = EXECUTIONGRAPH_RESULTS / Path(case)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "input.md").write_text(
        prompt + "\n",
        encoding="utf-8",
    )

    result = {
        "case": case,
        "status": "error",
        "input": prompt,
    }

    try:
        graph = client.generate_execution_graph(prompt)
        graph_data = graph.model_dump(mode="json")
        (output_dir / "execution_graph.json").write_text(
            json.dumps(graph_data, indent=2) + "\n",
            encoding="utf-8",
        )
        result["execution_graph"] = graph_data

        plan = compile_execution_graph(graph)
        plan_data = plan.model_dump(mode="json")
        (output_dir / "runtime_plan.json").write_text(
            json.dumps(plan_data, indent=2) + "\n",
            encoding="utf-8",
        )
        result["runtime_plan"] = plan_data

        exit_code, stdout, stderr = run_scheduler(
            plan.model_dump_json()
        )

        (output_dir / "scheduler_trace.txt").write_text(
            stdout,
            encoding="utf-8",
        )

        if stderr:
            (output_dir / "scheduler_stderr.txt").write_text(
                stderr,
                encoding="utf-8",
            )

        result["scheduler_exit_code"] = exit_code
        result["status"] = "passed" if exit_code == 0 else "scheduler_failed"

    except subprocess.TimeoutExpired as exc:
        result["error_type"] = "TimeoutExpired"
        result["error"] = str(exc)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)

    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return result


def run_executiongraph(case: str | None, run_all: bool, limit: int | None) -> int:
    available = discover_executiongraph_cases()

    if case:
        case = case.removesuffix(".md")
        if case not in available:
            print(f"ERROR: unknown ExecutionGraph case: {case}", file=sys.stderr)
            return 1
        cases = [case]
    elif run_all:
        cases = available
    else:
        raise ValueError("provide --case, --all-executiongraph, or --list-executiongraph")

    if limit is not None:
        cases = cases[:limit]

    try:
        client = load_llm_client()
        binary = build_scheduler_for_observation()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print()
    print(f"LLM provider: {os.environ.get('NANO_LLM_PROVIDER', 'openai-compatible')}")
    print(f"ExecutionGraph cases: {len(cases)}")
    print(f"Results: {EXECUTIONGRAPH_RESULTS}")

    passed = 0
    failed = 0

    for index, current_case in enumerate(cases, start=1):
        print()
        print("=" * 72)
        print(f"[{index}/{len(cases)}] {current_case}")
        print("=" * 72)

        result = run_executiongraph_case(current_case, client, binary)
        print(f"status: {result['status']}")

        if result["status"] == "passed":
            passed += 1
        else:
            failed += 1
            print(f"error: {result.get('error', 'scheduler failed')}")

    print()
    print("=" * 72)
    print(f"COMPLETE: {passed} passed, {failed} failed")
    print("=" * 72)

    return 0 if failed == 0 else 1


def build_scheduler_for_observation() -> Path:
    cargo = shutil.which("cargo")

    if cargo is None:
        raise RuntimeError("cargo is not installed or not on PATH")

    manifest = ROOT / "scheduler" / "Cargo.toml"
    binary_name = "nano-scheduler.exe" if os.name == "nt" else "nano-scheduler"
    binary = ROOT / "scheduler" / "target" / "debug" / binary_name

    print("Building Rust scheduler...", flush=True)

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
        raise RuntimeError(
            "Rust scheduler build failed\n"
            f"stdout:\n{build.stdout}\n"
            f"stderr:\n{build.stderr}"
        )

    if not binary.is_file():
        raise RuntimeError(
            f"Rust scheduler binary was not produced: {binary}"
        )

    return binary


def run_input(prompt: str) -> int:
    provider = os.environ.get(
        "NANO_LLM_PROVIDER",
        "openai-compatible",
    )

    print()
    print(f"LLM provider: {provider}")

    client = load_llm_client()

    return run_plan(prompt, client)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Nano scheduling fixtures or the real ExecutionGraph observation corpus."
    )

    parser.add_argument(
        "case",
        nargs="?",
        help="scheduling fixture name, e.g. 04_retries/retry_once",
    )

    parser.add_argument(
        "--input",
        help="run arbitrary human-readable input through the configured LLM",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="list available deterministic scheduling fixtures",
    )

    parser.add_argument(
        "--list-executiongraph",
        action="store_true",
        help="list real-LLM ExecutionGraph observation cases",
    )

    parser.add_argument(
        "--executiongraph",
        metavar="CASE",
        help="run one real-LLM ExecutionGraph case",
    )

    parser.add_argument(
        "--all-executiongraph",
        action="store_true",
        help="run the complete real-LLM ExecutionGraph corpus",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="limit the number of ExecutionGraph cases run",
    )

    args = parser.parse_args()

    if args.list:
        for case in discover_scheduling_cases():
            print(case)
        return 0

    if args.list_executiongraph:
        for case in discover_executiongraph_cases():
            print(case)
        return 0

    if args.input is not None:
        return run_input(args.input)

    if args.executiongraph or args.all_executiongraph:
        return run_executiongraph(
            args.executiongraph,
            args.all_executiongraph,
            args.limit,
        )

    if not args.case:
        parser.error(
            "provide a scheduling fixture case, --input, "
            "--executiongraph, --all-executiongraph, or a list option"
        )

    case = args.case.removesuffix(".json").removesuffix(".md")
    available = discover_scheduling_cases()

    if case not in available:
        print(
            f"ERROR: unknown scheduling case: {case}",
            file=sys.stderr,
        )
        print()
        print("Available cases:")

        for available_case in available:
            print(f"  {available_case}")

        return 1

    return run_fixture(case)


if __name__ == "__main__":
    raise SystemExit(main())
