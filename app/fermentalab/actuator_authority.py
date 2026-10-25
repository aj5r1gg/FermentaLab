"""
FermentaLab simulated actuator authority.

This module evaluates whether advisory temperature-control requests
may be accepted by a simulated actuator layer.

It does not control GPIO, relays, mains equipment or physical outputs.

Authority is represented by an opaque, generation-bound token.
Revocation invalidates all previously issued tokens.
"""

from dataclasses import dataclass
from enum import Enum
from secrets import token_bytes


class ActuatorMode(Enum):
    OFF = "off"
    HEATING = "heating"
    COOLING = "cooling"


@dataclass(frozen=True)
class AuthorityToken:
    generation: int
    nonce: bytes


@dataclass(frozen=True)
class ActuatorDecision:
    mode: ActuatorMode
    heating_permitted: bool
    cooling_permitted: bool
    reason: str


class ActuatorAuthority:
    """
    Simulation-only authority boundary.

    No actuator request is permitted unless:
      - authority has explicitly been granted;
      - the supplied token matches the current generation;
      - the supplied token matches the current nonce;
      - the request is valid and mutually exclusive.

    Any invalid request revokes authority.
    """

    def __init__(self):
        self._generation = 0
        self._nonce = None
        self._authorised = False

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def authorised(self) -> bool:
        return self._authorised

    def grant(self) -> AuthorityToken:
        """
        Issue a new authority token.

        The caller is responsible for satisfying all external
        safety prerequisites before invoking this method.

        This method does not establish physical safety.
        """

        self._generation += 1
        self._nonce = token_bytes(32)
        self._authorised = True

        return AuthorityToken(
            generation=self._generation,
            nonce=self._nonce,
        )

    def revoke(self) -> ActuatorDecision:
        """
        Revoke authority and invalidate all previous tokens.
        """

        self._generation += 1
        self._nonce = None
        self._authorised = False

        return self._off("authority revoked")

    def evaluate(
        self,
        *,
        token: AuthorityToken | None,
        heating_requested: bool,
        cooling_requested: bool,
    ) -> ActuatorDecision:

        if not self._authorised:
            return self._off("authority not granted")

        if not isinstance(token, AuthorityToken):
            return self._fail("invalid authority token")

        if (
            type(token.generation) is not int
            or token.generation != self._generation
            or type(token.nonce) is not bytes
            or token.nonce != self._nonce
        ):
            return self._fail("stale or invalid authority token")

        if (
            type(heating_requested) is not bool
            or type(cooling_requested) is not bool
        ):
            return self._fail("invalid actuator request")

        if heating_requested and cooling_requested:
            return self._fail("conflicting actuator requests")

        if heating_requested:
            return ActuatorDecision(
                mode=ActuatorMode.HEATING,
                heating_permitted=True,
                cooling_permitted=False,
                reason="heating request authorised",
            )

        if cooling_requested:
            return ActuatorDecision(
                mode=ActuatorMode.COOLING,
                heating_permitted=False,
                cooling_permitted=True,
                reason="cooling request authorised",
            )

        return self._off("no actuator requested")

    def _fail(self, reason: str) -> ActuatorDecision:
        self.revoke()
        return self._off(reason)

    @staticmethod
    def _off(reason: str) -> ActuatorDecision:
        return ActuatorDecision(
            mode=ActuatorMode.OFF,
            heating_permitted=False,
            cooling_permitted=False,
            reason=reason,
        )
