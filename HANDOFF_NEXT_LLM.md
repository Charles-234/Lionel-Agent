# Lionel Agent: Current Handoff

Date: 2026-09-20
Repository: `D:\Phantom-agent`

## Verified baseline

Run from the repository root with the project virtual environment:

```powershell
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m compileall -q agent agent_registry tools tools_registry audit memory commands providers interfaces identity skills attachments lionel_platform mcp
```

Current result:

- 259 tests passed
- 6 subtests passed
- compilation succeeded

Do not run pytest from the repository root without the `tests` scope. The workspace contains archived/batch trees with duplicate module names.

## Architecture invariants

The security boundary must remain:

```text
input -> normalize -> role -> plan -> authorize -> tool select
-> policy/scope -> executor -> audit -> response
```

Rules:

- `interfaces/` carries input and output only.
- `tools/policy.py` is the policy enforcement point.
- `tools/executor.py` is the execution path.
- Capability discovery is not permission.
- A model, prompt, skill, MCP server, connector, or scheduler must never authorize itself.
- Simulation output remains explicitly unverified.
- Provider diagnostics, secrets, stack traces, and hidden reasoning never reach users.
- Never reset, clean, or restore the intentionally dirty worktree.
- Never commit `.env` or expose its values.

## Implemented features

### Agent brain and governance

- Request normalization and task-type validation.
- Deterministic role selection.
- Deterministic request planning.
- Bounded runtime and bounded runner.
- Confirmation pause/resume support.
- Role/capability authorization.
- Policy-gated tool registry and executor.
- Audit ledger/integration path.
- Session, working, and persistent memory foundations.

Relevant modules: `agent/`, `agent_registry/`, `tools/`, `tools_registry/`, `audit/`, `memory/`.

### Telegram and response quality

- Owner-only admission by default.
- Optional collaborator allowlist foundation.
- Rate limiting.
- Long reply splitting at Telegram-safe boundaries.
- Markdown and newline preservation.
- Sanitized user-facing errors.
- Image routing only for actual image MIME types.
- Documents, audio, voice, and video retain attachment bytes and metadata.

Relevant module: `interfaces/telegram_door.py`.

### Skills and knowledge

- Skill loader and hybrid retriever.
- Skill-assisted chat.
- TTP/public text ingestion and deduplication.
- `/ingest` command support.
- Persistent skill index support.

Relevant modules: `skills/`, `commands/registry.py`.

### Attachment extraction

`attachments/extractor.py` now provides bounded, dependency-optional inspection for:

- Plain text, Markdown, source files, JSON, YAML, and CSV.
- DOCX text via the OOXML archive.
- PDF text when `pypdf` is installed.
- APK archive metadata without executing the APK.
- Image dimensions/format and provider vision routing.
- Optional OCR with Pillow + Tesseract.
- Audio metadata and optional Whisper transcription.
- Video metadata and optional OpenCV inspection.

The extractor clips output, rejects oversized attachments, sanitizes archive paths by reading only known archive members, and never executes attachment content.

Optional media dependencies are listed in `requirements-media.txt`.

### Local model support

`providers/direct.py` and `providers/router.py` support an optional OpenAI-compatible local endpoint for:

- Ollama
- vLLM
- LM Studio

Configuration variables:

```text
LOCAL_LLM_URL=
LOCAL_LLM_API_KEY=local
LOCAL_LLM_MODEL=
```

When both URL and model are configured, the local model is appended to normal failover routing.

### Platform capability contracts

`lionel_platform/` contains declarative contracts for:

- Model profiles.
- Connector profiles.
- MCP server profiles.
- Sandbox profiles for local, Docker, SSH, and Modal.
- Deep codebase context collection.
- Bounded recurring scheduler primitives.

`mcp/registry.py` adds MCP server registration, tool allowlists, and explicit role/tool approval grants.

`mcp/transport.py` now provides:

- Streamable HTTP JSON-RPC sessions.
- Local stdio JSON-RPC sessions.
- MCP initialize, initialized notification, tool discovery, and tool calls.
- Governed MCP tool adapters registered through the normal tool registry.
- `MCP_TOOL_CALL` audit events with sanitized server/tool metadata.

`mcp/recommended.py` defines disabled-by-default entries for Parallel Search,
Playwright, Context7, 21st (`https://21st.dev/api/mcp`, requires the `x-api-key`
header from 21st.dev/mcp), AgentQL (`npx -y agentql-mcp`, expects
`AGENTQL_API_KEY`), and ClickSend (`npx -y @clicksend/clicksend-mcp-server@latest`,
expects `CLICKSEND_USERNAME` and `CLICKSEND_API_KEY`). They are not live-connected
until an operator reviews and enables them. Credentials stay in the operator
environment; the specs themselves are shareable metadata.

These are secure registries and policy inputs. They are not yet full network transports or autonomous execution adapters.

## Not yet implemented or incomplete

These items must not be reported as complete:

1. Live verification and operator configuration for the three recommended MCP servers.
2. Concrete Discord, Slack, WhatsApp, Signal, Email, and Home Assistant adapters.
3. Browser automation service with isolated browser profiles.
4. Actual Docker, SSH, Modal, and local sandbox executors wired through the policy gateway.
5. VS Code extension/UI for one-click multi-file edits and inline code actions.
6. Full multi-file codebase planner/editor with patch review and approval UI.
7. Durable subagent/team orchestration and `@mention` group coordination.
8. Persistent production scheduler/worker service.
9. Reinforcement-learning or automatic self-modification pipeline. This requires strict feedback review, evaluation, rollback, and approval; it must not let the agent rewrite its own policy.
10. Automatic skill synthesis/refinement from successful runs. Current skills are loaded and ingested, but self-generated skills still need human review and provenance.
11. Full OCR/transcription/video frame analysis in the base installation. These are optional and require local model/tool installation.
12. Native Claude/OpenAI/Anthropic-specific direct clients. OmniRoute or the OpenAI-compatible adapter can be used where compatible, but provider-specific streaming, tool calls, and multimodal contracts still need adapters.
13. Production observability, distributed queues, database-backed scheduler state, and horizontal worker scaling.
14. Full MFA/dashboard/invitation UI.

## Recommended next order

1. Enable and live-test one reviewed MCP server through the transport and policy path.
2. Build one connector end to end, preferably Discord or Slack, using the existing Telegram door contract.
3. Add a Docker sandbox executor with explicit filesystem/network scopes and audit events.
4. Add a persistent scheduler backed by SQLite/PostgreSQL and a single worker lease.
5. Add codebase indexing, symbol graph/context retrieval, patch preview, approval, and rollback.
6. Add subagents only after task budgets, role boundaries, cancellation, and audit events are enforced.
7. Add skill synthesis only as reviewed Markdown proposals, never direct automatic activation.

## Official platform links

### Hosting and deployment

- Oracle Cloud Always Free: https://www.oracle.com/cloud/free/
- Oracle Cloud console: https://cloud.oracle.com/
- Google Cloud Run: https://cloud.google.com/run
- Google Cloud free tier: https://cloud.google.com/free
- Render: https://render.com/
- Render pricing: https://render.com/pricing
- Railway: https://railway.com/
- Railway pricing: https://railway.com/pricing
- Fly.io: https://fly.io/
- Fly.io pricing: https://fly.io/docs/about/pricing/
- Hetzner Cloud: https://www.hetzner.com/cloud/

Recommendation: Oracle Always Free is the best no-cost persistent starting point when an account has capacity. Cloud Run is better for stateless HTTP workers but is less convenient for a long-running Telegram poller and local LLMs. No free platform guarantees unlimited uptime, storage, bandwidth, GPU inference, and autoscaling.

### Local models

- Ollama: https://ollama.com/
- Ollama API documentation: https://github.com/ollama/ollama/blob/main/docs/api.md
- vLLM: https://docs.vllm.ai/
- LM Studio: https://lmstudio.ai/

### MCP and automation

- Model Context Protocol: https://modelcontextprotocol.io/
- MCP specification: https://spec.modelcontextprotocol.io/
- Playwright: https://playwright.dev/
- Docker: https://www.docker.com/
- Modal: https://modal.com/

### Messaging and operations

- Telegram Bot API: https://core.telegram.org/bots/api
- Discord developer portal: https://discord.com/developers/applications
- Slack API: https://api.slack.com/
- WhatsApp Business Platform: https://developers.facebook.com/docs/whatsapp/
- Signal: https://signal.org/
- Home Assistant: https://www.home-assistant.io/

### Search and external knowledge

- Brave Search API: https://brave.com/search/api/
- Tavily: https://tavily.com/
- Perplexity API: https://docs.perplexity.ai/

## Continuation prompt for another LLM

You are continuing work on Lionel in `D:\Phantom-agent`. Read this file first and inspect the active source tree, not archived batch folders. Preserve the governance chain and do not bypass `tools/policy.py` or `tools/executor.py`. Do not reset, clean, restore, or delete the intentionally dirty worktree. Never expose `.env`, provider keys, bot tokens, stack traces, or hidden reasoning.

Start with:

```powershell
Set-Location D:\Phantom-agent
.venv\Scripts\python.exe -m pytest tests -q
```

The MCP JSON-RPC transport is now implemented in `mcp/transport.py` but the
recommended servers remain disabled by default. First inspect and live-test one
reviewed server, then implement the next milestones in this order: one real
connector adapter, Docker sandbox execution, persistent scheduler, and deep
codebase patch planning. Add focused tests before broad refactors. Treat
`lionel_platform/` as declarative capability metadata only until an executor is
explicitly wired through the policy gateway. Optional attachment backends are
in `requirements-media.txt`; do not make them mandatory for basic chat startup.

Before claiming completion, rerun the full test suite and compile command, and report implemented features, remaining gaps, and any external services that were not available for live validation.
