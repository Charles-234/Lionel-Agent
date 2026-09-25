"""
Lionel Agent - Configuration
Single source of truth for env vars, roles, and routing.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    """Read env var, strip whitespace."""
    return (os.environ.get(key) or default).strip()


# Agent Identity
AGENT_NAME = "Lionel"
AGENT_VERSION = "0.1.0"

# Telegram
ADMIN_TELEGRAM_ID = int(_env("ADMIN_TELEGRAM_ID", "0") or "0")
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")

# OmniRoute
OMNIROUTE_URL = _env("OMNIROUTE_URL").rstrip("/")
OMNIROUTE_API_KEY = _env("OMNIROUTE_API_KEY")

# Optional provider keys
GEMINI_API_KEY = _env("GEMINI_API_KEY")
SERPAPI_API_KEY = _env("SERPAPI_API_KEY")
HYBRID_ANALYSIS_API_KEY = _env("HYBRID_ANALYSIS_API_KEY")
NVD_API_KEY = _env("NVD_API_KEY")
E2B_API_KEY = _env("E2B_API_KEY")
OVHCLOUD_API_KEY = _env("OVHCLOUD_API_KEY")
LITELLM_AVAILABLE = True  # Always true after install

# --- IP Intelligence ---
IPINFO_TOKEN = _env("IPINFO_TOKEN")
IPGEOLOCATION_API_KEY = _env("IPGEOLOCATION_API_KEY")
IPINFO_AVAILABLE = bool(IPINFO_TOKEN)
IPGEOLOCATION_AVAILABLE = bool(IPGEOLOCATION_API_KEY)

# Direct provider keys (OmniRoute bypass)
GROQ_API_KEY = _env("GROQ_API_KEY")
CLOUDFLARE_API_TOKEN = _env("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ACCOUNT_ID = _env("CLOUDFLARE_ACCOUNT_ID")
HF_TOKEN = _env("HF_TOKEN")

# Optional local OpenAI-compatible endpoint (Ollama, vLLM, or LM Studio).
LOCAL_LLM_URL = _env("LOCAL_LLM_URL").rstrip("/")
LOCAL_LLM_API_KEY = _env("LOCAL_LLM_API_KEY", "local")
LOCAL_LLM_MODEL = _env("LOCAL_LLM_MODEL", "")

# Budget and logging
TOKEN_BUDGET_DAILY = int(_env("TOKEN_BUDGET_DAILY", "50000") or "50000")
LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()

# The 19 Roles — derived from agent_registry.roles.ROLES to stay in sync.
# The role names list is used in system prompts; the full Role objects carry
# capability_categories, risk_level, and other policy metadata.
from agent_registry.roles import ROLES as _ROLE_REGISTRY
ROLES = [r.name for r in _ROLE_REGISTRY.values()]

# Routing table - free-first, direct providers primary, OmniRoute opportunistic.
# Each entry: {"source": "omniroute" | "direct", "provider": ..., "model": ...}
ROUTING = {
    "chat": [
        {"source": "omniroute", "model": "groq/openai/gpt-oss-120b"},
        {"source": "direct", "provider": "groq", "model": "openai/gpt-oss-120b"},
        {"source": "direct", "provider": "gemini", "model": "gemini-3.6-flash"},
        {"source": "direct", "provider": "cloudflare", "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
        {"source": "direct", "provider": "groq", "model": "openai/gpt-oss-20b"},
        {"source": "direct", "provider": "gemini", "model": "gemini-3.1-flash-lite"},
        {"source": "litellm", "model": "llm7"},
    ],
    "code": [
        {"source": "omniroute", "model": "groq/openai/gpt-oss-120b"},
        {"source": "direct", "provider": "groq", "model": "openai/gpt-oss-120b"},
        {"source": "direct", "provider": "gemini", "model": "gemini-3.6-flash"},
        {"source": "direct", "provider": "cloudflare", "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
        {"source": "litellm", "model": "llm7"},
    ],
    "reasoning": [
        {"source": "omniroute", "model": "groq/openai/gpt-oss-120b"},
        {"source": "direct", "provider": "groq", "model": "openai/gpt-oss-120b"},
        {"source": "direct", "provider": "gemini", "model": "gemini-3.6-flash"},
        {"source": "direct", "provider": "cloudflare", "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
        {"source": "litellm", "model": "llm7"},
    ],
    "vision": [
        {"source": "omniroute", "model": "gemini/gemini-3.6-flash"},
        {"source": "direct", "provider": "gemini", "model": "gemini-3.6-flash"},
    ],
    "classify": [
        {"source": "omniroute", "model": "groq/openai/gpt-oss-20b"},
        {"source": "direct", "provider": "groq", "model": "openai/gpt-oss-20b"},
        {"source": "direct", "provider": "gemini", "model": "gemini-3.1-flash-lite"},
        {"source": "direct", "provider": "cloudflare", "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
        {"source": "litellm", "model": "llm7"},
    ],
    "tool_use": [
        {"source": "omniroute", "model": "groq/openai/gpt-oss-120b"},
        {"source": "direct", "provider": "groq", "model": "openai/gpt-oss-120b"},
        {"source": "direct", "provider": "gemini", "model": "gemini-3.6-flash"},
        {"source": "direct", "provider": "cloudflare", "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
        {"source": "litellm", "model": "llm7"},
    ],
}

if LOCAL_LLM_URL and LOCAL_LLM_MODEL:
    for _task in ("chat", "code", "reasoning", "classify", "tool_use"):
        ROUTING[_task].append({
            "source": "direct",
            "provider": "local",
            "model": LOCAL_LLM_MODEL,
        })

# Dead-model handling
PROVIDER_COOLDOWN_SECONDS = 86400
DEAD_MODEL_RETEST_SECONDS = 3600

# Token discipline
MAX_OUTPUT_TOKENS_DEFAULT = 2000
MAX_OUTPUT_TOKENS_SHORT = 200
MAX_OUTPUT_TOKENS_LONG = 4000
HISTORY_VERBATIM_TURNS = 3
HISTORY_SUMMARY_MAX_CHARS = 600
RESPONSE_CACHE_TTL_SECONDS = 3600

# Skill sources - where to find skills
SKILL_SOURCES = {
    "anthropic": {
        "type": "prebuilt_index",
        "root": "D:\\Anthropic-Cybersecurity-Skills",
        "index_path": "D:\\Anthropic-Cybersecurity-Skills\\index.json",
    },
    "web": {
        "type": "scan",
        "root": "D:\\Web Agent Skills",
        "filename": "SKILL.md",
    },
    "affaan": {
        "type": "scan",
        "root": "C:\\Users\\charl\\OneDrive\\Desktop\\affaan_m_ecc_framework",
        "filename": "SKILL.md",
    },
}

# Output location for the master skill index
SKILLS_INDEX_PATH = "D:\\phantom-agent\\skills\\master_index.json"
# Log settings
LOGS_DIR = "D:\\phantom-agent\\logs"

# Email for logs
LOG_EMAIL_TO = _env("LOG_EMAIL_TO")
LOG_EMAIL_FROM = _env("LOG_EMAIL_FROM")
LOG_EMAIL_PASSWORD = _env("LOG_EMAIL_PASSWORD")
LOG_EMAIL_SMTP_SERVER = _env("LOG_EMAIL_SMTP_SERVER", "smtp.gmail.com")
LOG_EMAIL_SMTP_PORT = int(_env("LOG_EMAIL_SMTP_PORT", "587") or "587")
LOG_EMAIL_ENABLED = _env("LOG_EMAIL_ENABLED", "false").lower() == "true"

# Embeddings (hybrid: Cloudflare -> local -> BM25)
EMBEDDINGS_ENABLED = _env("EMBEDDINGS_ENABLED", "true").lower() == "true"
EMBEDDINGS_PATH = "D:\\phantom-agent\\skills\\embeddings.npz"
CLOUDFLARE_EMBED_MODEL = "@cf/baai/bge-base-en-v1.5"
LOCAL_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_BATCH_SIZE = 50

# Retriever weights
SKILL_NAME_WEIGHT = 3.0
SKILL_DESC_WEIGHT = 1.0

def validate() -> list:
    """Return list of warnings. Empty list means all good."""
    issues = []
    if not OMNIROUTE_URL:
        issues.append("OMNIROUTE_URL is not set")
    if not OMNIROUTE_API_KEY:
        issues.append("OMNIROUTE_API_KEY is not set")
    if OMNIROUTE_API_KEY and not OMNIROUTE_API_KEY.startswith("sk-"):
        issues.append("OMNIROUTE_API_KEY does not start with sk-")
    if ADMIN_TELEGRAM_ID == 0:
        issues.append("ADMIN_TELEGRAM_ID is 0 (not set)")
    return issues


if __name__ == "__main__":
    print(f"Agent: {AGENT_NAME} v{AGENT_VERSION}")
    print(f"Roles: {len(ROLES)}")
    print(f"Task types: {len(ROUTING)}")
    print(f"Skill sources: {len(SKILL_SOURCES)}")
    print(f"Daily budget: {TOKEN_BUDGET_DAILY} tokens")
    problems = validate()
    if problems:
        print("\nWARNINGS:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("\nAll required config present.")