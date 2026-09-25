# Lionel Audit Ledger Batch

Installs a compact, local SQLite audit ledger.

Records:
- policy decisions
- tool executions
- verification results
- compact error codes

It deliberately does NOT store:
- prompts or full model responses
- chain-of-thought
- API keys/tokens/passwords
- raw network targets (targets are fingerprinted)

The ledger is currently standalone. Integration with the policy gateway
and execution facade is intentionally the next controlled step, after
these storage and sanitization tests pass.
