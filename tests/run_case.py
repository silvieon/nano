import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from nano_orchestrator.compiler import compile_execution_graph
from nano_orchestrator.llm import JsonLLMClient


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "scheduling"


def discover_cases() -> list[str]:
    """Return all scheduling fixtures that have both .md and .json files."""
    cases = []

    for json_file in sorted(FIXTURES.rglob("*.json")):
        md_file = json_file.with_suffix(".md")
        if md_file.is_file():
            cases.append(str(json_file.relative_to(FIXTURES).with_suffix("")))

    return cases


def run_scheduler(plan_json: str) -> tuple[int, str, str]:
    """Build and run the Rust scheduler directly."""
    cargo = shutil.which("cargo")

    if cargo is None:
        raise RuntimeError("cargo is not installed or not on PATH")

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


def run_case(case: str) -> int:
    md_path = FIXTURES / f"{case}.md"
    json_path = FIXTURES / f"{case}.json"

    if not md_path.is_file():
        print(f"ERROR: case not found: {case}")
        return 1

    if not json_path.is_file():
        print(f"ERROR: missing JSON fixture: {json_path}")
        return 1

    prompt = md_path.read_text().strip()
    llm_response = json_path.read_text()

    print()
    print("=" * 72)
    print(f"CASE: {case}")
    print("=" * 72)

    print()
    print("=== HUMAN REQUEST ===")
    print(prompt)

    graph = JsonLLMClient().generate_execution_graph(llm_response)
    plan = compile_execution_graph(graph)

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
    print("=" * 72)
    print(f"EXIT CODE: {exit_code}")
    print("=" * 72)
    print()

    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one Nano scheduling fixture end-to-end."
    )

    parser.add_argument(
        "case",
        nargs="?",
        help="fixture name, e.g. 04_retries/retry_once",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="list available scheduling cases",
    )

    args = parser.parse_args()

    if args.list:
        for case in discover_cases():
            print(case)
        return 0

    if not args.case:
        parser.error(
            "provide a case name or use --list"
        )

    case = args.case.removesuffix(".json").removesuffix(".md")

    available = discover_cases()

    if case not in available:
        print(f"ERROR: unknown case: {case}", file=sys.stderr)
        print()
        print("Available cases:")
        for available_case in available:
            print(f"  {available_case}")
        return 1

    return run_case(case)


if __name__ == "__main__":
    raise SystemExit(main())