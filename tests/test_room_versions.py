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
from http import HTTPStatus
from typing import Any

from parameterized import parameterized, parameterized_class
from synapse.server import HomeServer
from synapse.util.clock import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import FederatingModuleApiTestCase
from tests.server import make_request


@parameterized_class(
    (
        "DEFAULT_ROOM_VERSION",
        "ALLOWED_ROOM_VERSIONS",
        "ROOM_VERSIONS_THAT_SHOULD_FAIL",
        "ROOM_UPGRADE_AND_DOWNGRADE_PAIRINGS",
        "ROOM_UPGRADE_AND_DOWNGRADE_FAILURES",
    ),
    [
        (
            "9",
            ["9", "10"],
            ["8", 11, "bad_version"],
            [("9", "10"), ("10", "9")],
            ["8", "11"],
        ),
        (
            "10",
            ["10", "11"],
            ["9", "not_real", 9],
            [("10", "11"), ("11", "10")],
            ["9", "12"],
        ),
        (
            "11",
            ["11", "12"],
            ["10", "should_fail"],
            [("11", "12"), ("12", "11")],
            ["10"],
        ),
        (
            "12",
            ["11", "12"],
            ["9", 1, ["bad_version"]],
            [("11", "12"), ("12", "11")],
            ["10"],
        ),
    ],
)
class RoomVersionCreateRoomTest(FederatingModuleApiTestCase):
    """
    Tests for limiting room versions when upgrading and downgrading rooms.
    """

    # This is defined through the parameterize_class
    # ALLOWED_ROOM_VERSIONS
    # One test function checks these iteratively for failure. All should BAD_REQUEST
    ROOM_VERSIONS_THAT_SHOULD_FAIL: list[Any]
    # Tuples of pairings of room versions used to verify upgrades and downgrades. Going
    # either direction should work as long as both are inside the ALLOWED_ROOM_VERSIONS
    # limits.
    # (start version, end version)
    ROOM_UPGRADE_AND_DOWNGRADE_PAIRINGS: list[tuple[str, str]]
    # A list of upgrades or downgrades that should fall outside the limits defined by
    # ALLOWED_ROOM_VERSIONS. These should all fail. Test starts with default room ver.
    ROOM_UPGRADE_AND_DOWNGRADE_FAILURES: list[str]

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)

        self.user_a = self.register_user("a", "password")
        self.access_token_a = self.login("a", "password")

        self.admin_b = self.register_user("b", "password", admin=True)
        self.access_token_b = self.login("b", "password")

    def upgrade_room_to_version(
        self,
        _room_id: str,
        room_version: str,
        tok: str | None = None,
    ) -> str | None:
        """
        Upgrade a room.

        Args:
            _room_id
            room_version: The room version to upgrade the room to.
            tok: The access token to use in the request.
        Returns:
            The ID of the newly created room, or None if the request failed.
        """
        path = f"/_matrix/client/r0/rooms/{_room_id}/upgrade"
        content = {"new_version": room_version}

        channel = make_request(
            self.reactor,
            self.site,
            "POST",
            path,
            content,
            access_token=tok,
        )

        return channel.json_body.get("replacement_room")

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_fails(self, _label: str, is_public: bool) -> None:
        """
        Test that most generic ways of not doing a room version string, and a room
        version that is outside what is allowed, fail
        """
        for room_version in self.ROOM_VERSIONS_THAT_SHOULD_FAIL:
            self.create_local_room(
                self.user_a,
                is_public=is_public,
                room_version=room_version,
                expected_code=HTTPStatus.BAD_REQUEST,
            )

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_succeeds(self, _label: str, is_public: bool) -> None:
        """
        Tests that a room version that is allowed succeeds. This will use the default
        room version since they are all itemized per the parameterize_class
        """
        self.create_local_room(
            self.user_a,
            is_public=is_public,
            expected_code=HTTPStatus.OK,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_room_upgrades_and_downgrades(self, _label: str, is_public: bool) -> None:
        """
        Test room upgrades and downgrades work inside of limits, including "upgrading"
        to the same room version
        """
        for (
            start_room_version,
            finish_room_version,
        ) in self.ROOM_UPGRADE_AND_DOWNGRADE_PAIRINGS:

            # First test that a room can be "upgraded" into the same room version
            room_id = self.create_local_room(
                self.user_a, is_public=is_public, room_version=start_room_version
            )
            assert room_id
            room_id = self.upgrade_room_to_version(
                room_id, start_room_version, self.access_token_a
            )
            assert room_id

            # Then test that a real version change works
            room_id = self.create_local_room(
                self.user_a, is_public=is_public, room_version=start_room_version
            )
            assert room_id
            room_id = self.upgrade_room_to_version(
                room_id, finish_room_version, self.access_token_a
            )
            assert room_id

    @parameterized.expand([("public", True), ("private", False)])
    def test_room_version_fails_outside_of_allowed_limits(
        self, _label: str, is_public: bool
    ) -> None:
        """
        Test that changing a room version outside the limits fails, but works for an
        admin. Each room starts with the DEFAULT_ROOM_VERSION
        """
        for change_room_version_to in self.ROOM_UPGRADE_AND_DOWNGRADE_FAILURES:
            # First test that the "downgrade" fails with normal user
            # This is a DEFAULT_ROOM_VERSION room
            room_id = self.create_local_room(self.user_a, is_public=is_public)
            assert room_id

            room_id = self.upgrade_room_to_version(
                room_id, change_room_version_to, self.access_token_a
            )
            # This is None because the room should fail
            assert room_id is None

            # Then make sure it works with an admin. This is a DEFAULT_ROOM_VERSION room
            room_id = self.create_local_room(self.admin_b, is_public=is_public)
            assert room_id

            room_id = self.upgrade_room_to_version(
                room_id, change_room_version_to, self.access_token_b
            )
            assert room_id
