#!/usr/bin/env python3

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from nano_orchestrator.compiler import compile_execution_graph
from nano_orchestrator.llm import JsonLLMClient, load_llm_client


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "scheduling"


def discover_cases() -> list[str]:
    cases = []

    for json_file in sorted(FIXTURES.rglob("*.json")):
        md_file = json_file.with_suffix(".md")

        if md_file.is_file():
            cases.append(
                str(json_file.relative_to(FIXTURES).with_suffix(""))
            )

    return cases


def run_scheduler(plan_json: str) -> tuple[int, str, str]:
    cargo = shutil.which("cargo")

    if cargo is None:
        raise RuntimeError(
            "cargo is not installed or not on PATH"
        )

    manifest = ROOT / "scheduler" / "Cargo.toml"
    binary = ROOT / "scheduler" / "target" / "debug" / "nano-scheduler"

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
    md_path = FIXTURES / f"{case}.md"
    json_path = FIXTURES / f"{case}.json"

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


def run_input(prompt: str) -> int:
    provider = __import__(
        "os"
    ).environ.get("NANO_LLM_PROVIDER", "openai-compatible")

    print()
    print(f"LLM provider: {provider}")

    client = load_llm_client()

    return run_plan(prompt, client)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a Nano scheduling fixture or arbitrary user input."
    )

    parser.add_argument(
        "case",
        nargs="?",
        help="fixture name, e.g. 04_retries/retry_once",
    )

    parser.add_argument(
        "--input",
        help="run arbitrary human-readable input through the configured LLM",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="list available scheduling fixtures",
    )

    args = parser.parse_args()

    if args.list:
        for case in discover_cases():
            print(case)

        return 0

    if args.input is not None:
        return run_input(args.input)

    if not args.case:
        parser.error(
            "provide a fixture case, --input, or --list"
        )

    case = args.case.removesuffix(".json").removesuffix(".md")

    available = discover_cases()

    if case not in available:
        print(
            f"ERROR: unknown case: {case}",
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