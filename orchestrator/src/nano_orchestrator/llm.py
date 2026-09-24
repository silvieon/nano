from __future__ import annotations

import json
from typing import Protocol

from .models import ExecutionGraph


class LLMClient(Protocol):
    def generate_execution_graph(self, prompt: str) -> ExecutionGraph: ...


class JsonLLMClient:
    """Development adapter: accepts an already structured LLM response.

    This keeps the semantic boundary testable without coupling the first
    vertical slice to a specific model provider. A real Ollama/API adapter
    can implement LLMClient later and return the same validated model.
    """

    def generate_execution_graph(self, response_json: str) -> ExecutionGraph:
        return ExecutionGraph.model_validate(json.loads(response_json))
