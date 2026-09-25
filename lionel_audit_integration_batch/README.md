# Lionel Audit Integration Batch

Integrates the verified SQLite audit ledger at the single tool execution
facade.

Safety properties:
- audit request is recorded before tool execution
- audit write failure aborts execution (fail closed)
- result/verification status is recorded after execution
- raw targets are fingerprinted by the ledger
- secrets are redacted
- prompts and chain-of-thought are not stored

This batch assumes the existing capability-aware `tools.registry` and
`tools.executor` architecture is present. The installer backs up the
existing executor and integration tests before replacement.
