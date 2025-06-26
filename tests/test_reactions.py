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

from synapse.api.constants import EventTypes, RelationTypes
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import FederatingModuleApiTestCase


class ReactionLimitationTestCase(FederatingModuleApiTestCase):
    """
    Test that m.reactions can be rejected or allowed per gematik spec
    """

    # By default, we are SERVER_NAME_FROM_LIST
    # server_name_for_this_server = "tim.test.gematik.de"
    # This test case will model being an PRO server on the federation list

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)

        self.user_a = self.register_user("a", "password")
        self.login("a", "password")

    def test_single_reaction(self) -> None:
        room_id = self.create_local_room(self.user_a, [], False)
        assert room_id is not None
        message_body = self.helper.send(
            room_id, "message", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_body.get("event_id"),
                    "key": "H",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.OK,
        )

    def test_multiple_reactions(self) -> None:
        room_id = self.create_local_room(self.user_a, [], False)
        assert room_id is not None
        message_body = self.helper.send(
            room_id, "message", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_body.get("event_id"),
                    "key": "DH",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.FORBIDDEN,
        )
