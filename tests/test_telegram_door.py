"""Focused tests for the Telegram outside door (Phase 6 start).

The door holds no intelligence: it only links the owner's number,
refuses strangers with one safe line, and carries text both ways.
"""

import sys
import unittest

import config
from interfaces.telegram_door import (
    EMPTY_MESSAGE,
    OWNER_NOT_SET_MESSAGE,
    POLLING_LIBRARY_MISSING_MESSAGE,
    STRANGER_REFUSED_MESSAGE,
    IncomingMessage,
    TelegramDoor,
    is_owner,
    owner_id,
    screen_message,
)


class TelegramDoorTests(unittest.TestCase):
    def setUp(self):
        self._saved = config.ADMIN_TELEGRAM_ID
        config.ADMIN_TELEGRAM_ID = 12345

    def tearDown(self):
        config.ADMIN_TELEGRAM_ID = self._saved

    def test_owner_number_is_linked(self):
        self.assertEqual(owner_id(), 12345)
        self.assertTrue(is_owner(12345))
        self.assertFalse(is_owner(999))

    def test_stranger_is_refused_before_core(self):
        calls = []
        door = TelegramDoor(core_handler=lambda text: calls.append(text) or "hi")
        reply = door.handle(IncomingMessage(user_id=999, text="hello"))
        self.assertEqual(reply.text, STRANGER_REFUSED_MESSAGE)
        self.assertEqual(calls, [])
        self.assertIn(999, door.refused_strangers)

    def test_owner_message_reaches_core_and_back(self):
        door = TelegramDoor(core_handler=lambda text: f"got: {text}")
        reply = door.handle(IncomingMessage(user_id=12345, text="hello"))
        self.assertEqual(reply.text, "got: hello")

    def test_empty_owner_text_is_refused_safely(self):
        decision = screen_message(IncomingMessage(user_id=12345, text="   "))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, EMPTY_MESSAGE)

    def test_owner_missing_gives_setup_line(self):
        config.ADMIN_TELEGRAM_ID = 0
        decision = screen_message(IncomingMessage(user_id=12345, text="hi"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, OWNER_NOT_SET_MESSAGE)
        self.assertIn("ADMIN_TELEGRAM_ID", decision.reason)

    def test_owner_missing_stops_polling_without_touching_network(self):
        config.ADMIN_TELEGRAM_ID = 0
        door = TelegramDoor()
        self.assertEqual(door.start_polling(), OWNER_NOT_SET_MESSAGE)

    def test_start_greets_the_owner(self):
        door = TelegramDoor()
        reply = door.handle(IncomingMessage(user_id=12345, text="/start"))
        self.assertIn("/help", reply.text)

    def test_keyboard_shortcut_dispatches_builtin_command(self):
        door = TelegramDoor()
        self.assertIn("/help", door.handle(IncomingMessage(user_id=12345, text="/help")).text)

    def test_command_refuses_stranger_before_core(self):
        door = TelegramDoor()
        reply = door.handle(IncomingMessage(user_id=999, text="/search test"))
        self.assertEqual(reply.text, STRANGER_REFUSED_MESSAGE)
        self.assertFalse(reply.text.startswith("Result:"))
        self.assertIn(999, door.refused_strangers)

    def test_unknown_command_gives_a_plain_line(self):
        door = TelegramDoor()
        reply = door.handle(IncomingMessage(user_id=12345, text="/frobnicate"))
        self.assertTrue(reply.text.strip())
        self.assertIn("Unknown command", reply.text)

    def test_secrets_never_leave_through_replies(self):
        door = TelegramDoor(core_handler=lambda text: "token=abc123 sk-abcdef123456")
        reply = door.handle(IncomingMessage(user_id=12345, text="hi"))
        self.assertNotIn("abc123", reply.text)
        self.assertNotIn("sk-abcdef", reply.text)

    def test_core_failure_gives_safe_line(self):
        def _boom(text):
            raise RuntimeError("provider blew up: sk-secret")

        door = TelegramDoor(core_handler=_boom)
        reply = door.handle(IncomingMessage(user_id=12345, text="hi"))
        self.assertEqual(reply.text, "I could not handle that. Try again.")
        self.assertNotIn("sk-secret", reply.text)

    def test_rate_limit_refuses_bursts_before_core(self):
        calls = []
        door = TelegramDoor(core_handler=lambda text: calls.append(text) or "ok")

        for i in range(20):
            reply = door.handle(IncomingMessage(user_id=12345, text=f"msg {i}"))
            if i < 19:
                self.assertEqual(reply.text, f"ok")

        blocked = door.handle(IncomingMessage(user_id=12345, text="too many"))
        self.assertEqual(blocked.text, "Too many messages. Please wait a moment and try again.")
        self.assertEqual(len(calls), 20)

    def test_polling_missing_library_says_so_plainly(self):
        saved = sys.modules.get("telegram")
        sys.modules["telegram"] = None
        try:
            door = TelegramDoor()
            self.assertEqual(door.start_polling(), POLLING_LIBRARY_MISSING_MESSAGE)
        finally:
            if saved is None:
                sys.modules.pop("telegram", None)
            else:
                sys.modules["telegram"] = saved

    def test_door_replies_never_leak_the_bot_token(self):
        token = config.TELEGRAM_BOT_TOKEN
        if not token:
            self.skipTest("No bot token configured in this environment.")
        door = TelegramDoor()
        for text in ("/help", "/start", "/status"):
            reply = door.handle(IncomingMessage(user_id=12345, text=text))
            self.assertNotIn(token, reply.text)

    def test_long_replies_keep_content_and_formatting(self):
        from agent.safety import sanitize_for_display

        long_text = "# Section\n\n" + "Line one\n\n" + ("detail " * 600) + "\n\n```bash\necho hello\n```"
        cleaned = sanitize_for_display(long_text)

        self.assertIn("# Section", cleaned)
        self.assertIn("```bash", cleaned)
        self.assertIn("echo hello", cleaned)
        self.assertIn("Line one", cleaned)
        self.assertTrue(len(cleaned) > 1000)
        self.assertNotIn("\n\n\n", cleaned)


class AllowlistDoorTests(unittest.TestCase):
    """Phase 9 groundwork: optional collaborator allowlist at the door.

    Default stays owner-only. With an allowlist attached, invited
    collaborators get the free-text chat path; slash commands remain
    owner-only until collaborator command access goes through the
    governed path.
    """

    def setUp(self):
        self._saved = config.ADMIN_TELEGRAM_ID
        config.ADMIN_TELEGRAM_ID = 12345

    def tearDown(self):
        config.ADMIN_TELEGRAM_ID = self._saved

    def _registry(self):
        from identity.registry import IdentityRegistry

        registry = IdentityRegistry()
        registry.seed_owner(12345)
        registry.invite(777, invited_by=12345, display_name="ally")
        return registry

    def test_without_allowlist_the_door_stays_owner_only(self):
        calls = []
        door = TelegramDoor(core_handler=lambda text: calls.append(text) or "hi")
        reply = door.handle(IncomingMessage(user_id=777, text="hello"))
        self.assertEqual(reply.text, STRANGER_REFUSED_MESSAGE)
        self.assertEqual(calls, [])

    def test_invited_collaborator_reaches_core(self):
        calls = []
        door = TelegramDoor(
            core_handler=lambda text: calls.append(text) or "hi",
            allowed_users=self._registry(),
        )
        reply = door.handle(IncomingMessage(user_id=777, text="hello"))
        self.assertEqual(reply.text, "hi")
        self.assertEqual(calls, ["hello"])
        self.assertNotIn(777, door.refused_strangers)

    def test_revoked_collaborator_is_refused_again(self):
        from identity.registry import IdentityRegistry

        registry = IdentityRegistry()
        registry.seed_owner(12345)
        registry.invite(777, invited_by=12345)
        registry.revoke(777, by=12345)
        door = TelegramDoor(
            core_handler=lambda text: "hi", allowed_users=registry
        )
        reply = door.handle(IncomingMessage(user_id=777, text="hello"))
        self.assertEqual(reply.text, STRANGER_REFUSED_MESSAGE)
        self.assertIn(777, door.refused_strangers)

    def test_unknown_user_is_refused_even_with_allowlist(self):
        door = TelegramDoor(
            core_handler=lambda text: "hi", allowed_users=self._registry()
        )
        reply = door.handle(IncomingMessage(user_id=888, text="hello"))
        self.assertEqual(reply.text, STRANGER_REFUSED_MESSAGE)

    def test_collaborator_empty_text_gets_the_empty_line(self):
        door = TelegramDoor(
            core_handler=lambda text: "hi", allowed_users=self._registry()
        )
        reply = door.handle(IncomingMessage(user_id=777, text="   "))
        self.assertEqual(reply.text, EMPTY_MESSAGE)

    def test_owner_missing_line_wins_over_allowlist(self):
        config.ADMIN_TELEGRAM_ID = 0
        door = TelegramDoor(
            core_handler=lambda text: "hi", allowed_users=self._registry()
        )
        reply = door.handle(IncomingMessage(user_id=777, text="hello"))
        self.assertEqual(reply.text, OWNER_NOT_SET_MESSAGE)

    def test_collaborator_commands_stay_owner_only(self):
        door = TelegramDoor(
            core_handler=lambda text: "hi", allowed_users=self._registry()
        )
        reply = door.handle(IncomingMessage(user_id=777, text="/help"))
        self.assertEqual(reply.text, STRANGER_REFUSED_MESSAGE)


if __name__ == "__main__":
    unittest.main()
