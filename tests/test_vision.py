"""
Tests for Lionel Vision and Multimodal support.

Verifies:
- Multimodal Message creation (text + image bytes).
- Gemini direct provider payload packaging (inlineData base64).
- OmniRoute payload packaging (image_url data URI).
- Chat router switching to task_type='vision' when image is present.
- TelegramDoor screening and dispatching messages with photos.
"""
import base64
import unittest
from unittest.mock import MagicMock, patch

from agent.chat import chat
from interfaces.telegram_door import (
    EMPTY_MESSAGE,
    IncomingMessage,
    TelegramDoor,
    screen_message,
)
from providers.direct import call_gemini
from providers.omniroute import call as call_omniroute
from providers.types import Completion, Message


class MultimodalTypesTests(unittest.TestCase):
    def test_message_with_image_data(self):
        fake_bytes = b"\x89PNG\r\n\x1a\nfake_image_data"
        msg = Message(
            role="user",
            content="Describe this diagram",
            image_data=fake_bytes,
            image_mime_type="image/png",
        )
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "Describe this diagram")
        self.assertEqual(msg.image_data, fake_bytes)
        self.assertEqual(msg.image_mime_type, "image/png")


class GeminiVisionDirectTests(unittest.TestCase):
    @patch("providers.direct.config")
    @patch("providers.direct._post_with_retries")
    def test_call_gemini_packages_inlinedata(self, mock_post, mock_config):
        mock_config.GEMINI_API_KEY = "test-key"
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "This is a network topology diagram."}]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 20,
                "totalTokenCount": 120,
            },
        }
        mock_post.return_value = fake_resp

        fake_bytes = b"fake_jpeg_bytes"
        b64_expected = base64.b64encode(fake_bytes).decode("utf-8")

        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(
                role="user",
                content="What is in this picture?",
                image_data=fake_bytes,
                image_mime_type="image/jpeg",
            ),
        ]

        completion = call_gemini("gemini-3.6-flash", messages)
        self.assertEqual(completion.text, "This is a network topology diagram.")
        self.assertEqual(completion.provider, "gemini-direct")

        # Verify payload passed to _post_with_retries
        call_args = mock_post.call_args
        payload = call_args[0][2]
        contents = payload["contents"]
        self.assertEqual(len(contents), 1)
        user_parts = contents[0]["parts"]
        self.assertEqual(len(user_parts), 2)
        self.assertEqual(user_parts[0], {"text": "What is in this picture?"})
        self.assertEqual(
            user_parts[1],
            {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": b64_expected,
                }
            },
        )


class OmniRouteVisionTests(unittest.TestCase):
    @patch("providers.omniroute.config")
    @patch("providers.omniroute.requests.post")
    def test_call_omniroute_packages_image_url(self, mock_post, mock_config):
        mock_config.OMNIROUTE_URL = "https://omniroute.example.com"
        mock_config.OMNIROUTE_API_KEY = "sk-test"

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "choices": [
                {"message": {"content": "Identified a screenshot of terminal output."}}
            ],
            "usage": {"total_tokens": 150},
        }
        mock_post.return_value = fake_resp

        fake_bytes = b"sample_png"
        b64_expected = base64.b64encode(fake_bytes).decode("utf-8")

        messages = [
            Message(
                role="user",
                content="Analyze this screenshot",
                image_data=fake_bytes,
                image_mime_type="image/png",
            )
        ]

        completion = call_omniroute("gemini/gemini-3.6-flash", messages)
        self.assertEqual(completion.text, "Identified a screenshot of terminal output.")

        # Verify request json payload
        call_kwargs = mock_post.call_args[1]
        json_payload = call_kwargs["json"]
        sent_messages = json_payload["messages"]
        self.assertEqual(len(sent_messages), 1)
        content_items = sent_messages[0]["content"]
        self.assertEqual(content_items[0], {"type": "text", "text": "Analyze this screenshot"})
        self.assertEqual(
            content_items[1],
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64_expected}"},
            },
        )


class ChatVisionRoutingTests(unittest.TestCase):
    @patch("agent.chat.extract_attachment")
    @patch("agent.chat.token_budget")
    @patch("agent.chat.router.call_with_failover")
    def test_chat_includes_extracted_document_context(self, mock_router, mock_budget, mock_extract):
        mock_budget.can_afford.return_value = True
        mock_extract.return_value.context = "ATTACHMENT: report.pdf\nEXTRACTED CONTENT:\nImportant document text"
        mock_router.return_value = Completion(
            text="The document contains important text.",
            model="gpt-oss-120b",
            provider="groq",
            total_tokens=30,
        )

        resp = chat(
            user_id=123,
            user_message="Summarize this document",
            attachment_bytes=b"%PDF-1.7",
            attachment_mime_type="application/pdf",
            attachment_name="report.pdf",
        )

        self.assertEqual(resp.text, "The document contains important text.")
        self.assertIn("Important document text", mock_router.call_args[1]["messages"][-1].content)

    @patch("agent.chat.token_budget")
    @patch("agent.chat.router.call_with_failover")
    def test_chat_switches_to_vision_task_when_image_present(self, mock_router, mock_budget):
        mock_budget.can_afford.return_value = True
        mock_router.return_value = Completion(
            text="I see a flowchart with three steps.",
            model="gemini-3.6-flash",
            provider="gemini-direct",
            total_tokens=95,
        )

        fake_image = b"flowchart_png_bytes"
        resp = chat(
            user_id=123,
            user_message="Explain the diagram",
            image_bytes=fake_image,
            image_mime_type="image/png",
        )

        self.assertEqual(resp.text, "I see a flowchart with three steps.")
        # Ensure task_type was passed as "vision"
        mock_router.assert_called_once()
        self.assertEqual(mock_router.call_args[1]["task_type"], "vision")

    @patch("agent.chat.token_budget")
    @patch("agent.chat.router.call_with_failover")
    def test_chat_uses_chat_task_when_no_image(self, mock_router, mock_budget):
        mock_budget.can_afford.return_value = True
        mock_router.return_value = Completion(
            text="Hello there!",
            model="gpt-oss-120b",
            provider="groq",
            total_tokens=25,
        )

        resp = chat(user_id=123, user_message="Hello")
        self.assertEqual(resp.text, "Hello there!")
        mock_router.assert_called_once()
        self.assertEqual(mock_router.call_args[1]["task_type"], "chat")

    @patch("agent.chat.token_budget")
    @patch("agent.chat.router.call_with_failover")
    def test_chat_uses_chat_task_for_non_image_media(self, mock_router, mock_budget):
        mock_budget.can_afford.return_value = True
        mock_router.return_value = Completion(
            text="I can read the file metadata, but I need the actual extracted text for a proper summary.",
            model="gpt-oss-120b",
            provider="groq",
            total_tokens=42,
        )

        resp = chat(
            user_id=123,
            user_message="Read the PDF I have provided",
            image_bytes=b"%PDF-1.4 fake bytes",
            image_mime_type="application/pdf",
        )

        self.assertEqual(resp.text, "I can read the file metadata, but I need the actual extracted text for a proper summary.")
        mock_router.assert_called_once()
        self.assertEqual(mock_router.call_args[1]["task_type"], "chat")
        self.assertIn("application/pdf", mock_router.call_args[1]["messages"][-1].content)


class TelegramDoorVisionTests(unittest.TestCase):
    def test_screen_message_allows_image_without_text(self):
        msg = IncomingMessage(
            user_id=12345,
            text="",
            image_bytes=b"sample_image",
            image_mime_type="image/jpeg",
        )
        with patch("interfaces.telegram_door.owner_id", return_value=12345):
            decision = screen_message(msg)
            self.assertTrue(decision.allowed)

    def test_screen_message_rejects_empty_text_without_image(self):
        msg = IncomingMessage(user_id=12345, text="   ")
        with patch("interfaces.telegram_door.owner_id", return_value=12345):
            decision = screen_message(msg)
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason, EMPTY_MESSAGE)

    def test_dispatch_forwards_image_bytes_to_core_handler(self):
        received = {}

        def handler(text, img=None, mime="image/jpeg"):
            received["text"] = text
            received["img"] = img
            received["mime"] = mime
            return "Vision analysis complete"

        door = TelegramDoor(core_handler=handler)
        fake_img = b"photo_bytes"
        with patch("interfaces.telegram_door.owner_id", return_value=12345):
            reply = door.handle(
                IncomingMessage(
                    user_id=12345,
                    text="Examine this",
                    image_bytes=fake_img,
                    image_mime_type="image/jpeg",
                )
            )

        self.assertEqual(reply.text, "Vision analysis complete")
        self.assertEqual(received["text"], "Examine this")
        self.assertEqual(received["img"], fake_img)
        self.assertEqual(received["mime"], "image/jpeg")


class SplitReplyTests(unittest.TestCase):
    """Verify _split_reply respects TG_MAX_LENGTH and keeps content intact."""

    def setUp(self):
        from interfaces.telegram_door import _split_reply
        self._split = _split_reply

    def test_short_text_not_split(self):
        text = "Hello world"
        chunks = self._split(text, limit=100)
        self.assertEqual(chunks, [text])

    def test_text_at_exact_limit_not_split(self):
        text = "A" * 100
        chunks = self._split(text, limit=100)
        self.assertEqual(chunks, [text])

    def test_multiline_split_on_newline(self):
        # 3 lines of 60 chars each; limit=100 → first two lines fit (120 > 100)
        # so it should split after line 1 (60 chars) + line 2 would exceed.
        line = "X" * 59 + "\n"
        text = line * 3
        chunks = self._split(text, limit=100)
        # All content must be preserved.
        self.assertEqual("".join(chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 100)

    def test_hard_cut_for_single_long_line(self):
        text = "B" * 250
        chunks = self._split(text, limit=100)
        self.assertEqual("".join(chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 100)

    def test_full_tg_limit(self):
        # Simulate a 5000-char reply (> 4096).
        text = ("Line of text.\n") * 360  # ~5040 chars
        chunks = self._split(text)  # uses default TG_MAX_LENGTH=4096
        self.assertEqual("".join(chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4096)


if __name__ == "__main__":
    unittest.main(verbosity=2)
