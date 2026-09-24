# Daemons

Resource-specific services. Language is deliberately not fixed.

Examples:
- `pronsole/`: Python PronsoleD adapter
- `web-search/`
- `filesystem/`
- `document/`
- `codegen/`

Every daemon implements the protobuf ToolService contract. It can run locally, remotely, containerized, or in Kubernetes.
