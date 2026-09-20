"""
Lionel Agent - Chat mode (Mode 4).

Retrieves relevant skills, sends context + question to the AI router,
returns the response. Tracks token usage per user.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

import config
from providers import router, token_budget
from providers.types import Message, ProviderError
from skills import retriever
from agent import prompts
from memory import history

logger = logging.getLogger(__name__)


# Skill count heuristic
def _skills_for_query(query: str) -> int:
    """
    Decide how many skills to retrieve based on query complexity.
    Short/simple queries: 5. Long/complex: up to 12.
    """
    n = len(query)
    words = len(query.split())
    if n < 40 and words < 8:
        return 5
    if n < 120 and words < 20:
        return 5
    if n < 300:
        return 8
    return 12


@dataclass
class ChatResponse:
    """Result of a chat turn."""
    text: str
    model: str
    provider: str
    tokens_used: int
    skills_used: List[str]
    truncated: bool = False
    error: Optional[str] = None


def chat(
    user_id: int,
    user_message: str,
    include_skills: bool = True,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
) -> ChatResponse:
    """
    Process one chat turn.

    Steps:
    1. Check token budget
    2. Retrieve relevant skills (if include_skills)
    3. Build system prompt
    4. Build message list with history
    5. Call router (switches to 'vision' if image_bytes provided)
    6. Record token usage
    7. Store exchange in history
    """
    user_message = (user_message or "").strip()
    if not user_message and not image_bytes:
        return ChatResponse(
            text="(empty message)", model="", provider="",
            tokens_used=0, skills_used=[], error="empty",
        )
    if not user_message and image_bytes:
        user_message = "Please analyze this image and explain what you see."

    # 1. Budget check
    estimated = 500 + len(user_message) // 4  # rough prompt estimate
    if not token_budget.can_afford(user_id, estimated):
        return ChatResponse(
            text=(
                f"Daily token budget reached ({config.TOKEN_BUDGET_DAILY} tokens). "
                f"Try again after UTC midnight, or ask an admin to raise the cap."
            ),
            model="", provider="", tokens_used=0, skills_used=[],
            error="budget_exceeded",
        )

    # 2. Retrieve skills (skill-assisted chat)
    skills = []
    try:
        r = retriever.get_retriever()
        total_skills = len(r.skills)
    except Exception as e:
        logger.warning(f"Retriever unavailable: {e}")
        total_skills = 0

    if include_skills and total_skills > 0:
        k = _skills_for_query(user_message)
        try:
            skills = retriever.search(user_message, top_k=k)
        except Exception as e:
            logger.warning(f"Skill search failed: {e}")
            skills = []

    # 3. Build system prompt
    if skills:
        system_prompt = prompts.build_chat_with_skills_system(skills, total_skills)
    else:
        system_prompt = prompts.build_chat_system(total_skills)

    # 4. Build message list with history
    messages: List[Message] = [Message(role="system", content=system_prompt)]

    h = history.get(user_id)
    for turn in h.recent():
        if turn.role in ("user", "assistant"):
            messages.append(Message(role=turn.role, content=turn.content))

    messages.append(
        Message(
            role="user",
            content=user_message,
            image_data=image_bytes,
            image_mime_type=image_mime_type,
        )
    )

    # 5. Call router
    task_type = "vision" if image_bytes else "chat"
    try:
        completion = router.call_with_failover(
            task_type=task_type,
            messages=messages,
            max_tokens=config.MAX_OUTPUT_TOKENS_DEFAULT,
            temperature=0.7,
        )
    except ProviderError as e:
        # Keep diagnostic details in server logs only.
        # Never expose provider/internal error details to the user.
        logger.error("Chat router failed (%s): %s", task_type, e.message, exc_info=True)

        return ChatResponse(
            text="I'm temporarily unable to process your request. Please try again shortly.",
            model="",
            provider="",
            tokens_used=0,
            skills_used=[s.name for s in skills],
            error="router_failure",
        )

    # 6. Record usage
    token_budget.record(user_id, completion.total_tokens)

    # 7. Store history
    hist_entry = f"[Image attached] {user_message}" if image_bytes else user_message
    h.add("user", hist_entry)
    h.add("assistant", completion.text)

    return ChatResponse(
        text=completion.text,
        model=completion.model,
        provider=completion.provider,
        tokens_used=completion.total_tokens,
        skills_used=[s.name for s in skills],
    )


def clear_history(user_id: int) -> None:
    history.clear(user_id)