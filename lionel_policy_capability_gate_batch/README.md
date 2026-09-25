# Lionel Capability Policy Gate Batch

This is the next governance layer after the Role + Capability and Tool Registries.

It makes the capability-to-tool relationship enforceable at the execution boundary.

## Enforcement

For high-risk/network tools:

`Capability -> registered tool -> policy scope -> execution`

A model, prompt, or skill cannot grant itself permission.

The recon chain now supplies explicit capability context:
- subfinder/httpx -> `reconnaissance`
- nuclei -> `security_testing`

Simulation remains explicit and unverified.

The tests are designed to remain offline except for a real-adapter boundary check;
that check does not require a successful external scan and accepts a controlled
"binary unavailable" result.

## Install

From `D:\phantom-agent`:

```powershell
python .\lionel_policy_capability_gate_batch\install_lionel_policy_capability_gate.py
```

A timestamped backup is created before replacement.
