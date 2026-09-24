from __future__ import annotations

import json
import sys

from .compiler import compile_execution_graph
from .llm import JsonLLMClient


def main() -> None:
    """Read a structured LLM response and emit Runtime IR JSON.

    This is intentionally a pipe-friendly boundary:
        LLM response JSON -> Python validation/compiler -> Rust scheduler stdin
    """
    response = sys.stdin.read()
    if not response.strip():
        raise SystemExit("expected execution-graph JSON on stdin")

    graph = JsonLLMClient().generate_execution_graph(response)
    plan = compile_execution_graph(graph)
    print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
