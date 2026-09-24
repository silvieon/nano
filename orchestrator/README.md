# Nano Orchestrator

The Nano orchestrator owns semantic planning and compilation.

The orchestrator does not depend on a specific LLM provider.

## Architecture

```text
human input
    |
    v
LLMClient
    |
    v
ExecutionGraph
    |
    v
Plan Compiler
    |
    v
RuntimePlan
    |
    v
Rust Scheduler