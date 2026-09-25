# Lionel Tool Registry Batch

This adds the next governance layer after the Role + Capability Registry.

## What it does

1. Gives each tool a stable identity and machine-readable metadata.
2. Maps tools to Lionel capabilities.
3. Distinguishes implemented tools from planned integrations.
4. Records risk, network access, target authorization, simulation support, and provenance.
5. Provides capability-to-tool resolution without bypassing the Policy Gateway.

## Important

This batch does **not** make an external repository executable. Planned tools such as
Amass, recon-ng, SpiderFoot, and Ghidra are registered as disabled/unimplemented
until a real adapter exists and is tested.

The existing policy layer remains authoritative for execution.

## Install

Run from `D:\phantom-agent`:

```powershell
python .\lionel_tool_registry_batch\install_lionel_tool_registry.py
```
