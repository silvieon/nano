# Event Store

Initial backend: SQLite.

Canonical record: serialized protobuf Event.

Properties:
- append-only
- task + sequence indexed
- replayable
- durable across orchestrator disconnects

Possible later backends: PostgreSQL, NATS JetStream, Kafka/Redpanda, etc.

CSV/JSON/Parquet are export projections only.
