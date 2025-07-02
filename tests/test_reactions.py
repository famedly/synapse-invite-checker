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
from typing import Any

from parameterized import parameterized_class
from synapse.api.constants import EventTypes, RelationTypes
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import FederatingModuleApiTestCase

logger = logging.getLogger(__name__)


@parameterized_class(
    [{"limit_reactions_enabled": True}, {"limit_reactions_enabled": False}]
)
class ReactionLimitationTestCase(FederatingModuleApiTestCase):
    """
    Test that m.reactions can be rejected or allowed per gematik spec
    """

    # By default, we are SERVER_NAME_FROM_LIST
    # server_name_for_this_server = "tim.test.gematik.de"
    # This test case will model being an PRO server on the federation list

    limit_reactions_enabled: bool

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)

        self.user_a = self.register_user("a", "password")
        self.login("a", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update(
            {
                "limit_reactions": self.limit_reactions_enabled,
            }
        )

        return conf

    def test_single_cluster_reaction(self) -> None:
        room_id = self.create_local_room(self.user_a, [], False)
        assert room_id is not None
        message_1_body = self.helper.send(
            room_id, "message 1", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_1_body.get("event_id"),
                    # single characters are not allowed
                    "key": "H",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=(
                HTTPStatus.BAD_REQUEST
                if self.limit_reactions_enabled
                else HTTPStatus.OK
            ),
        )
        message_2_body = self.helper.send(
            room_id, "message 2", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_2_body.get("event_id"),
                    # A single simple emoji is allowed
                    # \uD83D\uDC4D
                    "key": "👍",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.OK,
        )
        message_3_body = self.helper.send(
            room_id, "message 3", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_3_body.get("event_id"),
                    # A single "compound" or grapheme cluster emoji is allowed
                    # :male-technologist:
                    # \uD83D\uDC68\u200D\uD83D\uDCBB
                    # xf0x9fx91xa8xe2x80x8dxf0x9fx92xbb
                    "key": "👨‍💻",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.OK,
        )
        message_4_body = self.helper.send(
            room_id, "message 4", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_4_body.get("event_id"),
                    # A single "compound" or grapheme cluster emoji is allowed
                    # :de:
                    # \uD83C\uDDE9\uD83C\uDDEA
                    "key": "🇩🇪",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.OK,
        )
        message_5_body = self.helper.send(
            room_id, "message 5", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_5_body.get("event_id"),
                    # A single "compound" or grapheme cluster emoji is allowed
                    # :family_adult_adult_child_child:
                    # \uD83E\uDDD1\u200D\uD83E\uDDD1\u200D\uD83E\uDDD2\u200D\uD83E\uDDD2
                    "key": "🧑‍🧑‍🧒‍🧒",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=HTTPStatus.OK,
        )

    def test_empty_reaction(self) -> None:
        room_id = self.create_local_room(self.user_a, [], False)
        assert room_id is not None
        message_1_body = self.helper.send(
            room_id, "message 1", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_1_body.get("event_id"),
                    "key": "",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            # Need clarification on if this should pass or not
            expect_code=HTTPStatus.OK,
        )

    def test_multiple_cluster_reaction(self) -> None:
        room_id = self.create_local_room(self.user_a, [], False)
        assert room_id is not None
        message_1_body = self.helper.send(
            room_id, "message 1", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_1_body.get("event_id"),
                    # Words(or sentences) are not allowed
                    "key": "Hello there",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=(
                HTTPStatus.BAD_REQUEST
                if self.limit_reactions_enabled
                else HTTPStatus.OK
            ),
        )
        message_2_body = self.helper.send(
            room_id, "message 2", tok=self.map_user_id_to_token[self.user_a]
        )
        self.helper.send_event(
            room_id,
            EventTypes.Reaction,
            {
                "m.relates_to": {
                    "event_id": message_2_body.get("event_id"),
                    # Two separate emoji are not allowed(in the same reaction)
                    # :+1: and :smiley:
                    # \uD83D\uDC4D\uD83D\uDE03
                    "key": "👍😃",
                    "rel_type": RelationTypes.ANNOTATION,
                }
            },
            tok=self.map_user_id_to_token[self.user_a],
            expect_code=(
                HTTPStatus.BAD_REQUEST
                if self.limit_reactions_enabled
                else HTTPStatus.OK
            ),
        )
