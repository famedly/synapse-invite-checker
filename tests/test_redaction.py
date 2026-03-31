# Copyright (C) 2025 Famedly
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import logging
from http import HTTPStatus

from parameterized import parameterized_class
from synapse.server import HomeServer
from synapse.util.clock import Clock
from twisted.internet.testing import MemoryReactor

from synapse_invite_checker.types import TimVersion
from tests.base import FederatingModuleApiTestCase

logger = logging.getLogger(__name__)

TWENTY_FOUR_HOURS_IN_SECONDS = 24 * 60 * 60


def _redact_event_helper(
    make_request,
    room_id: str,
    event_id: str,
    tok: str,
    expect_code: int = HTTPStatus.OK,
) -> dict:
    channel = make_request(
        "PUT",
        f"/_matrix/client/r0/rooms/{room_id}/redact/{event_id}/1",
        content={"reason": "test redaction"},
        access_token=tok,
    )
    assert (
        channel.code == expect_code
    ), f"Expected {expect_code}, got {channel.code}: {channel.json_body}"
    return channel.json_body


@parameterized_class(
    ("DEFAULT_ROOM_VERSION",),
    [
        ("9",),
        ("10",),
        ("11",),
        ("12",),
    ],
)
class RedactionTimeLimitTestCase(FederatingModuleApiTestCase):
    """
    Test that redactions of events older than 24 hours are rejected in TIM version 1.2.
    """

    TIM_VERSION = TimVersion.V1_2
    ALLOWED_ROOM_VERSIONS = ["9", "10", "11", "12"]

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.login("a", "password")
        self.admin_user = self.register_user("admin_user", "password", admin=True)
        self.login("admin_user", "password")

    def _redact_event(
        self, room_id: str, event_id: str, tok: str, expect_code: int = HTTPStatus.OK
    ) -> dict:
        return _redact_event_helper(
            self.make_request,
            room_id,
            event_id,
            tok,
            expect_code=expect_code,
        )

    def test_redaction_within_24h_allowed(self) -> None:
        room_id = self.create_local_room(self.user_a, [], False)
        assert room_id is not None

        body = self.helper.send(
            room_id, "message", tok=self.map_user_id_to_token[self.user_a]
        )
        event_id = body["event_id"]

        # Redact immediately (within 24h) should succeed
        self._redact_event(
            room_id,
            event_id,
            self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.OK,
        )

    def test_redaction_after_24h_rejected(self) -> None:
        room_id = self.create_local_room(self.user_a, [], False)
        assert room_id is not None

        body = self.helper.send(
            room_id, "message", tok=self.map_user_id_to_token[self.user_a]
        )
        event_id = body["event_id"]

        # Advance time past 24 hours
        self.reactor.advance(TWENTY_FOUR_HOURS_IN_SECONDS + 1)

        # Redact after 24h should be rejected
        self._redact_event(
            room_id,
            event_id,
            self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.FORBIDDEN,
        )

    def test_redaction_after_24h_allowed_for_admin(self) -> None:
        room_id = self.create_local_room(self.admin_user, [], False)
        assert room_id is not None

        body = self.helper.send(
            room_id, "message", tok=self.map_user_id_to_token[self.admin_user]
        )
        event_id = body["event_id"]

        # Advance time past 24 hours
        self.reactor.advance(TWENTY_FOUR_HOURS_IN_SECONDS + 1)

        # Admin redaction after 24h should succeed
        self._redact_event(
            room_id,
            event_id,
            self.map_user_id_to_token[self.admin_user],
            expect_code=HTTPStatus.OK,
        )


@parameterized_class(
    ("DEFAULT_ROOM_VERSION",),
    [
        ("9",),
        ("10",),
        ("11",),
        ("12",),
    ],
)
class RedactionTimeLimitV1_1TestCase(FederatingModuleApiTestCase):
    """
    Test that redactions are NOT restricted by time in TIM version 1.1.
    """

    TIM_VERSION = TimVersion.V1_1
    ALLOWED_ROOM_VERSIONS = ["9", "10", "11", "12"]

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.login("a", "password")

    def _redact_event(
        self, room_id: str, event_id: str, tok: str, expect_code: int = HTTPStatus.OK
    ) -> dict:
        return _redact_event_helper(
            self.make_request,
            room_id,
            event_id,
            tok,
            expect_code=expect_code,
        )

    def test_redaction_after_24h_allowed_in_v1_1(self) -> None:
        room_id = self.create_local_room(self.user_a, [], False)
        assert room_id is not None

        body = self.helper.send(
            room_id, "message", tok=self.map_user_id_to_token[self.user_a]
        )
        event_id = body["event_id"]

        # Advance time past 24 hours
        self.reactor.advance(TWENTY_FOUR_HOURS_IN_SECONDS + 1)

        # Redact after 24h should succeed
        self._redact_event(
            room_id,
            event_id,
            self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.OK,
        )
