# LIONEL AGENT — HANDOVER NOTE (auto-generated)

## Status: ALL PHASES COMPLETE AND PUSHED

Repo: https://github.com/Charles-234/Lionel-Agent (branch: master)
Last test run: 212 passed, 6 subtests. Compile check: clean.
Live bot: @GuardianLionel_bot — owner-only (your Telegram ID), running via
`scripts/start_lionel.bat`, autostart task `LionelAgentDoor` (install with
`scripts/install_autostart.ps1`, run once in PowerShell).

## What is done, per phase
- Phase 2-4: governed foundation, agent brain (normalizer, role selector,
  planner, bounded runtime, session state), memory (working, session,
  persistent SQLite with lifecycle/privacy caps).
- Phase 5: bounded runner + confirmation pause/resume + bridge
  (READY_TO_RUN / NEEDS_ROLE / NEEDS_PLAN ...), input safety screen
  (agent/safety.py), controlled external-knowledge store in persistent memory.
- Phase 6-7: Telegram door (interfaces/telegram_door.py) — thin carrier only:
  owner check, stranger refuse+log, reply sanitization, no brain/policy/audit
  inside; plugged into agent chat + command registry.
- Phase 8: production hardening — error lines never leak internals
  (commands/registry.py fixed), logs to logs/ (gitignored), autostart scripts.
- Phase 9 groundwork: identity/ package (pure owner+collaborator allowlist)
  and identity/mfa.py (pure stdlib TOTP — no deps). Dashboard/MFA UI NOT built
  yet — these are the foundations for it.
- External-knowledge: tools/web_fetcher.py — governed URL text fetcher
  (reads only, no code execution), wired through PolicyGateway with the
  research capability; simulation mode returns unverified mock data.
  GitHub private repos / Google Drive / PDF / video-audio extraction are
  NOT done — needs your access tokens and a media-extraction layer (future).

## How to run / restart the bot
  cd D:\Phantom-agent
  scripts\start_lionel.bat
Or install autostart once:
  powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1

## Secrets safety
- .env is gitignored and was NEVER committed. Your bot token and admin ID
  stay local. Verify anytime: `git ls-files .env` (must print nothing).

## Known limitations / next work (the honest list)
1. Dashboard + full MFA flow (Stitch/Figma design, web UI, invite emails) —
   foundations only (identity + TOTP) are in place.
2. Private GitHub repos and Google Drive ingestion — needs OAuth/PAT handling
   design first; never store tokens in plain files.
3. PDF / video / audio learning — needs text-extraction tooling (pypdf,
   whisper, etc.); the governed fetcher currently reads text/HTML only.
4. TTP framework (Tactics/Techniques/Procedures as first-class skill records)
   — the skills/ loader pattern is the template; extend it with source URLs
   via web_fetcher.
5. commands/registry.py reply surface is hardened but could gain rate limits.

## Governance invariants (do not break)
- One chain: input -> normalize -> role -> plan -> authorize -> tool select
  -> policy/scope -> executor -> audit -> response.
- Single governance boundary: tools/policy.py. Single executor: tools/executor.py.
- agent_registry/authorization.py stays pure (no audit/persistence).
- Interfaces carry only; they never think, authorize, or run.
- Simulation output is always marked unverified.
