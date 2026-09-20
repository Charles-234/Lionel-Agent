"""Tests for the pure identity allowlist (Phase 9 groundwork).

The registry answers one question only: is this sender admitted, and as
what? These tests prove it never guesses, never leaks, and never reaches
outside its own in-memory data.
"""

import unittest

from identity.registry import (
    ROLE_COLLABORATOR,
    ROLE_NONE,
    ROLE_OWNER,
    IdentityRegistry,
    Person,
)


class IdentityRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = IdentityRegistry()
        self.registry.seed_owner(12345, display_name="Charles")

    def test_owner_is_seeded_exactly_once(self):
        self.assertEqual(self.registry.owner_id, 12345)
        with self.assertRaises(ValueError):
            self.registry.seed_owner(999)

    def test_owner_shape_is_validated(self):
        with self.assertRaises(ValueError):
            IdentityRegistry().seed_owner("12345")
        with self.assertRaises(ValueError):
            IdentityRegistry().seed_owner(True)
        with self.assertRaises(ValueError):
            IdentityRegistry().seed_owner(-1)

    def test_only_the_owner_may_invite(self):
        person = self.registry.invite(777, invited_by=12345, display_name="ally")
        self.assertEqual(person.role, ROLE_COLLABORATOR)
        with self.assertRaises(ValueError):
            self.registry.invite(888, invited_by=777)

    def test_invite_requires_a_seeded_owner(self):
        with self.assertRaises(ValueError):
            IdentityRegistry().invite(777, invited_by=12345)

    def test_invite_rejects_duplicates_and_owner_id(self):
        self.registry.invite(777, invited_by=12345)
        with self.assertRaises(ValueError):
            self.registry.invite(777, invited_by=12345)
        with self.assertRaises(ValueError):
            self.registry.invite(12345, invited_by=12345)

    def test_revoke_and_restore_round_trip(self):
        self.registry.invite(777, invited_by=12345)
        self.assertTrue(self.registry.revoke(777, by=12345))
        self.assertFalse(self.registry.is_admitted(777).allowed)
        self.assertTrue(self.registry.restore(777, by=12345))
        self.assertTrue(self.registry.is_admitted(777).allowed)

    def test_revoke_is_idempotent_and_guarded(self):
        self.registry.invite(777, invited_by=12345)
        self.assertTrue(self.registry.revoke(777, by=12345))
        self.assertFalse(self.registry.revoke(777, by=12345))
        self.assertFalse(self.registry.revoke(888, by=12345))
        with self.assertRaises(ValueError):
            self.registry.revoke(777, by=999)
        with self.assertRaises(ValueError):
            self.registry.revoke(12345, by=12345)

    def test_restore_is_idempotent_and_guarded(self):
        self.assertFalse(self.registry.restore(888, by=12345))
        self.registry.invite(777, invited_by=12345)
        self.assertFalse(self.registry.restore(777, by=12345))
        self.registry.revoke(777, by=12345)
        self.assertTrue(self.registry.restore(777, by=12345))
        self.assertFalse(self.registry.restore(777, by=12345))
        with self.assertRaises(ValueError):
            self.registry.restore(777, by=999)

    def test_admission_answers_are_explicit(self):
        self.registry.invite(777, invited_by=12345)
        self.assertTrue(self.registry.is_admitted(12345).allowed)
        self.assertTrue(self.registry.is_admitted(777).allowed)
        refused = self.registry.is_admitted(888)
        self.assertFalse(refused.allowed)
        self.assertEqual(refused.role, ROLE_NONE)
        self.registry.revoke(777, by=12345)
        revoked = self.registry.is_admitted(777)
        self.assertFalse(revoked.allowed)
        self.assertEqual(revoked.role, ROLE_COLLABORATOR)

    def test_admission_refuses_unknown_shapes_quietly(self):
        for bad in (None, "777", True, 7.7, 0, -7):
            self.assertFalse(self.registry.is_admitted(bad).allowed)
        self.assertIsNone(self.registry.lookup("777"))

    def test_admitted_ids_are_sorted_and_exclude_revoked(self):
        self.registry.invite(999, invited_by=12345)
        self.registry.invite(777, invited_by=12345)
        self.registry.revoke(999, by=12345)
        self.assertEqual(self.registry.admitted_ids(), (777, 12345))

    def test_lookup_returns_frozen_records(self):
        person = self.registry.lookup(12345)
        self.assertIsInstance(person, Person)
        self.assertEqual(person.role, ROLE_OWNER)
        self.assertEqual(person.invited_by, 0)


if __name__ == "__main__":
    unittest.main()
