# Phantom Agent

<div align="center">

  <!-- ============================================================================
       CINEMATIC CAPSULE BANNER — Teal/Mint #009688 palette, animated capsule render
  ============================================================================ -->
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="#gh-dark-mode-only"/>
    <source media="(prefers-color-scheme: light)" srcset="#gh-light-mode-only"/>
    <img
      src="https://capsule-render.vercel.app/api?type=waving&color=009688&height=260&section=header&text=Phantom%20Agent&fontSize=70&fontColor=ffffff&animation=twinkling&descSize=18&desc=Agentic%20Telegram%20Automation&descAlignY=65"
      width="100%"
      alt="Phantom Agent — animated teal capsule banner"
    />
  </picture>

  <br />

  <!-- ============================================================================
       TECH SHIELDS — style=for-the-badge
  ============================================================================ -->
  <a href="https://www.python.org/">
    <img
      src="https://img.shields.io/badge/Language-Python%203.11+-3776AB?style=for-the-badge&logo=python&logoColor=white"
      alt="Python"
    />
  </a>
  <a href="https://core.telegram.org/bots/api">
    <img
      src="https://img.shields.io/badge/Telegram-Bot%20API-009688?style=for-the-badge&logo=telegram&logoColor=white"
      alt="Telegram Bot API"
    />
  </a>
  <a href="https://github.com/Charles-234/Phantom-agent/actions">
    <img
      src="https://img.shields.io/badge/Automation-Agentic%20Workflow-009688?style=for-the-badge&logo=githubactions&logoColor=white"
      alt="Automation"
    />
  </a>
  <a href="https://owasp.org/www-project-top-ten/2021/A05_2021-Security_Misconfiguration">
    <img
      src="https://img.shields.io/badge/OWASP-A05%20Hardened-2ecc71?style=for-the-badge&logo=shield&logoColor=white"
      alt="OWASP Hardened"
    />
  </a>

  <br />
  <br />

  <!-- ============================================================================
       LIVE REPOSITORY WIDGET — GitHub Readme Stats Repo Card, tokyonight theme
  ============================================================================ -->
  <a href="https://github.com/Charles-234/Phantom-agent">
    <img
      src="https://github-readme-stats.vercel.app/api/pin/?username=Charles-234&repo=Phantom-agent&theme=tokyonight&show_owner=true"
      width="490"
      alt="Phantom Agent repository card"
    />
  </a>

</div>

<br />

---

## 👋 About Phantom Agent

**Phantom Agent** is a hardened, production-grade agentic automation layer built around a Telegram bot interface. It turns chat messages into governed, auditable actions: role-based planning, provider failover routing, session state, input validation, and exception recovery — all without hardcoded secrets.

> ⚠️ **Security notice:** This repository is prepared for public release. All runtime credentials (Telegram bot token, provider API keys, admin IDs) are intentionally absent. They are injected exclusively through environment variables and a local `.env` file that is strictly gitignored. See **[Security & Configuration](#-security--configuration)** below.


---

## 🔐 Security & Configuration

### OWASP A05:2021 — Security Misconfiguration (hardened)

| Safeguard | Implementation |
|---|---|
| No hardcoded secrets | Every credential resolves from environment variables via `config.py` (`os.environ.get`). |
| Secret files excluded from Git | `.env`, `.env.*`, `config.json`, `*.key`, `*.pem`, `credentials*`, `secrets*`, `Armando.txt` are all gitignored. |
| Template-only defaults | `.env.example` documents every required key without real values. |
| Dependency isolation | `node_modules/`, `.venv/`, `__pycache__/`, and interpreter caches are ignored. |
| Error handling | Provider/internal errors are logged server-side only; users receive sanitized messages. |

### First-time setup

```bash
# 1. Clone the public repo
git clone https://github.com/Charles-234/Phantom-agent.git
cd Phantom-agent

# 2. Create your local environment file from the template
cp .env.example .env
#   ^^^ Fill in your own values. .env is never committed.

# 3. Install dependencies
pip install -r requirements.txt

# 4. Validate configuration
python config.py

# 5. Run
python cli.py
```

Required environment variables (`ADMIN_TELEGRAM_ID`, `OMNIROUTE_URL`, `OMNIROUTE_API_KEY`, `TELEGRAM_BOT_TOKEN`) plus optional provider keys are all listed in **[`.env.example`](./.env.example)** with no values filled in.

---

## 🏗️ Architecture at a Glance

### Visual text blueprint — Telegram → internal request flow

```text
┌──────────────────┐       HTTPS webhook (verified)        ┌────────────────────────┐
│   Telegram User  │ ─────────────────────────────────────►│  Webhook Endpoint      │
│   (@PhantomBot)  │  (TELEGRAM_BOT_TOKEN validation)      │  /api/telegram  │
└──────────────────┘                                       └──────────┬─────────────┘
                                                                       │
                                                                       ▼
                                                              ┌────────────────────┐
                                                              │   Input Validation │
                                                              │  schema + PII scan │
                                                              │  + rate limiting   │
                                                              └──────────┬─────────┘
                                                                         │
                                                                         ▼
                                                      ┌──────────────────────────┐
                                                      │   Session State          │◄────┐
                                                      │  (user_id, history,    │     │
                                                      │   turn counter, TTL)   │     │
                                                      └──────────────┬───────────┘     │
                                                                     │             │
                                                                     ▼             │
                                                    ┌──────────────────────┐     │
                                                    │   Agent Runtime        │─────┘
                                                    │  normalize → role      │
                                                    │  select → plan         │
                                                    └──────────┬─────────────┘
                                                               │
                        ┌─────────────────────────────────────┼────────────────────────────────┐
                        ▼                                     ▼                                ▼
              ┌───────────────┐                       ┌───────────────┐              ┌──────────────┐
              │ Provider      │                       │   Tools /     │              │  Skills      │
              │ Router (FA)   │                       │   Capabilities│              │  Retriever   │
              └───────┬───────┘                       └───────┬───────┘              └──────┬───────┘
                      │                                       │                             │
                      ▼                                       ▼                             ▼
         ┌─────────────────────────────────────────────────────────────────────────────────┐
         │   Direct: Groq · Gemini · Cloudflare · HF · Deepseek   ·   OmniRoute gateway   │
         │   Failover → cooldown → dead-model retest → local LLM fallback (LOCAL_LLM_URL) │
         └─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                      ┌──────────────────────────────┐
                      │  Sanitize → Audit Ledger →   │
                      │  Telegram reply message      │
                      └────────────────────┬─────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │   Telegram User │
                                  │   (bot reply)   │
                                  └─────────────────┘
```

---

## 📊 Technical Highlights Matrix

| Engineering Logic | Business Outcome |
|---|---|
| **Session state** — per-`user_id` history, turn counters, TTL expiry | Continuous, context-aware conversations; users never repeat themselves |
| **Input validation** — JSON schema, PII/secret scanning, rate limits | Malformed and malicious input is rejected before it reaches the model |
| **Exception recovery** — provider failover, cooldowns, dead-model retest | 24/7 availability even when an upstream LLM provider degrades |
| **Role-based capability authorization** — least-privilege tool gating | Actions execute only for authorized roles; sensitive tools require confirmation |
| **Audit ledger + server-side sanitized logs** | Full traceability of every turn without leaking credentials to users |
| **Environment-variable configuration** | Zero secrets in source; deployable to any cloud/runtime safely |

---

## 💬 Simulated User Chat Trace

```bash
$ phantom-agent> /start
✨ Phantom Agent online.
   Roles loaded: 19  |  Routing: failover-ready  |  OWASP A05: hardened

$ phantom-agent> Summarize yesterday's audit ledger and flag high-severity findings.
> [route]     chat → omniroute/gpt-oss-120b → direct/gemini-3.6-flash (failover)
> [session]   state restored for user 1650192264 (turns: 4)
> [validation] input sanitized — PII redacted, size within limits
> [skills]    retrieved 8 skills (audit-ledger, severity-triage, log-parse)
▶ Assistant: Audit summary for 2026-09-25:
   • 1,240 events processed · 3 high-severity flags
   • 14:02 UTC — failed admin authentication (rate limit tripped)
   • 14:17 UTC — provider cooldown: direct/groq (auto-failed over to Gemini)
   • 14:55 UTC — e2b sandbox request denied (missing confirmation)
   All findings written to the audit ledger.

$ phantom-agent> /run-limit --status
▶ Daily token budget: 142,850 / 2,000,000 used (7%)
▶ Providers OK: omniroute, gemini, cloudflare · Direct: groq (cooldown cleared)
▶ All systems nominal.

$ phantom-agent> /help
▶ Commands: /start · /run-limit · /status · /clear-history · /quit
```

---

## 🗺️ Roadmap

- [x] Env-variable configuration with `.env.example` template
- [x] Strict `.gitignore` (`.env`, `config.json`, `node_modules/`, `__pycache__/`)
- [x] OWASP A05:2021 misconfiguration hardening
- [x] Private off-site backup snapshot (`Phantom-agent-private-backup`)
- [ ] Telegram webhook deployment (Railway / fly.io)
- [ ] Dashboard auth with MFA (`identity/mfa.py` groundwork)
- [ ] Observability: token-budget alerts + provider health endpoint

---

<div align="center">

  <!-- ============================================================================
       DESIGNER FOOTER — centered profile buttons
  ============================================================================ -->
  <a href="https://github.com/Charles-234">
    <img
      src="https://img.shields.io/badge/GitHub-@Charles--234-000000?style=for-the-badge&logo=github&logoColor=white"
      alt="Charles-234 GitHub profile"
    />
  </a>
  <a href="https://github.com/Charles-234?tab=repositories">
    <img
      src="https://img.shields.io/badge/Explore-All%20Projects-009688?style=for-the-badge"
      alt="All projects"
    />
  </a>
  <a href="https://github.com/Charles-234/Phantom-agent">
    <img
      src="https://img.shields.io/badge/Star-Phantom%20Agent-009688?style=for-the-badge&logo=github&logoColor=white"
      alt="Star Phantom Agent"
    />
  </a>

  <br />
  <br />

  <sub>Maintained by <b>Charles-234</b> · Built for secure agentic automation · 🛡️ OWASP A05 hardened</sub>

</div>

**Cloud-private snapshot:** A byte-for-byte backup of the original repository (including local `.env` secrets) is prepared at `D:\Phantom-agent-private-backup` as a separate Git repo, ready for your manual push to a private GitHub repository.