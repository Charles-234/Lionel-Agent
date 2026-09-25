# Lionel Role + Capability Batch

This batch adds the first machine-readable Role Registry and Capability Registry.

## Design

- Lionel remains one core agent; roles are metadata, not 19 separate agents.
- Roles describe domains, skill categories, capability categories, preferred task types,
  risk level, and expected outputs.
- Capabilities describe what Lionel can potentially do.
- Authorization remains the responsibility of the existing policy/tool governance layer.
- This batch does not invent or enable GitHub integration, MCP servers, Ghidra, or other
  tools that have not yet been implemented and verified.

## Install

From `D:\phantom-agent` after extracting this folder:

```powershell
python .\lionel_role_capability_batch\install_lionel_role_capability.py
```

The installer creates a timestamped backup before changing the project.
