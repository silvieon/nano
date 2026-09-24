from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any, Protocol
from urllib import request

from .models import ExecutionGraph


class LLMClient(Protocol):
    """Provider-independent interface used by the Nano orchestrator."""

    def generate_execution_graph(self, prompt: str) -> ExecutionGraph:
        ...


class JsonLLMClient:
    """Deterministic fixture client used by tests."""

    def generate_execution_graph(self, response: str) -> ExecutionGraph:
        payload = json.loads(response)
        return ExecutionGraph.model_validate(payload)


class OpenAICompatibleLLM:
    """LLM client for OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate_execution_graph(self, prompt: str) -> ExecutionGraph:
        schema = ExecutionGraph.model_json_schema()

        system_prompt = (
            "You are the planning component of Nano. "
            "Convert the user's request into an execution graph. "
            "Return only JSON matching the supplied schema. "
            "Do not execute tools yourself."
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "execution_graph",
                    "strict": True,
                    "schema": schema,
                },
            },
        }

        body = json.dumps(payload).encode("utf-8")

        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        with request.urlopen(req, timeout=self.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))

        content = result["choices"][0]["message"]["content"]

        if isinstance(content, list):
            text_parts = []

            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))

            content = "".join(text_parts)

        if not isinstance(content, str):
            raise ValueError("LLM returned non-text content")

        try:
            graph_payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "LLM returned invalid JSON for ExecutionGraph"
            ) from exc

        return ExecutionGraph.model_validate(graph_payload)


def load_custom_adapter(spec: str) -> LLMClient:
    """
    Load a user-defined adapter.

    Example:
        NANO_LLM_ADAPTER=my_adapter:MyLLM
    """
    try:
        module_name, class_name = spec.split(":", 1)
    except ValueError as exc:
        raise ValueError(
            "NANO_LLM_ADAPTER must have the form module:ClassName"
        ) from exc

    module = importlib.import_module(module_name)
    adapter_class = getattr(module, class_name)

    client = adapter_class()

    if not hasattr(client, "generate_execution_graph"):
        raise TypeError(
            f"{spec} does not implement generate_execution_graph()"
        )

    return client


def load_llm_client() -> LLMClient:
    """
    Construct the configured LLM provider.

    Supported providers:

        fixture
            Deterministic JSON fixture client.

        openai-compatible
            Any OpenAI-compatible chat-completions endpoint.

        custom
            Python adapter specified by NANO_LLM_ADAPTER.
    """
    provider = os.getenv("NANO_LLM_PROVIDER", "openai-compatible")

    if provider == "fixture":
        return JsonLLMClient()

    if provider == "openai-compatible":
        base_url = os.getenv(
            "NANO_LLM_BASE_URL",
            "http://localhost:11434/v1",
        )
        api_key = os.getenv("NANO_LLM_API_KEY", "local")
        model = os.getenv("NANO_LLM_MODEL")

        if not model:
            raise RuntimeError(
                "NANO_LLM_MODEL must be set when using "
                "the openai-compatible provider"
            )

        return OpenAICompatibleLLM(
            base_url=base_url,
            api_key=api_key,
            model=model,
        )

    if provider == "custom":
        adapter = os.getenv("NANO_LLM_ADAPTER")

        if not adapter:
            raise RuntimeError(
                "NANO_LLM_ADAPTER must be set when using "
                "the custom provider"
            )

        return load_custom_adapter(adapter)

    raise ValueError(
        f"Unknown NANO_LLM_PROVIDER: {provider!r}"
    )