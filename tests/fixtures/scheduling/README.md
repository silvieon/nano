# Scheduling fixture corpus

Each scenario has:

- `.md`: human-readable request
- `.json`: deterministic ExecutionGraph fixture standing in for the LLM

Directory progression:

1. basic DAG execution
2. dependency policies
3. failure handling
4. retries
5. recovery/fallback
6. timeouts/deadlines
7. cancellation/pause/resume
8. resource contention/deduplication
9. artifact handling
10. agentic replanning

The `simulate` fields are intentionally part of the test contract. The current
scheduler ignores them; later scheduler/daemon test layers should consume them
to deterministically inject failures, timeouts, and other conditions.
