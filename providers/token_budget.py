"""
Lionel Agent - Per-user daily token budget.

Tracks tokens consumed per user per day. Admins bypass.
Resets at UTC midnight. In-memory only for now.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

import config

logger = logging.getLogger(__name__)


@dataclass
class UserBudget:
    """Budget state for one user."""
    used: int = 0
    day: str = ""          # "YYYY-MM-DD" in UTC
    warnings_issued: set = field(default_factory=set)

    def check_day(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.day != today:
            self.used = 0
            self.day = today
            self.warnings_issued.clear()


class TokenBudget:
    """Tracks and enforces daily token caps per user."""

    def __init__(self):
        self._by_user: Dict[int, UserBudget] = {}

    def _get(self, user_id: int) -> UserBudget:
        if user_id not in self._by_user:
            self._by_user[user_id] = UserBudget()
        b = self._by_user[user_id]
        b.check_day()
        return b

    def is_admin(self, user_id: int) -> bool:
        return config.ADMIN_TELEGRAM_ID != 0 and user_id == config.ADMIN_TELEGRAM_ID

    def can_afford(self, user_id: int, estimated_tokens: int) -> bool:
        """Check if user has budget for an estimated request."""
        if self.is_admin(user_id):
            return True
        b = self._get(user_id)
        return (b.used + estimated_tokens) <= config.TOKEN_BUDGET_DAILY

    def record(self, user_id: int, tokens: int) -> None:
        """Record token usage after a call completes."""
        if self.is_admin(user_id):
            return
        b = self._get(user_id)
        b.used += tokens

        pct = (b.used / config.TOKEN_BUDGET_DAILY) * 100
        for threshold in (50, 80, 100):
            if pct >= threshold and threshold not in b.warnings_issued:
                b.warnings_issued.add(threshold)
                logger.warning(
                    f"User {user_id} at {threshold}% daily budget "
                    f"({b.used}/{config.TOKEN_BUDGET_DAILY})"
                )

    def remaining(self, user_id: int) -> int:
        """Tokens remaining today for this user."""
        if self.is_admin(user_id):
            return 10**9
        b = self._get(user_id)
        return max(0, config.TOKEN_BUDGET_DAILY - b.used)

    def stats(self, user_id: int) -> Dict[str, int]:
        b = self._get(user_id)
        return {
            "used": b.used,
            "cap": config.TOKEN_BUDGET_DAILY,
            "remaining": self.remaining(user_id),
        }


# Singleton
_budget = TokenBudget()


def can_afford(user_id: int, estimated_tokens: int) -> bool:
    return _budget.can_afford(user_id, estimated_tokens)


def record(user_id: int, tokens: int) -> None:
    _budget.record(user_id, tokens)


def remaining(user_id: int) -> int:
    return _budget.remaining(user_id)


def stats(user_id: int) -> Dict[str, int]:
    return _budget.stats(user_id)


def is_admin(user_id: int) -> bool:
    return _budget.is_admin(user_id)