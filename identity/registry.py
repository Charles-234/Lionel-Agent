"""Pure identity allowlist for Lionel's owner and invited collaborators.

This module answers exactly one question: is this sender admitted, and as
what? It never authorizes tools, roles, or capabilities, never touches
policy or audit, and never reads configuration. Tool authorization stays
in agent_registry.authorization. Policy stays in tools.policy. This file
is deliberately pure: no I/O, no persistence, no side effects.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

ROLE_OWNER = "owner"
ROLE_COLLABORATOR = "collaborator"
ROLE_NONE = "none"

STATUS_ACTIVE = "active"
STATUS_REVOKED = "revoked"


@dataclass(frozen=True)
class Person:
    """One admitted human: a Telegram number plus a lifecycle state."""

    telegram_id: int
    role: str
    status: str
    display_name: str
    invited_by: int


@dataclass(frozen=True)
class Admission:
    """One explicit admission answer. Never guessed."""

    allowed: bool
    role: str
    reason: str


def _checked_id(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")
    if value <= 0:
        raise ValueError(f"{label} must be a positive integer.")
    return value


class IdentityRegistry:
    """In-memory allowlist: one owner, owner-only invites, explicit revocation.

    Rules are deliberate and small:

    1. Exactly one owner may be seeded, once.
    2. Only an active owner may invite, revoke, or restore.
    3. Revoked people stay listed with a revoked status so history is visible.
    4. Admission is refused, never guessed, for anything unknown or revoked.
    """

    def __init__(self) -> None:
        self._people: Dict[int, Person] = {}
        self._owner_id: Optional[int] = None

    @property
    def owner_id(self) -> Optional[int]:
        """Return the seeded owner's number, or None before seeding."""
        return self._owner_id

    def seed_owner(self, telegram_id: object, display_name: str = "") -> Person:
        """Register the one owner. Raises if an owner already exists."""
        checked = _checked_id(telegram_id, "Owner id")
        if self._owner_id is not None:
            raise ValueError("The owner is already seeded.")
        person = Person(
            telegram_id=checked,
            role=ROLE_OWNER,
            status=STATUS_ACTIVE,
            display_name=display_name,
            invited_by=0,
        )
        self._people[checked] = person
        self._owner_id = checked
        return person

    def invite(
        self,
        telegram_id: object,
        *,
        invited_by: object,
        display_name: str = "",
    ) -> Person:
        """Add one collaborator. Only the seeded, active owner may invite."""
        checked = _checked_id(telegram_id, "Invitee id")
        actor = _checked_id(invited_by, "Inviter id")
        if self._owner_id is None:
            raise ValueError("Seed the owner before inviting anyone.")
        if actor != self._owner_id:
            raise ValueError("Only the owner may invite collaborators.")
        if checked == self._owner_id:
            raise ValueError("The owner is already registered.")
        if checked in self._people:
            raise ValueError("This person is already registered.")
        person = Person(
            telegram_id=checked,
            role=ROLE_COLLABORATOR,
            status=STATUS_ACTIVE,
            display_name=display_name,
            invited_by=actor,
        )
        self._people[checked] = person
        return person

    def revoke(self, telegram_id: object, *, by: object) -> bool:
        """Revoke one collaborator. Returns True only when status changed.

        Raises if the actor is not the active owner or targets the owner.
        Returns False when the target is unknown or already revoked.
        """
        checked = _checked_id(telegram_id, "Target id")
        actor = _checked_id(by, "Actor id")
        if self._owner_id is None or actor != self._owner_id:
            raise ValueError("Only the owner may revoke access.")
        if checked == self._owner_id:
            raise ValueError("The owner cannot revoke their own access.")
        person = self._people.get(checked)
        if person is None or person.status == STATUS_REVOKED:
            return False
        self._people[checked] = Person(
            telegram_id=person.telegram_id,
            role=person.role,
            status=STATUS_REVOKED,
            display_name=person.display_name,
            invited_by=person.invited_by,
        )
        return True

    def restore(self, telegram_id: object, *, by: object) -> bool:
        """Restore one revoked collaborator. Returns True only when changed."""
        checked = _checked_id(telegram_id, "Target id")
        actor = _checked_id(by, "Actor id")
        if self._owner_id is None or actor != self._owner_id:
            raise ValueError("Only the owner may restore access.")
        if checked == self._owner_id:
            raise ValueError("The owner's access is never revoked.")
        person = self._people.get(checked)
        if person is None or person.status == STATUS_ACTIVE:
            return False
        self._people[checked] = Person(
            telegram_id=person.telegram_id,
            role=person.role,
            status=STATUS_ACTIVE,
            display_name=person.display_name,
            invited_by=person.invited_by,
        )
        return True

    def lookup(self, telegram_id: object) -> Optional[Person]:
        """Return one person record, or None when unknown."""
        if isinstance(telegram_id, bool) or not isinstance(telegram_id, int):
            return None
        return self._people.get(telegram_id)

    def is_admitted(self, telegram_id: object) -> Admission:
        """Answer one admission question. Refuses unknown shapes quietly."""
        person = self.lookup(telegram_id)
        if person is None:
            return Admission(False, ROLE_NONE, "Not on the identity allowlist.")
        if person.status == STATUS_REVOKED:
            return Admission(False, person.role, "Access was revoked.")
        return Admission(True, person.role, "Admitted by the identity allowlist.")

    def admitted_ids(self) -> Tuple[int, ...]:
        """Return currently admitted numbers in deterministic ascending order."""
        return tuple(
            sorted(
                p.telegram_id
                for p in self._people.values()
                if p.status == STATUS_ACTIVE
            )
        )
