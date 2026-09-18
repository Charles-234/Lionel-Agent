"""
Lionel Agent - Command registry.
"""
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from skills import retriever

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    text: str
    is_error: bool = False


def cmd_help(args: List[str]) -> CommandResult:
    lines = [
        "Lionel commands:",
        "",
        "/help                        - this message",
        "/search <query>              - find skills by keyword",
        "/skill <name>                - print a full skill",
        "/skills                      - list skill counts by source",
        "/categories                  - list skill categories",
        "/sources                     - list skill sources",
        "/chat <message>              - AI chat with skill context",
        "/clear                       - clear conversation history",
        "/budget                      - show your token usage today",
        "/status                      - agent status (router, cooldowns)",
    ]
    return CommandResult("\n".join(lines))


def cmd_search(args: List[str]) -> CommandResult:
    if not args:
        return CommandResult("Usage: /search <query>", is_error=True)
    query = " ".join(args)
    matches = retriever.search(query, top_k=10)
    if not matches:
        return CommandResult(f"No skills found for: {query}")
    lines = [f"Top {len(matches)} matches for {query!r}:", ""]
    for i, m in enumerate(matches, 1):
        desc = m.description[:140].replace("\n", " ")
        lines.append(f"{i}. [{m.source}] {m.name}")
        lines.append(f"   {desc}")
        lines.append("")
    lines.append("Use: /skill <name>  to load one")
    return CommandResult("\n".join(lines))


def cmd_skill(args: List[str]) -> CommandResult:
    if not args:
        return CommandResult("Usage: /skill <name>", is_error=True)
    name = " ".join(args)
    content = retriever.get_retriever().load_skill_by_name(name)
    if content is None:
        return CommandResult(f"Skill not found: {name}", is_error=True)
    if len(content) > 8000:
        content = content[:8000] + "\n\n... (truncated)"
    return CommandResult(content)


def cmd_skills(args: List[str]) -> CommandResult:
    sources = retriever.list_sources()
    total = sum(sources.values())
    lines = [f"Total skills: {total}", ""]
    for source, count in sorted(sources.items()):
        lines.append(f"  {source:12s} {count}")
    return CommandResult("\n".join(lines))


def cmd_categories(args: List[str]) -> CommandResult:
    cats = retriever.list_categories()
    lines = [f"Categories ({len(cats)} total):", ""]
    for cat, count in sorted(cats.items(), key=lambda x: -x[1])[:30]:
        lines.append(f"  {count:5d}  {cat}")
    return CommandResult("\n".join(lines))


def cmd_sources(args: List[str]) -> CommandResult:
    from config import SKILL_SOURCES
    lines = ["Skill sources:", ""]
    for name, cfg in SKILL_SOURCES.items():
        lines.append(f"  {name:12s} root={cfg.get('root', '?')}")
    return CommandResult("\n".join(lines))


def cmd_status(args: List[str]) -> CommandResult:
    from providers import router
    lines = ["Lionel status:", ""]
    state = router.router_state()
    if not state:
        lines.append("  Router: all models healthy")
    else:
        lines.append("  Router: models in cooldown:")
        for model, status in state.items():
            lines.append(f"    {model}: {status}")
    return CommandResult("\n".join(lines))


def cmd_chat(args: List[str]) -> CommandResult:
    """Simple CLI chat. Real chat runs through telegram/CLI in the wrapper."""
    if not args:
        return CommandResult("Usage: /chat <message>", is_error=True)
    message = " ".join(args)
    from agent.chat import chat
    # Use 0 as user_id for CLI (non-admin)
    resp = chat(user_id=0, user_message=message, include_skills=True)
    lines = [resp.text, ""]
    lines.append(f"[{resp.provider}/{resp.model} | {resp.tokens_used} tokens | {len(resp.skills_used)} skills]")
    return CommandResult("\n".join(lines), is_error=bool(resp.error))


def cmd_clear(args: List[str]) -> CommandResult:
    from memory import history
    history.clear(0)
    return CommandResult("History cleared.")


def cmd_budget(args: List[str]) -> CommandResult:
    from providers import token_budget
    s = token_budget.stats(0)
    lines = [
        "Token budget today:",
        f"  used:      {s['used']}",
        f"  cap:       {s['cap']}",
        f"  remaining: {s['remaining']}",
    ]
    return CommandResult("\n".join(lines))


COMMANDS: Dict[str, Callable[[List[str]], CommandResult]] = {
    "help": cmd_help,
    "search": cmd_search,
    "skill": cmd_skill,
    "skills": cmd_skills,
    "categories": cmd_categories,
    "sources": cmd_sources,
    "status": cmd_status,
    "chat": cmd_chat,
    "clear": cmd_clear,
    "budget": cmd_budget,
}


def parse_and_dispatch(text: str) -> Optional[CommandResult]:
    if not text or not text.startswith("/"):
        return None
    parts = text[1:].strip().split()
    if not parts:
        return CommandResult("Type /help for commands")
    cmd = parts[0].lower()
    args = parts[1:]
    handler = COMMANDS.get(cmd)
    if handler is None:
        return CommandResult(f"Unknown command: /{cmd}. Type /help.", is_error=True)
    try:
        return handler(args)
    except Exception as e:
        logger.exception(f"Command '/{cmd}' failed")
        return CommandResult(f"Command error: {e}", is_error=True)