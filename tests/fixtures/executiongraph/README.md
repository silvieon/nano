# Nano ExecutionGraph Observation Corpus

This corpus is for evaluating real LLM-generated `ExecutionGraph` plans.

Unlike `tests/fixtures/scheduling/`, these cases intentionally do **not**
contain expected `.json` graphs. The human-readable `.md` prompt is the
input to the real LLM.

For each case, capture:
1. Human input
2. ExecutionGraph
3. RuntimePlan
4. Rust scheduler trace
5. Validation/compilation errors

The purpose is observation first. Do not modify prompts to make the model
succeed. Failures are data.

Categories:
- `01_basic` — single-task requests
- `02_dependencies` — sequential/data-dependent work
- `03_parallelism` — independent concurrent work
- `04_fanout_fanin` — parallel branches followed by synthesis
- `05_conditionals` — result-dependent branching
- `06_retries_and_recovery` — retries and fallback behavior
- `07_artifacts` — artifact-producing pipelines
- `08_complex_requests` — realistic multi-step plans
- `09_agentic` — discovered-information-driven plans
- `10_ambiguity` — underspecified requests
- `11_stress` — wide, deep, and mixed graphs
