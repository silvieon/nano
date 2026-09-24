# PronsoleD Adapter

First real long-running integration target.

PronsoleD remains Python and is installed with:

    python3 -m pip install .

The adapter exposes printer operations through gRPC instead of making the orchestrator SSH directly into the printer host.

Likely operations:
- status
- start
- pause
- resume
- abort
- telemetry

Print tasks should emit heartbeat/progress events.
