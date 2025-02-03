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
import contextlib
from http import HTTPStatus

from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import ModuleApiTestCase, construct_extra_content


class RoomVersionCreateRoomTest(ModuleApiTestCase):
    """
    Tests for limiting room versions when creating rooms. Use the defaults of room
    versions "9" or "10"
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)

        self.user_a = self.register_user("a", "password")
        self.access_token_a = self.login("a", "password")

    def user_create_room(
        self,
        invitee_list: list[str] | None = None,
        is_public: bool = False,
        room_ver: str | int = None,
        expect_code: int = HTTPStatus.OK,
    ) -> str | None:
        """
        Helper to send an api request with a full set of required additional room state
        to the room creation matrix endpoint. Returns a room_id if successful
        """
        # Hide the assertion from create_room_as() when the error code is unexpected. It
        # makes errors for the tests less clear when all we get is the http response
        with contextlib.suppress(AssertionError):
            return self.helper.create_room_as(
                self.user_a,
                is_public=is_public,
                room_version=room_ver,
                tok=self.access_token_a,
                expect_code=expect_code,
                extra_content=construct_extra_content(self.user_a, invitee_list or []),
            )
        return None

    def test_create_room_fails(self) -> None:
        """
        Test that most generic ways of not doing a room version string, and a room
        version that is outside of what is wanted, fail
        """
        self.assertIsNone(
            self.user_create_room(
                [],
                is_public=False,
                room_ver="8",
                expect_code=HTTPStatus.BAD_REQUEST,
            )
        )
        self.assertIsNone(
            self.user_create_room(
                [],
                is_public=False,
                room_ver=8,
                expect_code=HTTPStatus.BAD_REQUEST,
            )
        )

        self.assertIsNone(
            self.user_create_room(
                [],
                is_public=False,
                room_ver="11",
                expect_code=HTTPStatus.BAD_REQUEST,
            )
        )
        self.assertIsNone(
            self.user_create_room(
                [],
                is_public=False,
                room_ver=11,
                expect_code=HTTPStatus.BAD_REQUEST,
            )
        )
        self.assertIsNone(
            self.user_create_room(
                [],
                is_public=False,
                room_ver="bad_version",
                expect_code=HTTPStatus.BAD_REQUEST,
            )
        )

    def test_create_room_succeeds(self) -> None:
        """
        Tests that a room version that is allowed succeeds
        """
        assert self.user_create_room(
            [],
            is_public=False,
            room_ver="9",
            expect_code=HTTPStatus.OK,
        )
        assert self.user_create_room(
            [],
            is_public=False,
            room_ver="10",
            expect_code=HTTPStatus.OK,
        )
