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

from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import FederatingModuleApiTestCase

logger = logging.getLogger(__name__)


class LocalJoinTestCase(FederatingModuleApiTestCase):
    """
    Tests to verify that we don't break local public/private rooms by accident.
    Specifically, this checks the code for joining a room and not just inviting. This is
    needed for PRO servers as they are allowed to have public rooms. EPA servers do not
    need this test, as they do not allow for local joining.
    """

    # server_name_for_this_server = "tim.test.gematik.de"

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.user_b = self.register_user("b", "password")
        self.user_c = self.register_user("c", "password")
        self.user_d = self.register_user("d", "password")
        self.access_token_a = self.login("a", "password")
        self.access_token_b = self.login("b", "password")
        self.access_token_c = self.login("c", "password")
        self.access_token_d = self.login("d", "password")

    def test_joining_public_with_invites(self) -> None:
        """Test joining a local public room with invites is allowed"""
        room_id = self.create_local_room(self.user_a, [], is_public=True)
        assert room_id is not None, "Room should have been created"

        self.helper.invite(room_id, self.user_a, self.user_b, tok=self.access_token_a)
        self.helper.invite(room_id, self.user_a, self.user_c, tok=self.access_token_a)
        self.helper.invite(room_id, self.user_a, self.user_d, tok=self.access_token_a)

        self.helper.join(room_id, self.user_b, tok=self.access_token_b)
        self.helper.join(room_id, self.user_c, tok=self.access_token_c)
        self.helper.join(room_id, self.user_d, tok=self.access_token_d)

    def test_joining_public_no_invites(self) -> None:
        """Test joining a local public room with no invites is allowed"""
        room_id = self.create_local_room(self.user_a, [], is_public=True)
        assert room_id is not None, "Room should have been created"

        self.helper.join(room_id, self.user_b, tok=self.access_token_b)
        self.helper.join(room_id, self.user_c, tok=self.access_token_c)
        self.helper.join(room_id, self.user_d, tok=self.access_token_d)

    def test_joining_private_no_invites(self) -> None:
        """Test joining a local private room with no invites is denied"""
        room_id = self.create_local_room(self.user_a, [], is_public=False)
        assert room_id is not None, "Room should have been created"

        self.helper.join(
            room_id,
            self.user_b,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_b,
        )
        self.helper.join(
            room_id,
            self.user_c,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_c,
        )
        self.helper.join(
            room_id,
            self.user_d,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_d,
        )

    def test_joining_private_with_invites(self) -> None:
        """Test joining a local private room with invites is allowed"""
        room_id = self.create_local_room(self.user_a, [], is_public=False)
        assert room_id is not None, "Room should have been created"

        self.helper.invite(room_id, self.user_a, self.user_b, tok=self.access_token_a)
        self.helper.invite(room_id, self.user_a, self.user_c, tok=self.access_token_a)
        self.helper.invite(room_id, self.user_a, self.user_d, tok=self.access_token_a)

        self.helper.join(room_id, self.user_b, tok=self.access_token_b)
        self.helper.join(room_id, self.user_c, tok=self.access_token_c)
        self.helper.join(room_id, self.user_d, tok=self.access_token_d)
