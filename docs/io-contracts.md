# I/O Contracts

| Boundary | Input | Output | Canonical format |
|---|---|---|---|
| User -> orchestrator | text | goal/context | UTF-8 |
| Orchestrator <-> LLM | prompt/context | decision | text + schema-constrained JSON |
| Orchestrator -> scheduler | execution graph | task commands | typed model |
| Scheduler <-> call plane | tasks/events | RPC traffic | gRPC + Protobuf |
| Call plane <-> daemon | requests/events | results/control | gRPC + Protobuf |
| Runtime -> event store | events | replay/query | Protobuf |
| Event store -> analytics | event projections | datasets | CSV/JSON/Parquet |
| Daemon -> resource | resource-specific | resource-specific | HTTP/SSH/serial/filesystem/etc. |

## Task lifecycle

CREATED -> READY -> RUNNING -> SUCCEEDED/FAILED/CANCELLED/PAUSED

A running task can emit HEARTBEAT and PROGRESS events. Heartbeats are telemetry/observations, not leases.

A transport disconnect must not implicitly terminate a task.

## Event envelope

Every event should contain:
- event ID
- task ID
- optional parent task ID
- monotonically increasing task sequence
- timestamp
- producer
- schema version
- typed payload (`oneof`)

## Search results

Search-oriented daemons should return normalized candidates:

FOUND -> candidates + source/evidence metadata
NONE -> reason
AMBIGUOUS -> candidates

Each search tool may return its closest match. The orchestrator owns semantic arbitration when multiple tools return plausible objects.

## Long-running work

Start -> Accepted -> Progress*/Heartbeat* -> Result/Failure

Control operations can include Pause, Resume, Cancel.

Large artifacts should be references, not embedded repeatedly in event messages.
