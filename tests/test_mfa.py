"""Tests for the pure MFA groundwork (RFC 6238 TOTP, stdlib only).

Confirms: interoperability with RFC 6238 test vectors, window behaviour,
constant-time compare path, tamper resistance, and provisioning URI shape.
No I/O, no network, no persistence.
"""

import base64
import unittest
from urllib.parse import parse_qs, urlparse

from identity import mfa


class TotpRfcVectorTests(unittest.TestCase):
    # RFC 6238 appendix B reference secret ("12345678901234567890" in ASCII).
    RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_rfc6238_sha1_vectors(self):
        cases = [
            (59, "287082"),
            (1111111109, "081804"),
            (1111111111, "050471"),
            (1234567890, "005924"),
            (2000000000, "279037"),
        ]
        for timestamp, expected in cases:
            self.assertEqual(
                mfa.totp_at(self.RFC_SECRET, timestamp), expected,
                msg=f"vector failed at t={timestamp}",
            )

    def test_rfc6238_sha256_vector(self):
        # RFC 6238 appendix B: the SHA-256 secret is the 32-byte ASCII string
        # "12345678901234567890123456789012". Build the base32 form from the
        # raw bytes so the vector test stays exact instead of hand-typed.
        secret256 = base64.b32encode(
            b"12345678901234567890123456789012"
        ).decode("ascii").rstrip("=")
        self.assertEqual(
            mfa.totp_at(secret256, 1111111109, digits=8, algorithm="sha256"),
            "68084774",
        )


class TotpVerifyTests(unittest.TestCase):
    def setUp(self):
        self.secret = mfa.generate_secret()

    def test_generated_secret_round_trips(self):
        code = mfa.totp_at(self.secret, 1000.0)
        self.assertTrue(mfa.verify(self.secret, code, 1000.0))
        self.assertFalse(mfa.verify(self.secret, "000000", 1000.0))

    def test_window_admits_neighbours_only(self):
        code = mfa.totp_at(self.secret, 1000.0)
        self.assertTrue(mfa.verify(self.secret, code, 1000.0 + 30))
        self.assertFalse(mfa.verify(self.secret, code, 1000.0 + 30 * 3))

    def test_wrong_shapes_are_refused_safely(self):
        code = mfa.totp_at(self.secret, 1000.0)
        for bad in ("", None, "12ab56", code[:-1] + "x", code + "0"):
            self.assertFalse(mfa.verify(self.secret, bad, 1000.0))

    def test_verify_never_accepts_a_code_from_a_different_secret(self):
        other = mfa.generate_secret()
        code = mfa.totp_at(other, 1000.0)
        self.assertFalse(mfa.verify(self.secret, code, 1000.0))

    def test_invalid_window_raises_not_guesses(self):
        code = mfa.totp_at(self.secret, 1000.0)
        with self.assertRaises(ValueError):
            mfa.verify(self.secret, code, 1000.0, window=9)


class ProvisioningUriTests(unittest.TestCase):
    def test_uri_contains_required_components(self):
        secret = mfa.generate_secret()
        uri = mfa.provisioning_uri(secret, "charles@lionel", issuer="Lionel")
        parsed = urlparse(uri)
        self.assertEqual(parsed.scheme, "otpauth")
        self.assertEqual(parsed.netloc, "totp")
        self.assertIn("Lionel%3Acharles%40lionel", parsed.path)
        query = parse_qs(parsed.query)
        self.assertEqual(query["secret"], [secret])
        self.assertEqual(query["issuer"], ["Lionel"])
        self.assertEqual(query["digits"], ["6"])
        self.assertEqual(query["period"], ["30"])


if __name__ == "__main__":
    unittest.main()