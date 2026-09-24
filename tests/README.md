# Nano scheduler testing horizon

This directory contains **tests/ only**. Copy/merge it into the root of the Nano repository.

The `.md` files are human-readable requests. The `.json` files are deterministic stand-ins for the LLM's schema-constrained ExecutionGraph response.

Some scenarios are intentionally tagged `future_behavior` because the current Rust scheduler does not yet implement retries, timeouts, cancellation, conditional branches, or replanning. Those fixtures are test targets/specifications for the next scheduler layers rather than pretending those features already work.

Run from the repository root:

    pytest -q -s tests

For only the existing end-to-end vertical slice:

    pytest -q -s tests/test_human_requests.py

For the new horizon fixture validation:

    pytest -q -s tests/test_scheduler_horizon.py
