from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    service: str
    operation: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    timeout_ms: int = 30_000
    retry_limit: int = 0


class ExecutionGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    nodes: list[GraphNode]


class RuntimeTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    service: str
    operation: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    timeout_ms: int = 30_000
    retry_limit: int = 0


class RuntimePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    tasks: list[RuntimeTask]