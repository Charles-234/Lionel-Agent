"""Tests for the governed web fetcher.

Everything runs offline: the HTTP layer is faked, so no test touches the
network. Proves the fetcher's own hygiene: URL scheme/private-host checks,
script/style stripping, secret redaction, size caps, and that simulation
stays explicitly unverified.
"""

import unittest

from tools.base import ToolResult
from tools.mocks import MockWebFetch
from tools.web_fetcher import WebFetcher, _clean_url, _extract_text


class _FakeResponse:
    def __init__(self, status_code=200, body=b""):
        self.status_code = status_code
        self._body = body

    def iter_content(self, chunk_size=65536):
        yield self._body

    def close(self):
        pass


class _FakeSessionModule:
    """Stands in for requests inside the module under test."""

    class exceptions:  # noqa: N801 - mirrors requests' namespace
        class RequestException(Exception):
            pass


def _raise(_exc):
    raise _FakeSessionModule.exceptions.RequestException("boom")


def _return(response):
    return response


class UrlHygieneTests(unittest.TestCase):
    def test_only_public_http_https_survives(self):
        self.assertEqual(_clean_url("https://example.com/page"), "https://example.com/page")
        self.assertEqual(_clean_url("http://example.com"), "http://example.com")
        for bad in (
            "ftp://example.com",
            "file:///etc/passwd",
            "gopher://example.com",
            "https:///no-host",
            "not a url",
            "",
            None,
            123,
        ):
            self.assertEqual(_clean_url(bad), "", msg=f"should refuse {bad!r}")

    def test_private_and_local_addresses_are_refused(self):
        for private in (
            "http://localhost/x",
            "http://127.0.0.1/x",
            "http://10.0.0.5/x",
            "http://192.168.1.1/x",
            "http://169.254.1.1/x",
            "http://172.16.0.1/x",
        ):
            self.assertEqual(_clean_url(private), "", msg=f"should refuse {private}")

    def test_whitespace_and_oversized_urls_are_refused(self):
        self.assertEqual(_clean_url("https://example.com/a b"), "")
        self.assertEqual(_clean_url("https://" + "a" * 3000 + ".com"), "")


class TextExtractionTests(unittest.TestCase):
    def test_script_and_style_bodies_are_removed(self):
        html = b"<html><head><style>body{}</style></head><body><script>alert(1)</script><p>Hello</p></body></html>"
        text = _extract_text(html)
        self.assertNotIn("alert", text)
        self.assertNotIn("body{}", text)
        self.assertIn("Hello", text)

    def test_control_characters_are_cleaned(self):
        text = _extract_text(b"a\x00b\x07c\x1fd\x7fe")
        for ch in ("\x00", "\x07", "\x1d", "\x7f"):
            self.assertNotIn(ch, text)

    def test_secret_looking_lines_are_redacted(self):
        html = (
            b"<p>ok</p>\n"
            b"api_key = supersecret123\n"
            b"Authorization: Bearer abcdef\n"
            b"password: hunter2\n"
            b"<p>after</p>"
        )
        text = _extract_text(html)
        self.assertNotIn("supersecret123", text)
        self.assertNotIn("abcdef", text)
        self.assertNotIn("hunter2", text)
        self.assertIn("[redacted]", text)
        self.assertIn("after", text)

    def test_output_is_size_capped(self):
        text = _extract_text(b"x" * 500_000)
        self.assertLessEqual(len(text), 200_000)


class GovernedRunTests(unittest.TestCase):
    def setUp(self):
        self.fetcher = WebFetcher()

    def _patch_requests(self, response=None, exc=None):
        import tools.web_fetcher as wf

        fake = _FakeSessionModule()
        fake.get = lambda *args, **kwargs: (
            _raise(exc) if exc is not None else _return(response)
        )
        self._real_requests = wf.requests
        wf.requests = fake
        self.addCleanup(setattr, wf, "requests", self._real_requests)

    def test_network_failure_is_safe_and_untimed(self):
        self._patch_requests(exc=True)
        result = self.fetcher.run(url="https://example.com")
        self.assertFalse(result.success)
        self.assertNotIn("boom", (result.error or "").lower())

    def test_non_200_is_refused_without_body(self):
        self._patch_requests(_FakeResponse(status_code=403, body=b"secret page"))
        result = self.fetcher.run(url="https://example.com")
        self.assertFalse(result.success)
        self.assertIn("403", result.error)
        self.assertNotIn("secret page", (result.error or ""))

    def test_success_returns_clean_structured_text(self):
        body = b"<html><body><p>Clean content</p><script>evil()</script></body></html>"
        self._patch_requests(_FakeResponse(body=body))
        result = self.fetcher.run(url="https://example.com")
        self.assertTrue(result.success)
        self.assertIn("Clean content", result.data["text"])
        self.assertNotIn("evil()", result.data["text"])
        self.assertEqual(result.data["url"], "https://example.com")

    def test_invalid_url_never_touches_the_network(self):
        result = self.fetcher.run(url="file:///etc/passwd")
        self.assertFalse(result.success)
        self.assertIn("http(s)", result.error)

    def test_simulation_explicitly_unverified(self):
        registry_result = ToolResult(success=True)
        self.assertTrue(registry_result.success)  # keep import meaning explicit
        mock = MockWebFetch()
        sim = mock.run(url="https://example.com")
        self.assertEqual(sim.execution_mode, "simulation")
        self.assertFalse(sim.verified)


if __name__ == "__main__":
    unittest.main()