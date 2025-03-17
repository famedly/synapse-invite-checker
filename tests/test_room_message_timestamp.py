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

from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import ModuleApiTestCase

logger = logging.getLogger(__name__)


class MessageTimestampTestCase(ModuleApiTestCase):
    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        #  @a:test is a practitioner
        #  @b:test is an organization
        #  @c:test is an 'orgPract'
        self.user_a = self.register_user("a", "password")
        self.access_token_a = self.login("a", "password")
        self.user_b = self.register_user("b", "password")
        self.access_token_b = self.login("b", "password")
        self.user_c = self.register_user("c", "password")

        # @d:test is none of those types of actor and should be just a 'User'. For
        # context, this could be a chatbot or an office manager
        self.user_d = self.register_user("d", "password")
        self.access_token_d = self.login("d", "password")

    def user_a_create_room(
        self,
        is_public: bool,
    ) -> str | None:
        """
        Helper to send an api request with a full set of required additional room state
        to the room creation matrix endpoint.
        """
        # Hide the assertion from create_room_as() when the error code is unexpected. It
        # makes errors for the tests less clear when all we get is the http response
        return self.helper.create_room_as(
            self.user_a,
            is_public=is_public,
            tok=self.access_token_a,
        )

    def test_can_find_last_message_timestamp(self) -> None:
        # self.hs.mockmod: InviteChecker
        # create a room, add another user
        # send a message, get the timestamp
        # send two more messages, get the timestamp
        # have other user send a message, get that timestamp
        # have other user send two more messages, and get that timestamp

        def send_message_and_assert_latest_activity(room, message, tok) -> None:
            body = self.helper.send(room, message, tok=tok)

            event_id = self.helper.get_event(room, body.get("event_id"), tok=tok)
            event_ts = event_id.get("origin_server_ts")

            ts_found = self.get_success_or_raise(
                self.hs.mockmod.get_timestamp_of_last_eligible_activity_in_room(room)
            )

            self.assertEqual(event_ts, ts_found)

        room_id = self.user_a_create_room(is_public=False)
        assert room_id, "Room created"

        self.helper.invite(room_id, targ=self.user_b, tok=self.access_token_a)
        self.helper.join(room_id, self.user_b, tok=self.access_token_b)

        send_message_and_assert_latest_activity(
            room_id, "Message 1", tok=self.access_token_a
        )
        self.helper.send(room_id, "Message 2", tok=self.access_token_a)

        send_message_and_assert_latest_activity(
            room_id, "Message 3", tok=self.access_token_a
        )

        send_message_and_assert_latest_activity(
            room_id, "Message 4", tok=self.access_token_b
        )

        self.helper.send(room_id, "Message 5", tok=self.access_token_b)

        self.helper.send(room_id, "Message 6", tok=self.access_token_b)
        self.helper.send(room_id, "Message 7", tok=self.access_token_b)
        self.helper.send(room_id, "Message 8", tok=self.access_token_b)
        self.helper.send(room_id, "Message 9", tok=self.access_token_b)
        send_message_and_assert_latest_activity(
            room_id, "Message 10", tok=self.access_token_b
        )
