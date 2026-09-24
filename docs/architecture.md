# Architecture

## 1. Orchestrator — Python

Owns semantic reasoning:
- interpret user goals
- decompose work
- construct/revise execution graphs
- arbitrate search results
- decide when evidence is sufficient
- synthesize the final response

Input: user text, runtime state, relevant event history, service capabilities.

Output: typed task-graph objects and scheduler requests.

LLM output may be JSON constrained by a schema/Pydantic model. That JSON is immediately validated and converted to typed Python objects; it is not the RPC protocol.

## 2. Scheduler — Rust

Owns deterministic execution:
- DAG readiness
- parallel fan-out/fan-in
- bounded concurrency
- retries
- cancellation
- task state
- deadlines
- RPC invocation

Input: typed task graph + runtime events.

Output: gRPC calls + task lifecycle events.

No LLM reasoning belongs here.

## 3. Call Plane — Rust

Owns transport:
- gRPC
- service registration/discovery
- request correlation
- streaming events
- connection/reconnection behavior

It does not decide task meaning.

## 4. Daemons — language agnostic

Each daemon owns actual resource execution. A daemon may be Python, Rust, Go, C/C++, etc., provided it implements the protobuf service contract.

Examples:
- Python PronsoleD adapter
- web search
- filesystem
- document renderer
- code generation

Daemons own resource state and continue independently of an orchestrator connection.

## 5. Event Store

Canonical format: Protobuf events.

Initial implementation: SQLite with append-only event rows containing the serialized protobuf payload.

Exports are projections:
- CSV: tabular analysis
- JSON: human/API interchange
- Parquet: analytics

## 6. Physical/API I/O

Daemons may touch HTTP, filesystem, SMB, SSH, serial/USB, printers, GPUs, etc. The orchestrator should not directly own these resource connections.

## Kubernetes mapping

Later, services can become Deployments/StatefulSets/Jobs. Physical-resource daemons may remain outside Kubernetes and be reached over gRPC.
