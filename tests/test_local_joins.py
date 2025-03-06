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
import logging
from http import HTTPStatus

from parameterized import parameterized
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import ModuleApiTestCase, construct_extra_content


logger = logging.getLogger(__name__)


class LocalJoinTestCase(ModuleApiTestCase):
    # server_name_for_this_server = "tim.test.gematik.de"

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        #  "a" is a practitioner
        #  "b" is an organization
        #  "c" is an 'orgPract'
        self.user_a = self.register_user("a", "password")
        self.access_token_a = self.login("a", "password")
        self.user_b = self.register_user("b", "password")
        self.access_token_b = self.login("b", "password")
        self.user_c = self.register_user("c", "password")
        self.access_token_c = self.login("c", "password")

        # "d" is none of those types of actor and should be just a 'User'. For
        # context, this could be a chatbot or an office manager
        self.user_d = self.register_user("d", "password")
        self.access_token_d = self.login("d", "password")

        self.user_id_to_token = {
            self.user_a: self.access_token_a,
            self.user_b: self.access_token_b,
            self.user_c: self.access_token_c,
            self.user_d: self.access_token_d,
        }

    # def default_config(self) -> dict[str, Any]:
    #     conf = super().default_config()
    #     conf["server_notices"] = {"system_mxid_localpart": "server", "auto_join": True}
    #     return conf

    def user_create_room(
        self,
        creating_user: str,
        invitee_list: list[str],
        is_public: bool,
    ) -> str | None:
        """
        Helper to send an api request with a full set of required additional room state
        to the room creation matrix endpoint.
        """
        # Hide the assertion from create_room_as() when the error code is unexpected. It
        # makes errors for the tests less clear when all we get is the http response
        with contextlib.suppress(AssertionError):
            return self.helper.create_room_as(
                creating_user,
                is_public=is_public,
                tok=self.user_id_to_token.get(creating_user),
                extra_content=construct_extra_content(creating_user, invitee_list),
            )
        return None

    @parameterized.expand([("with_invites", True), ("no_invites", False)])
    def test_joining_public(self, label: str, use_invites: bool) -> None:
        room_id = self.user_create_room(self.user_a, [], is_public=True)
        if use_invites:
            self.helper.invite(
                room_id, self.user_a, self.user_b, tok=self.access_token_a
            )
            self.helper.invite(
                room_id, self.user_a, self.user_c, tok=self.access_token_a
            )
            self.helper.invite(
                room_id, self.user_a, self.user_d, tok=self.access_token_a
            )

        self.helper.join(room_id, self.user_b, tok=self.access_token_b)
        self.helper.join(room_id, self.user_c, tok=self.access_token_c)
        self.helper.join(room_id, self.user_d, tok=self.access_token_d)

    @parameterized.expand([("with_invites", True), ("no_invites", False)])
    def test_joining_private(self, label: str, use_invites: bool) -> None:
        room_id = self.user_create_room(self.user_a, [], is_public=False)
        if use_invites:
            self.helper.invite(
                room_id, self.user_a, self.user_b, tok=self.access_token_a
            )
            self.helper.invite(
                room_id, self.user_a, self.user_c, tok=self.access_token_a
            )
            self.helper.invite(
                room_id, self.user_a, self.user_d, tok=self.access_token_a
            )

        self.helper.join(
            room_id,
            self.user_b,
            expect_code=HTTPStatus.OK if use_invites else HTTPStatus.FORBIDDEN,
            tok=self.access_token_b,
        )
        self.helper.join(
            room_id,
            self.user_c,
            expect_code=HTTPStatus.OK if use_invites else HTTPStatus.FORBIDDEN,
            tok=self.access_token_c,
        )
        self.helper.join(
            room_id,
            self.user_d,
            expect_code=HTTPStatus.OK if use_invites else HTTPStatus.FORBIDDEN,
            tok=self.access_token_d,
        )
