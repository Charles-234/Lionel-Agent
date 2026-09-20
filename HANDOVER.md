# LIONEL AGENT — HANDOVER NOTE (auto-generated)

## Status: ALL COMMITTED PHASES COMPLETE AND PUSHED

Repo: https://github.com/Charles-234/Lionel-Agent (branch: master)
Latest pushed commit: `0acff05` (on top of `c10aec6`, `1b3fcbb`).
Last test run: 212 passed, 6 subtests. Compile check: clean.
Live bot: @GuardianLionel_bot — owner-only (your Telegram ID), verified
running as one logical process (venv launcher PID + its interpreter child,
started 3:20 AM), logs in `logs/door_stdout.log` / `logs/door_stderr.log`
(both gitignored, both clean).
Open the project in VS Code: `code D:\Phantom-agent` (or File → Open Folder).
Note: GitHub shows your last commit a couple of days older than "today"
because almost everything built here landed in the single `0acff05` push;
if the web view looks behind, hard-refresh (Ctrl+F5) — the push was
confirmed by git (`0acff05..master -> master`).

## Up-to-date diagnosis (what a fresh session should know first)
- Working tree: intentionally dirty. Untracked scratch folders (backups/,
  inspection_* , lionel_*_batch/, v1_tool_inventory/, Armando.txt,
  retriever_diagnostic.py, _role_capability_patch/) are deliberate and must
  NOT be committed or deleted.
- All real source + tests are committed and pushed. `git status` should show
  only those untracked scratch entries.
- `.env` holds your real ADMIN_TELEGRAM_ID + TELEGRAM_BOT_TOKEN and is
  gitignored (`git ls-files .env` must print nothing — verify if paranoid).
- In-progress work started but NOT committed: the TTP ingestion layer
  (`skills/ingest.py` — turning governed-fetched public text into skill
  records the retriever understands). Nothing was written yet; the patterns
  to follow are skills/loader.py `_normalize`, the COMMANDS map in
  commands/registry.py, and tools/web_fetcher.py. A 30-day study-plan corpus
  and similar public material are the intended first test inputs.

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

## Continuation prompt (paste this into a fresh Cline session)

<user_input mode="act">
Repo D:\Phantom-agent (Lionel agent), remote Charles-234/Lionel-Agent, branch
master, commit 0acff05. Read HANDOVER.md first — it lists the up-to-date
diagnosis and governance invariants. Rules: capability is not permission; one
chain (input -> normalize -> role -> plan -> authorize -> tool select ->
policy/scope -> executor -> audit -> response); single boundary tools/policy.py;
single executor tools/executor.py; interfaces carry only; never bypass, reorder
or duplicate the chain; no policy in handlers/providers/planners; repo is
intentionally dirty — never git reset/clean/checkout/restore; never touch the
untracked scratch folders; never commit or push .env (it is gitignored — keep
it that way); commit/push only when I say so. Tests: .venv\Scripts\python.exe
-m pytest tests -q (scope to tests/; do not run pytest from repo root — backup
and batch folders contain duplicate module names). Compile: .venv\Scripts\
python.exe -m compileall -q agent agent_registry tools tools_registry audit
memory commands providers interfaces identity skills. Do not expose secrets,
tokens, stack traces or provider diagnostics in any user-facing output.
TASK: finish the TTP ingestion layer described in HANDOVER.md — a pure
skills/ingest.py that turns governed-fetched public text (via the existing
web_fetch tool through the PolicyGateway, capability `research`, role
`virtual_assistant`) into normalized skill records the retriever already
understands (follow skills/loader.py `_normalize` exactly), deduped by id,
appended atomically to the skills index, plus an `/ingest <url>` command in
commands/registry.py following the COMMANDS map pattern, plus
tests/test_ttp_ingest.py (offline: fake fetch + tmp index path; no network in
tests). Refuse nothing silently: if the fetch fails or the text is unusable,
return a short safe line. Keep every layer's role unchanged; the ingest
command must not authorize or execute anything itself — it goes through the
governed executor path like every other tool use. Then run the full tests +
compile check and report results without starting the bot (it may already be
running; do not spawn a second instance).
</user_input>

## Delivery of this note
- Telegram handover note sent to owner ID via the live bot.
- Email NOT sent: no SMTP credentials exist in .env; do not invent a mailer.

