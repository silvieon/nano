# Nano runtime sketch

Current vertical slice:

`LLM structured output -> Python semantic graph -> plan compiler -> Runtime IR JSON -> Rust DAG scheduler`

The Rust scheduler intentionally simulates task execution and prints its execution trace. gRPC/call-plane integration comes after this boundary is stable.

## Run the vertical slice

```bash
cd orchestrator
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
PYTHONPATH=src python -m nano_orchestrator < src/nano_orchestrator/example_graph.json > /tmp/runtime-plan.json

cd ../scheduler
cargo run < /tmp/runtime-plan.json
```

The first two independent tasks should start together; `resolve` waits for both; `report` waits for `resolve`.

## Running the current vertical slice

From the repository root:

```bash
python3 -m pip install -e orchestrator
pytest -q
```

To see the human request and the Rust scheduler's stdout trace:

```bash
pytest -s tests/test_human_requests.py
```

The scheduler is launched by pytest for each integration case; there is no scheduler daemon to start separately yet.
