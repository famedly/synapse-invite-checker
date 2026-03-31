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

from parameterized import parameterized
from synapse.server import HomeServer
from synapse.util.clock import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import FederatingModuleApiTestCase
from tests.server import make_request


class RoomVersionCreateRoomTest(FederatingModuleApiTestCase):
    """
    Tests for limiting room versions when creating rooms. Use the defaults of room
    versions "9" or "10"
    """

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
        version that is outside of what is wanted, fail
        """
        self.create_local_room(
            self.user_a,
            is_public=is_public,
            room_version="8",
            expected_code=HTTPStatus.BAD_REQUEST,
        )

        self.create_local_room(
            self.user_a,
            is_public=is_public,
            room_version=8,  # type: ignore[arg-type]
            expected_code=HTTPStatus.BAD_REQUEST,
        )

        self.create_local_room(
            self.user_a,
            is_public=is_public,
            room_version="11",
            expected_code=HTTPStatus.BAD_REQUEST,
        )

        self.create_local_room(
            self.user_a,
            is_public=is_public,
            room_version=11,  # type: ignore[arg-type]
            expected_code=HTTPStatus.BAD_REQUEST,
        )

        self.create_local_room(
            self.user_a,
            is_public=is_public,
            room_version="bad_version",
            expected_code=HTTPStatus.BAD_REQUEST,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_succeeds(self, _label: str, is_public: bool) -> None:
        """
        Tests that a room version that is allowed succeeds
        """
        self.create_local_room(
            self.user_a,
            is_public=is_public,
            room_version="9",
            expected_code=HTTPStatus.OK,
        )
        self.create_local_room(
            self.user_a,
            is_public=is_public,
            room_version="10",
            expected_code=HTTPStatus.OK,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_room_upgrades(self, _label: str, is_public: bool) -> None:
        """
        Test room upgrades fail outside of defaults
        """
        # 9 -> 9 works
        room_id = self.create_local_room(
            self.user_a, is_public=is_public, room_version="9"
        )
        assert room_id
        room_id = self.upgrade_room_to_version(room_id, "9", self.access_token_a)
        assert room_id

        # 10 -> 10 works
        room_id = self.create_local_room(
            self.user_a, is_public=is_public, room_version="10"
        )
        assert room_id
        room_id = self.upgrade_room_to_version(room_id, "10", self.access_token_a)
        assert room_id

        # 9 -> 10 works
        room_id = self.create_local_room(
            self.user_a, is_public=is_public, room_version="9"
        )
        assert room_id
        room_id = self.upgrade_room_to_version(room_id, "10", self.access_token_a)
        assert room_id

        # 9 -> 8 doesn't work
        room_id = self.create_local_room(
            self.user_a, is_public=is_public, room_version="9"
        )
        assert room_id

        room_id = self.upgrade_room_to_version(room_id, "8", self.access_token_a)
        assert room_id is None

        # 9 -> 8 requires an admin
        room_id = self.create_local_room(
            self.admin_b, is_public=is_public, room_version="9"
        )
        assert room_id

        room_id = self.upgrade_room_to_version(room_id, "8", self.access_token_b)
        assert room_id
