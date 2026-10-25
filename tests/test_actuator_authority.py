import unittest

from fermentalab.actuator_authority import (
    ActuatorAuthority,
    ActuatorMode,
    AuthorityToken,
)


class TestActuatorAuthority(unittest.TestCase):

    def setUp(self):
        self.authority = ActuatorAuthority()

    def request(self, token, heating=False, cooling=False):
        return self.authority.evaluate(
            token=token,
            heating_requested=heating,
            cooling_requested=cooling,
        )

    def test_default_inhibited(self):
        self.assertFalse(self.authority.authorised)

    def test_request_without_authority_is_off(self):
        decision = self.request(None, heating=True)
        self.assertEqual(decision.mode, ActuatorMode.OFF)

    def test_grant_issues_token(self):
        token = self.authority.grant()
        self.assertIsInstance(token, AuthorityToken)
        self.assertTrue(self.authority.authorised)

    def test_valid_heating_request(self):
        token = self.authority.grant()
        decision = self.request(token, heating=True)
        self.assertEqual(decision.mode, ActuatorMode.HEATING)

    def test_valid_cooling_request(self):
        token = self.authority.grant()
        decision = self.request(token, cooling=True)
        self.assertEqual(decision.mode, ActuatorMode.COOLING)

    def test_no_request_is_off(self):
        token = self.authority.grant()
        decision = self.request(token)
        self.assertEqual(decision.mode, ActuatorMode.OFF)

    def test_revoke_disables_authority(self):
        token = self.authority.grant()
        self.authority.revoke()

        decision = self.request(token, heating=True)
        self.assertEqual(decision.mode, ActuatorMode.OFF)
        self.assertFalse(self.authority.authorised)

    def test_regrant_invalidates_old_token(self):
        old_token = self.authority.grant()
        new_token = self.authority.grant()

        self.assertNotEqual(
            old_token.generation,
            new_token.generation,
        )

        decision = self.request(old_token, heating=True)
        self.assertEqual(decision.mode, ActuatorMode.OFF)

    def test_stale_token_revokes_current_authority(self):
        old_token = self.authority.grant()
        self.authority.grant()

        self.request(old_token, heating=True)

        self.assertFalse(self.authority.authorised)

    def test_conflicting_requests_rejected(self):
        token = self.authority.grant()

        decision = self.request(
            token,
            heating=True,
            cooling=True,
        )

        self.assertEqual(decision.mode, ActuatorMode.OFF)
        self.assertFalse(self.authority.authorised)

    def test_non_boolean_request_rejected(self):
        token = self.authority.grant()

        decision = self.request(
            token,
            heating=1,
        )

        self.assertEqual(decision.mode, ActuatorMode.OFF)
        self.assertFalse(self.authority.authorised)

    def test_invalid_token_rejected(self):
        self.authority.grant()

        decision = self.request(
            "invalid",
            heating=True,
        )

        self.assertEqual(decision.mode, ActuatorMode.OFF)
        self.assertFalse(self.authority.authorised)

    def test_forged_generation_rejected(self):
        token = self.authority.grant()

        forged = AuthorityToken(
            generation=token.generation + 1,
            nonce=token.nonce,
        )

        decision = self.request(forged, heating=True)

        self.assertEqual(decision.mode, ActuatorMode.OFF)

    def test_forged_nonce_rejected(self):
        token = self.authority.grant()

        forged = AuthorityToken(
            generation=token.generation,
            nonce=b"incorrect",
        )

        decision = self.request(forged, cooling=True)

        self.assertEqual(decision.mode, ActuatorMode.OFF)

    def test_generation_advances_on_revoke(self):
        token = self.authority.grant()
        self.authority.revoke()

        self.assertGreater(
            self.authority.generation,
            token.generation,
        )

    def test_repeated_revoke_remains_off(self):
        self.authority.revoke()
        decision = self.authority.revoke()

        self.assertEqual(decision.mode, ActuatorMode.OFF)
        self.assertFalse(self.authority.authorised)

    def test_no_simultaneous_heating_and_cooling(self):
        token = self.authority.grant()

        for heating, cooling in (
            (False, False),
            (True, False),
            (False, True),
        ):
            decision = self.request(
                token,
                heating=heating,
                cooling=cooling,
            )

            self.assertFalse(
                decision.heating_permitted
                and decision.cooling_permitted
            )


if __name__ == "__main__":
    unittest.main()
