# Lionel Architecture v1 — Capability/Tool Governance

This package implements the first architectural hardening layer identified in the Lionel audit.

## Added
- `tools/base.py`: richer tool manifest + explicit execution provenance.
- `tools/policy.py`: central policy gateway and explicit authorization scopes.
- `tools/registry.py`: one registry for discoverable tools and policy-enforced execution.
- `tools/executor.py`: execution facade for chains and future agent tool calls.
- `chains/recon.py`: migrated from direct tool instantiation to registry/policy execution.
- `tests/test_governed_tools.py`: tests for deny-by-default, simulation provenance and scope boundaries.

## Security behavior
- Real network/security tools require an explicit authorization scope.
- Targets are not inferred as authorized from user intent.
- Simulation must be explicitly requested and is always `verified=False`.
- Tool calls no longer need to bypass a central gate.

## Installation
Copy these files into the corresponding paths in `D:\phantom-agent`.
Do not overwrite `.env` or other unrelated files.

Then run the verification commands from the main project.
