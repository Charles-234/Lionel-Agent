# Lionel MCP Integration

`mcp/registry.py` provides the first secure MCP boundary. It registers server
metadata and explicit role/tool grants; it does not start arbitrary commands or
execute MCP tools by itself. A future transport adapter must call the existing
policy gateway, require a role and capability, and record the action in audit.

Servers must be disabled by default and every tool must be allowlisted. Keep
secrets in environment variables or a secret manager rather than in this
directory.

