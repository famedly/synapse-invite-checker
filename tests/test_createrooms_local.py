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

from parameterized import parameterized
from typing import Any

from synapse.api.constants import EventTypes, HistoryVisibility, JoinRules
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import (
    ModuleApiTestCase,
    construct_extra_content,
)
from tests.test_utils import INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL


class LocalProModeCreateRoomTest(ModuleApiTestCase):
    """
    These tests are for invites during room creation. Invites after room creation will
    be tested separately

    Each single invite test has three parts: not only room creation invites between special Users, such
    as 'pract' but also with an 'org' User, such as a nurse or a department. Also test
    Users such as 'Org-Admin' that don't have special rights
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        #  "a" is a practitioner
        #  "b" is an organization
        #  "c" is an 'orgPract'
        self.pro_user_a = self.register_user("a", "password")
        self.access_token_a = self.login("a", "password")
        self.pro_user_b = self.register_user("b", "password")
        self.access_token_b = self.login("b", "password")
        self.pro_user_c = self.register_user("c", "password")

        # "d" is none of those types of actor and should be just a 'User'. For
        # context, this could be a chatbot or an office manager
        self.pro_user_d = self.register_user("d", "password")
        self.access_token_d = self.login("d", "password")

        self.map_user_id_to_token = {
            self.pro_user_a: self.access_token_a,
            self.pro_user_b: self.access_token_b,
            self.pro_user_d: self.access_token_d,
        }

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        conf["server_notices"] = {"system_mxid_localpart": "server", "auto_join": True}
        return conf

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
                tok=self.map_user_id_to_token[creating_user],
                extra_content=construct_extra_content(creating_user, invitee_list),
            )
        return None

    # 'label' as first parameter names the test clearly for failures
    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room(self, label: str, is_public: bool) -> None:
        """Tests room creation with a local user can be created"""
        for invitee in [
            self.pro_user_b,
            self.pro_user_c,
            self.pro_user_d,
        ]:
            room_id = self.user_create_room(
                self.pro_user_a,
                [invitee],
                is_public=is_public,
            )
            assert (
                room_id
            ), f"{label} room from {self.pro_user_a} should be created with invite to: {invitee}"
        for invitee in [
            self.pro_user_a,
            self.pro_user_c,
            self.pro_user_d,
        ]:
            room_id = self.user_create_room(
                self.pro_user_b,
                [invitee],
                is_public=is_public,
            )
            assert (
                room_id
            ), f"{label} room from {self.pro_user_b} should be created with invite to: {invitee}"
        for invitee in [
            self.pro_user_b,
            self.pro_user_c,
            self.pro_user_a,
        ]:
            room_id = self.user_create_room(
                self.pro_user_d,
                [invitee],
                is_public=is_public,
            )
            assert (
                room_id
            ), f"{label} room from {self.pro_user_d} should be created with invite to: {invitee}"

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_with_two_invites_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests that a room can NOT be created when more than one additional member is
        invited during creation
        """
        for invitee_list in [
            [self.pro_user_b, self.pro_user_c],
            [self.pro_user_d, self.pro_user_c],
        ]:
            room_id = self.user_create_room(
                self.pro_user_a,
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"{label} room should not be created with invites to: {invitee_list}"

    def test_create_server_notices_room(self) -> None:
        """
        Test that a server notices room works as expected on pro mode servers
        """
        # send_notice() will automatically create a server notices room and then invite
        # the user it is directed towards. The server notices manager has no method to
        # invite a user during creation of the room
        room_id = self.get_success_or_raise(
            self.hs.get_server_notices_manager().send_notice(
                self.pro_user_d, {"body": "Server Notice message", "msgtype": "m.text"}
            )
        )
        # Retrieving the room_id is a sign that the room was created, the user was
        # invited, and the message was sent
        assert room_id, "Server notices room should have been found"

    @parameterized.expand([("private", False), ("public", True)])
    def test_create_room_then_modify_join_rules(
        self, label: str, is_public: bool
    ) -> None:
        """
        Test that a misbehaving client can not accidentally make their room public after
        the room was created
        """
        room_id = self.user_create_room(self.pro_user_a, [], is_public=is_public)
        assert room_id, f"{label} room should be created"
        # This should be ALLOWED for an already public room, it's silly but is idempotent
        self.helper.send_state(
            room_id,
            EventTypes.JoinRules,
            {"join_rule": JoinRules.PUBLIC},
            tok=self.access_token_a,
            expect_code=HTTPStatus.OK if is_public else HTTPStatus.FORBIDDEN,
        )

    @parameterized.expand([("private", False), ("public", True)])
    def test_create_room_then_modify_history_visibility(
        self, label: str, is_public: bool
    ) -> None:
        """
        Test that a misbehaving client can not accidentally make their room visible
        after the room was created
        """
        room_id = self.user_create_room(self.pro_user_a, [], is_public=is_public)
        assert room_id, f"{label} room should be created"
        # This should be FORBIDDEN for any room
        self.helper.send_state(
            room_id,
            EventTypes.RoomHistoryVisibility,
            {"history_visibility": HistoryVisibility.WORLD_READABLE},
            tok=self.access_token_a,
            expect_code=HTTPStatus.FORBIDDEN,
        )


class LocalEpaModeCreateRoomTest(ModuleApiTestCase):
    """
    These tests are for invites during room creation. Invites after room creation will
    be tested separately

    ePA mode configurations should never have 'pract', 'org' or 'orgPract' Users, so
    they are not included in these tests
    """

    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.epa_user_d = self.register_user("d", "password")
        self.access_token = self.login("d", "password")

        self.epa_user_e = self.register_user("e", "password")
        self.epa_user_f = self.register_user("f", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        conf["server_notices"] = {"system_mxid_localpart": "server", "auto_join": True}
        return conf

    def user_d_create_room(
        self,
        invitee_list: list[str],
        is_public: bool,
        custom_initial_state: dict[str, Any] | None = None,
    ) -> str | None:
        """
        Helper to send an api request with a full set of required additional room state
        to the room creation matrix endpoint.
        """
        # Hide the assertion from create_room_as() when the error code is unexpected. It
        # makes errors for the tests less clear when all we get is the http response
        with contextlib.suppress(AssertionError):
            return self.helper.create_room_as(
                self.epa_user_d,
                is_public=is_public,
                tok=self.access_token,
                extra_content=custom_initial_state
                or construct_extra_content(self.epa_user_d, invitee_list),
            )
        return None

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_fails(self, label: str, is_public: bool) -> None:
        """Tests room creation with a local user will be denied"""
        for invitee in [
            self.epa_user_e,
            self.epa_user_f,
        ]:
            room_id = self.user_d_create_room(
                [invitee],
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"{label} room should not be created with invite to: {invitee}"

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_with_two_invites_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests that a room can NOT be created when more than one additional member is
        invited during creation
        """
        invitee_list = [self.epa_user_e, self.epa_user_f]
        room_id = self.user_d_create_room(
            invitee_list,
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"{label} room should not be created with invites to: {invitee_list}"

    def test_create_room_with_modified_join_rules(self) -> None:
        """
        Test that a misbehaving insurance client can not accidentally make their room public
        """
        join_rule = {
            "type": "m.room.join_rules",
            "state_key": "",
            "content": {"join_rule": "public"},
        }
        initial_state = {"initial_state": [join_rule]}

        room_id = self.user_d_create_room(
            [], is_public=False, custom_initial_state=initial_state
        )
        # Without the blocking put in place, this fails for private rooms
        assert room_id is None, "Private room should NOT have been created"

    def test_create_room_with_modified_history_visibility(self) -> None:
        """
        Test that a misbehaving insurance client can not accidentally make their room visible
        """
        history_visibility = {
            "type": EventTypes.RoomHistoryVisibility,
            "state_key": "",
            "content": {"history_visibility": HistoryVisibility.WORLD_READABLE},
        }
        initial_state = {"initial_state": [history_visibility]}

        room_id = self.user_d_create_room(
            [], is_public=False, custom_initial_state=initial_state
        )
        # Without the blocking put in place, this fails for private rooms
        assert room_id is None, "Private room should NOT have been created"

    def test_create_room_then_modify_join_rules(self) -> None:
        """
        Test that a misbehaving insurance client can not accidentally make their room
        public after room was created
        """
        room_id = self.user_d_create_room([], is_public=False)
        assert room_id, "Private room should be created"
        # This should be FORBIDDEN
        self.helper.send_state(
            room_id,
            EventTypes.JoinRules,
            {"join_rule": JoinRules.PUBLIC},
            tok=self.access_token,
            expect_code=HTTPStatus.FORBIDDEN,
        )

    def test_create_room_then_modify_history_visibility(self) -> None:
        """
        Test that a misbehaving insurance client can not accidentally make their room
        public after room was created
        """
        room_id = self.user_d_create_room([], is_public=False)
        assert room_id, "Private room should be created"
        # This should be FORBIDDEN
        self.helper.send_state(
            room_id,
            EventTypes.RoomHistoryVisibility,
            {"history_visibility": HistoryVisibility.WORLD_READABLE},
            tok=self.access_token,
            expect_code=HTTPStatus.FORBIDDEN,
        )

    def test_create_server_notices_room(self) -> None:
        """
        Test that a server notices room ignores epa restriction rules. This is important
        because server notice rooms are created by a "fake" user on the local server and
        inviting another local server user is supposed to be forbidden. The server
        notice user is considered a system admin account and is therefor exempt from
        this restriction
        """
        # send_notice() will automatically create a server notices room and then invite
        # the user it is directed towards. The server notices manager has no method to
        # invite a user during creation of the room
        room_id = self.get_success_or_raise(
            self.hs.get_server_notices_manager().send_notice(
                self.epa_user_d, {"body": "Server Notice message", "msgtype": "m.text"}
            )
        )
        # Retrieving the room_id is a sign that the room was created, the user was
        # invited, and the message was sent
        assert room_id, "Server notices room should have been found"
