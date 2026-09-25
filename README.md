# Nano

Nano is a distributed, agentic execution runtime designed to turn human-readable requests into executable, observable work.

The core architecture separates **semantic reasoning** from **deterministic execution**:

```text
Human request
     │
     ▼
┌───────────────┐
│      LLM      │  user-selected / provider-independent
└───────┬───────┘
        │
        │ ExecutionGraph
        ▼
┌───────────────────┐
│  Plan Compiler    │
└─────────┬─────────┘
          │
          │ RuntimePlan
          ▼
┌───────────────────┐
│  Rust Scheduler   │
└─────────┬─────────┘
          │
          ▼
   Tools / Daemons
```

The LLM is responsible for deciding **what should happen**. The runtime is responsible for deciding **how that work executes**.

## Current status

Nano currently has a working vertical slice from human-readable requests through the Python orchestrator and plan compiler into a Rust scheduler.

The current development interface is:

```text
human-readable input
        ↓
LLM / deterministic fixture
        ↓
Pydantic ExecutionGraph
        ↓
Plan Compiler
        ↓
RuntimePlan
        ↓
Rust Scheduler
        ↓
human-readable scheduler trace
```

The scheduler currently supports deterministic task state transitions, dependency handling, parallel execution, simulated failures, retries, failure propagation, and related test scenarios. Additional capabilities remain under active development and are represented by explicit future-behavior tests where appropriate.

## LLM architecture

Nano does **not** depend on a particular LLM provider.

The orchestrator depends on an `LLMClient` interface whose job is to turn human-readable input into a validated `ExecutionGraph`.

```python
class LLMClient(Protocol):
    def generate_execution_graph(
        self,
        prompt: str,
    ) -> ExecutionGraph:
        ...
```

This allows the model/provider to be selected independently from the runtime.

Supported paths currently include:

- deterministic JSON fixtures for reproducible tests
- OpenAI-compatible APIs
- user-defined Python adapters

An OpenAI-compatible endpoint can be configured with:

```bash
export NANO_LLM_PROVIDER=openai-compatible
export NANO_LLM_BASE_URL=https://example.com/v1
export NANO_LLM_API_KEY=your-api-key
export NANO_LLM_MODEL=your-model
```

A local OpenAI-compatible server can be used in the same way.

Custom providers can implement `LLMClient` and be selected through configuration without modifying the compiler or scheduler.

## Running Nano

Install the orchestrator:

```bash
python3 -m pip install -e orchestrator
```

### Run the test suite

```bash
pytest -q -s tests
```

The test suite uses deterministic LLM fixtures so compiler and scheduler behavior does not depend on network access or model nondeterminism.

### Run one scheduling scenario

Available scenarios can be listed with:

```bash
python tests/run_case.py --list
```

Run an individual fixture:

```bash
python tests/run_case.py 04_retries/retry_once
```

This displays:

1. the human-readable request
2. the compiled runtime plan
3. the Rust scheduler trace
4. the scheduler exit code

### Run arbitrary human input

With an LLM provider configured:

```bash
python tests/run_case.py --input \
    "Check the printer status and save the result."
```

This exercises the real planning boundary:


```text
your input
    ↓
configured LLM
    ↓
ExecutionGraph
    ↓
compiler
    ↓
RuntimePlan
    ↓
Rust scheduler
    ↓
console trace
```

## Execution model

The semantic planning layer produces an `ExecutionGraph`.

The compiler translates that graph into a simpler runtime representation suitable for deterministic execution.

The Rust scheduler then manages task execution without requiring LLM reasoning for ordinary scheduling decisions.

Conceptually:

```text
ExecutionGraph
      │
      │ compile
      ▼
 RuntimePlan
      │
      │ execute
      ▼
 Rust Scheduler
      │
      ├── dependency resolution
      ├── readiness
      ├── parallel execution
      ├── retries
      ├── failure propagation
      └── state transitions
```

The scheduler should remain deterministic and operational. Agentic reasoning belongs above it.

## Testing horizon

The scheduling test corpus is organized around increasingly complex execution behavior:

```text
tests/
└── fixtures/
    └── scheduling/
        ├── 01_basic/
        ├── 02_dependencies/
        ├── 03_failures/
        ├── 04_retries/
        ├── 05_recovery/
        ├── 06_time/
        ├── 07_control/
        ├── 08_resources/
        ├── 09_artifacts/
        └── 10_agentic/
```

Each scenario uses a pair of files:

```text
scenario.md
scenario.json
```

The `.md` file contains the human-readable request.

The `.json` file is a deterministic stand-in for the schema-constrained LLM response.

This makes the compiler and scheduler testable independently of a live model while preserving the same `ExecutionGraph` boundary used by the real LLM path.

Some scenarios are intentionally marked as future behavior. Those tests describe capabilities that are part of the intended runtime model but are not yet fully implemented.

## Architecture boundaries

Nano deliberately keeps several responsibilities separate.

### LLM

The LLM handles semantic reasoning:

- interpreting human requests
- decomposing work
- selecting appropriate operations
- determining semantic dependencies
- producing an `ExecutionGraph`
- replanning when execution produces information that changes the required work

### Plan Compiler

The compiler translates the rich semantic execution graph into a runtime-oriented representation.

It is the boundary between:

```text
semantic plan
```

and:

```text
deterministic execution plan
```

### Rust Scheduler

The scheduler handles deterministic runtime behavior:

- task state
- dependency resolution
- readiness
- execution
- concurrency
- retries
- failure propagation
- cancellation
- runtime events

The scheduler does not become an LLM agent.

### Daemons

Actual tools and resource integrations are intended to live behind daemonized services.

A daemon owns the details of its resource or tool rather than requiring the scheduler to understand those details.

Examples include:

- 3D printers
- filesystem operations
- search services
- external APIs
- hardware resources

### Replanning

Agentic replanning belongs at the orchestrator boundary.

The intended flow is:

```text
Human request
     ↓
LLM
     ↓
ExecutionGraph
     ↓
Compiler
     ↓
RuntimePlan
     ↓
Scheduler
     ↓
execution event / failure / discovered fact
     ↓
Orchestrator
     ↓
LLM replan
     ↓
new ExecutionGraph
```

This keeps the scheduler deterministic while allowing the overall system to remain agentic.

## Repository layout

```text
nano/
├── orchestrator/
│   └── src/
│       └── nano_orchestrator/
│           ├── compiler.py
│           ├── llm.py
│           ├── models.py
│           └── ...
│
├── scheduler/
│   ├── Cargo.toml
│   └── src/
│       └── main.rs
│
├── daemons/
│   └── ...
│
├── proto/
│   └── ...
│
├── tests/
│   ├── run_case.py
│   ├── test_human_requests.py
│   ├── test_compiler.py
│   ├── test_scheduler_horizon.py
│   └── fixtures/
│       ├── scheduling/
│       └── executiongraph/
│
└── README.md
```

## Design direction

Nano is being developed toward a distributed runtime in which:

- the LLM provides semantic intelligence
- the compiler translates semantic intent into executable runtime IR
- Rust provides deterministic scheduling
- daemons own concrete tools and resources
- communication uses typed service contracts
- execution can be observed and persisted
- long-running work can survive individual process or connection failures
- Kubernetes can serve as a deployment substrate without becoming an architectural dependency

## ExecutionGraph observation corpus

The repository also contains a real-LLM planning corpus under:

```text
tests/
└── fixtures/
    └── executiongraph/
        ├── 01_basic/
        ├── 02_dependencies/
        ├── 03_parallelism/
        ├── 04_fanout_fanin/
        ├── 05_conditionals/
        ├── 06_retries_and_recovery/
        ├── 07_artifacts/
        ├── 08_complex_requests/
        ├── 09_agentic/
        ├── 10_ambiguity/
        └── 11_stress/
```

Unlike the deterministic scheduling fixtures, these cases intentionally do
not contain expected `.json` graphs. The human-readable `.md` prompt is sent
to the configured real LLM so that Nano's actual planning behavior can be
observed.

List the corpus:

```bash
python tests/run_case.py --list-executiongraph
```

Run one case:

```bash
python tests/run_case.py --executiongraph 02_dependencies/01_sequential_chain
```

Run a small smoke test:

```bash
python tests/run_case.py --all-executiongraph --limit 5
```

Run the complete corpus:

```bash
python tests/run_case.py --all-executiongraph
```

Each case records its observed artifacts under:

```text
tests/results/executiongraph/<case>/
    input.md
    execution_graph.json
    runtime_plan.json
    scheduler_trace.txt
    result.json
```

These results are intentionally ignored by Git. The corpus is for observing
model behavior first; it should not assume that a particular LLM will produce
one exact graph for every natural-language request.

The current vertical slice intentionally starts smaller: human input → plan → Rust scheduler → observable trace.

The goal is to build the distributed runtime around that boundary without collapsing semantic reasoning and deterministic execution into the same component.

## Plugging in different LLMs

Nano is intentionally **LLM-provider agnostic**.

The orchestrator does not depend on OpenAI, Anthropic, Google, or any particular model. The only contract between Nano and the model layer is:

```python
class LLMClient(Protocol):
    def generate_execution_graph(
        self,
        prompt: str,
    ) -> ExecutionGraph:
        ...
```

The selected LLM's job is to turn human-readable input into a schema-valid `ExecutionGraph`. Everything after that is handled by Nano's compiler and runtime.

### Hosted / corporate LLMs

For a hosted model, there are two approaches.

#### OpenAI-compatible APIs

If the provider exposes an OpenAI-compatible chat-completions endpoint, configure Nano with:

```bash
export NANO_LLM_PROVIDER=openai-compatible
export NANO_LLM_BASE_URL="https://provider.example/v1"
export NANO_LLM_API_KEY="your-api-key"
export NANO_LLM_MODEL="your-model"
```

Then:

```bash
python tests/run_case.py --input \
    "Check the printer status and save the result."
```

Nano sends the request to the configured endpoint and validates the returned `ExecutionGraph` before compiling it.

This interface is useful because the runtime does not need to know which company operates the endpoint.

#### Native provider adapters

Some providers expose APIs or SDKs whose interfaces differ from the OpenAI-compatible interface.

For those providers, Nano can use a dedicated adapter implementing `LLMClient`.

Conceptually:

```text
                    Nano
                     │
                     ▼
                 LLMClient
                /    |     \
               /     |      \
              ▼      ▼       ▼
           OpenAI  Anthropic  Google
           adapter  adapter   adapter
```

Each adapter translates between the provider's native API and Nano's common `ExecutionGraph` contract.

This keeps provider-specific authentication, request formatting, SDK usage, and response parsing outside the rest of Nano.

### Open-source and local LLMs

Open-source models can be integrated using the same boundary.

A common deployment pattern is:

```text
┌──────────────────────┐
│   Nano Orchestrator  │
└──────────┬───────────┘
           │
           │ OpenAI-compatible HTTP
           ▼
┌──────────────────────┐
│ Model Server         │
│                      │
│ Ollama               │
│ vLLM                 │
│ llama.cpp server     │
│ or another server    │
└──────────┬───────────┘
           │
           ▼
      Local / remote
       open model
```

For example, if the model server exposes an OpenAI-compatible endpoint:

```bash
export NANO_LLM_PROVIDER=openai-compatible
export NANO_LLM_BASE_URL="http://localhost:11434/v1"
export NANO_LLM_API_KEY="local"
export NANO_LLM_MODEL="your-model"
```

Nano then treats the local model exactly like any other compatible LLM endpoint.

The model itself can live:

- on the same machine as Nano
- on another machine on the local network
- on a dedicated GPU server
- inside a container
- inside a Kubernetes deployment

Nano does not need to know where the model is running.

### Writing a custom LLM adapter

If a model or provider does not expose an interface Nano already supports, implement `LLMClient`.

For example:

```python
from nano_orchestrator.models import ExecutionGraph


class MyLLM:
    def generate_execution_graph(
        self,
        prompt: str,
    ) -> ExecutionGraph:
        response = call_my_model(prompt)

        return ExecutionGraph.model_validate(
            response
        )
```

Then configure Nano to load it:

```bash
export NANO_LLM_PROVIDER=custom
export NANO_LLM_ADAPTER=my_adapter:MyLLM
```

The rest of Nano remains unchanged.

### The important boundary

Adding a new model should **not** require changes to:

- the Rust scheduler
- the plan compiler
- daemon implementations
- runtime task semantics
- the event system
- resource integrations

The adapter only needs to turn:

```text
human-readable request
        ↓
     your LLM
        ↓
ExecutionGraph
```

Once Nano has the `ExecutionGraph`, the model has effectively handed control to the runtime:

```text
LLM
 │
 │ ExecutionGraph
 ▼
Compiler
 │
 │ RuntimePlan
 ▼
Rust Scheduler
 │
 ▼
Tools / Daemons
```

This separation allows Nano to switch between large hosted models, smaller local models, and custom models without changing the execution runtime.