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

from tests.base import FederatingModuleApiTestCase

logger = logging.getLogger(__name__)


class MessageTimestampTestCase(FederatingModuleApiTestCase):
    """
    Test to prove the last message timestamp can be obtained for room scanning purposes
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.user_b = self.register_user("b", "password")
        self.access_token_a = self.login("a", "password")
        self.access_token_b = self.login("b", "password")

    def test_can_find_last_message_timestamp(self) -> None:
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
                self.inv_checker.get_timestamp_of_last_eligible_activity_in_room(room)
            )

            self.assertEqual(event_ts, ts_found)

        room_id = self.create_local_room(self.user_a, [], is_public=False)
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
