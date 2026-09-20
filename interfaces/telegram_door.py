"""Telegram door for Lionel: carries messages, holds no intelligence.

This adapter is a thin outside door only. It never plans, never picks a
role, never authorizes, never runs tools, and never audits. It only:

1. Checks the sender's Telegram user id against the admin id.
2. Refuses strangers with one safe line and remembers nothing.
3. Passes the admin's words into the core and carries the reply back.
4. Refuses to contact the core until the owner id exists.

The owner link is exactly one number: ADMIN_TELEGRAM_ID in the .env file.
Only that number is treated as the owner. All other numbers are strangers.

Optionally, a pure identity allowlist (identity.registry.IdentityRegistry)
may be attached as ``allowed_users``. Admitted collaborators then get the
same free-text chat path as the owner. Slash commands stay owner-only in
this groundwork phase; collaborator command access must go through the
governed path later. Without an allowlist the door is owner-only, exactly
as before.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, List, Optional

import config

if TYPE_CHECKING:
    from identity.registry import Admission, IdentityRegistry

logger = logging.getLogger(__name__)


OWNER_NOT_SET_MESSAGE = "Owner number is not set. Set ADMIN_TELEGRAM_ID in .env."
STRANGER_REFUSED_MESSAGE = "Sorry, I only answer my owner."
EMPTY_MESSAGE = "Send a message or /help."
POLLING_LIBRARY_MISSING_MESSAGE = (
    "Telegram polling needs the python-telegram-bot package, "
    "which is not installed."
)
POLLING_STARTED_MESSAGE = "Lionel door is live and listening for the owner."
POLLING_START_FAILED_MESSAGE = (
    "Telegram door could not start. Check the server logs."
)
POLLING_FAILED_MESSAGE = "Telegram door polling failed. Check the server logs."
COMMANDS_UNAVAILABLE_MESSAGE = (
    "Door commands are unavailable right now. Try /help again shortly."
)
DOOR_HELP_FALLBACK_MESSAGE = (
    "Lionel door is live. Send a message, or try /help."
)


@dataclass(frozen=True)
class IncomingMessage:
    """One message carried in from the outside door."""

    user_id: int
    text: str
    image_bytes: Optional[bytes] = None
    image_mime_type: str = "image/jpeg"


@dataclass(frozen=True)
class OutgoingReply:
    """One safe line to carry back outside. Never holds secrets."""

    text: str


@dataclass(frozen=True)
class DoorDecision:
    """What the door decided before the core was ever touched."""

    allowed: bool
    reason: str


def owner_id() -> int:
    """Return the owner's Telegram number, or 0 when it is not set."""
    try:
        return int(config.ADMIN_TELEGRAM_ID or 0)
    except (TypeError, ValueError):
        return 0


def is_owner(user_id: Any) -> bool:
    """Report whether one sender number is the owner. Shape check only."""
    configured = owner_id()
    if not configured:
        return False
    return user_id == configured


def screen_message(message: Any) -> DoorDecision:
    """Decide at the door whether a message may enter. No core contact yet."""
    if owner_id() == 0:
        return DoorDecision(allowed=False, reason=OWNER_NOT_SET_MESSAGE)
    user_id = getattr(message, "user_id", None)
    if user_id != owner_id():
        return DoorDecision(allowed=False, reason=STRANGER_REFUSED_MESSAGE)
    text = getattr(message, "text", "")
    has_image = bool(getattr(message, "image_bytes", None))
    if not isinstance(text, str) or (not text.strip() and not has_image):
        return DoorDecision(allowed=False, reason=EMPTY_MESSAGE)
    return DoorDecision(allowed=True, reason="Owner message may enter.")


def allowlist_admission(door: "TelegramDoor", user_id: Any) -> Optional["Admission"]:
    """Consult the optional identity allowlist for a non-owner sender.

    Returns None when no allowlist is attached, so the owner-only path
    stays untouched. Never raises upward; lookup failure refuses.
    """
    allowed_users = getattr(door, "allowed_users", None)
    if allowed_users is None:
        return None
    try:
        return allowed_users.is_admitted(user_id)
    except Exception:
        logger.warning("Identity allowlist lookup failed.", exc_info=True)
        return None


def _command_dispatcher():
    """Return the shared command dispatcher, or None when it is unavailable.

    Commands stay thin: they are door-level helpers and never replace
    governance, tool authorization, or the core handler.
    """
    try:
        from commands.registry import parse_and_dispatch
    except Exception:
        logger.warning("Door command dispatcher is unavailable.", exc_info=True)
        return None
    return parse_and_dispatch


def _dispatch_message(door: TelegramDoor, message: IncomingMessage) -> OutgoingReply:
    """Carry one message in and one safe reply out, including built-in commands."""

    from agent.safety import sanitize_for_display

    text = getattr(message, "text", "")
    stripped = text.strip() if isinstance(text, str) else ""
    if stripped.startswith("/") and not getattr(message, "image_bytes", None):
        return _run_builtin_command(door, message.user_id, stripped)

    decision = screen_message(message)
    if not decision.allowed:
        if decision.reason != STRANGER_REFUSED_MESSAGE:
            # Owner not set, or empty text: the owner gets the same line.
            return OutgoingReply(text=decision.reason)
        admitted = allowlist_admission(door, message.user_id)
        if admitted is None or not admitted.allowed:
            door.note_stranger(message.user_id)
            return OutgoingReply(text=STRANGER_REFUSED_MESSAGE)
        if not stripped and not getattr(message, "image_bytes", None):
            return OutgoingReply(text=EMPTY_MESSAGE)
    if door.core_handler is None:
        return OutgoingReply(text="Core is not connected yet.")
    img_bytes = getattr(message, "image_bytes", None)
    img_mime = getattr(message, "image_mime_type", "image/jpeg")
    try:
        if img_bytes is not None:
            try:
                reply = door.core_handler(message.text, img_bytes, img_mime)
            except TypeError:
                reply = door.core_handler(message.text)
        else:
            reply = door.core_handler(message.text)
    except Exception:
        return OutgoingReply(text="I could not handle that. Try again.")
    return OutgoingReply(text=sanitize_for_display(reply))


def _run_builtin_command(door: TelegramDoor, user_id: Any, text: str) -> OutgoingReply:
    """Handle simple door commands without touching governance or the core."""

    from agent.safety import sanitize_for_display

    if user_id != owner_id():
        door.note_stranger(user_id)
        return OutgoingReply(text=STRANGER_REFUSED_MESSAGE)

    if not isinstance(text, str) or not text.strip():
        return OutgoingReply(text=EMPTY_MESSAGE)

    command = text.split(maxsplit=1)[0].lower()
    if command == "/start":
        # /start is a greeting, not a command with work behind it.
        text = "/help"
        command = "/help"

    dispatch = _command_dispatcher()
    if dispatch is None:
        if command == "/help":
            return OutgoingReply(text=DOOR_HELP_FALLBACK_MESSAGE)
        return OutgoingReply(text=COMMANDS_UNAVAILABLE_MESSAGE)

    try:
        result = dispatch(text)
    except Exception:
        logger.warning("Door command failed.", exc_info=True)
        return OutgoingReply(text="I could not handle that command. Try again.")

    if result is None:
        return OutgoingReply(text=EMPTY_MESSAGE)

    return OutgoingReply(text=sanitize_for_display(result.text))


@dataclass
class TelegramDoor:
    """The outside door. Needs a core handler plugged in to do real work.

    ``core_handler`` receives the message text and returns one reply string.
    The door never inspects that text for meaning; it only carries it.

    ``allowed_users`` is an optional pure identity allowlist
    (identity.registry.IdentityRegistry). When attached, invited
    collaborators are admitted beside the owner. When omitted, the door
    stays exactly as before: owner only.
    """

    core_handler: Optional[Callable[[str], str]] = None
    refused_strangers: List[int] = field(default_factory=list)
    allowed_users: Optional["IdentityRegistry"] = None

    def handle(self, message: IncomingMessage) -> OutgoingReply:
        """Carry one message in and one safe reply out."""
        return _dispatch_message(self, message)

    def note_stranger(self, user_id: Any) -> None:
        """Remember one stranger number for the owner to review. Bounded."""
        if not isinstance(user_id, int):
            return
        if user_id in self.refused_strangers:
            return
        self.refused_strangers.append(user_id)
        del self.refused_strangers[:-50]

    def start_polling(self) -> str:
        """Start Telegram polling if the library is installed and the owner is set.

        This is the live outside listener. It still does not think, authorize,
        run tools, or audit. It only carries owned messages in and replies out.
        """
        if owner_id() == 0:
            logger.warning("Telegram door will not start: owner id is not set.")
            return OWNER_NOT_SET_MESSAGE

        try:
            from telegram import Update
            from telegram.ext import ApplicationBuilder, MessageHandler, filters, CommandHandler
        except ImportError:
            logger.warning("Telegram polling requested but python-telegram-bot is not installed.")
            return POLLING_LIBRARY_MISSING_MESSAGE

        bot_token = config.TELEGRAM_BOT_TOKEN
        if not bot_token:
            logger.warning("Telegram door will not start: TELEGRAM_BOT_TOKEN is empty.")
            return OWNER_NOT_SET_MESSAGE

        door = self

        async def _handler(update: Update, context: Any) -> None:
            message = update.effective_message
            if message is None:
                return
            user_id = getattr(message.from_user, "id", None)
            text = (getattr(message, "text", "") or getattr(message, "caption", "") or "").strip()

            image_bytes = None
            image_mime_type = "image/jpeg"
            if getattr(message, "photo", None):
                try:
                    photo = message.photo[-1]
                    file = await photo.get_file()
                    image_bytes = bytes(await file.download_as_bytearray())
                    if not text:
                        text = "Please analyze this image and explain what you see."
                except Exception:
                    logger.warning("Failed to download Telegram photo from user %s", user_id, exc_info=True)

            incoming = IncomingMessage(
                user_id=user_id if isinstance(user_id, int) else 0,
                text=text,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
            )
            reply = door.handle(incoming)
            outgoing = reply.text
            if not outgoing:
                return
            try:
                await update.effective_message.reply_text(outgoing)
            except Exception:
                logger.warning("Failed to send Telegram reply to user %s", user_id)

        try:
            application = ApplicationBuilder().token(bot_token).build()
            # Text and photo handlers carry both plain words, images, and /commands
            application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, _handler))
            application.add_handler(CommandHandler("start", _handler))
        except Exception:
            logger.exception("Telegram door failed while building the application.")
            return POLLING_START_FAILED_MESSAGE

        try:
            application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception:
            logger.exception("Telegram polling failed.")
            return POLLING_FAILED_MESSAGE

        return POLLING_STARTED_MESSAGE


def run_chat_through_door(
    door: TelegramDoor,
    user_id: int,
    text: str,
    *,
    include_skills: bool = True,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
) -> OutgoingReply:
    """
    Run one chat turn through Lionel's chat mode, then return a safe reply.

    This is the "pluggable chat plug" for outside doors. The door is silent
    about what the chat layer does next. It only carries one message in and
    one safe reply out.
    """
    from agent.safety import sanitize_for_display
    from agent.chat import chat

    reply = chat(
        user_id=user_id,
        user_message=text,
        include_skills=include_skills,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
    )
    return OutgoingReply(text=sanitize_for_display(reply.text))


def set_door_to_chat_mode(
    door: TelegramDoor,
    *,
    skill_mode: bool = True,
) -> None:
    """
    Plug the chat brain into the door so it can answer owned messages.
    """
    door.core_handler = lambda text, img=None, mime="image/jpeg": run_chat_through_door(
        door,
        user_id=owner_id(),
        text=text,
        include_skills=skill_mode,
        image_bytes=img,
        image_mime_type=mime,
    ).text


class TelegramDoorFactory:
    """
    Helper to create a properly configured door ready for Telegram.
    """

    @staticmethod
    def create_chat_door(*, skill_mode: bool = True) -> TelegramDoor:
        """
        Create a Telegram door with the chat handler already plugged in.
        """
        door = TelegramDoor()
        set_door_to_chat_mode(door, skill_mode=skill_mode)
        return door

    @staticmethod
    def create_door_with_custom_handler(
        handler: Callable[[str], str],
    ) -> TelegramDoor:
        """
        Create a Telegram door with a custom core handler.
        """
        door = TelegramDoor()
        door.core_handler = handler
        return door



def main() -> int:
    """Start the live Telegram door for the owner.

    This is the only entry point that turns the listener on. It still holds no
    intelligence: it plugs the chat path in and lets the door carry messages.
    """
    door = TelegramDoorFactory.create_chat_door(skill_mode=True)
    outcome = door.start_polling()
    if outcome != POLLING_STARTED_MESSAGE:
        logger.warning("Telegram door did not go live.")
        print(outcome)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

