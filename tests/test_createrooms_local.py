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
from parameterized import parameterized
from typing import Any

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
                self.user_a,
                is_public=is_public,
                tok=self.access_token_a,
                extra_content=construct_extra_content(self.user_a, invitee_list),
            )
        return None

    def user_b_create_room(
        self,
        invitee_list: list[str],
        is_public: bool,
    ) -> str | None:
        """
        Same as `user_a_create_room()` except for user_b
        """
        with contextlib.suppress(AssertionError):
            return self.helper.create_room_as(
                self.user_b,
                is_public=is_public,
                tok=self.access_token_b,
                extra_content=construct_extra_content(self.user_b, invitee_list),
            )
        return None

    def user_d_create_room(
        self,
        invitee_list: list[str],
        is_public: bool,
    ) -> str | None:
        """
        Same as `user_a_create_room()` except for user_d
        """
        with contextlib.suppress(AssertionError):
            return self.helper.create_room_as(
                self.user_d,
                is_public=is_public,
                tok=self.access_token_d,
                extra_content=construct_extra_content(self.user_d, invitee_list),
            )
        return None

    # 'label' as first parameter names the test clearly for failures
    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room(self, label: str, is_public: bool) -> None:
        """Tests room creation with a local user can be created"""
        for invitee in [
            self.user_b,
            self.user_c,
            self.user_d,
        ]:
            room_id = self.user_a_create_room(
                [invitee],
                is_public=is_public,
            )
            assert (
                room_id
            ), f"{label} room from {self.user_a} not created with invite to:[{invitee}]"
        for invitee in [
            self.user_a,
            self.user_c,
            self.user_d,
        ]:
            room_id = self.user_b_create_room(
                [invitee],
                is_public=is_public,
            )
            assert (
                room_id
            ), f"{label} room from {self.user_b} not created with invite to:[{invitee}]"
        for invitee in [
            self.user_b,
            self.user_c,
            self.user_a,
        ]:
            room_id = self.user_d_create_room(
                [invitee],
                is_public=is_public,
            )
            assert (
                room_id
            ), f"{label} room from {self.user_d} not created with invite to:[{invitee}]"

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_with_two_invites_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests that a room can NOT be created when more than one additional member is
        invited during creation
        """
        for invitee_list in [
            [self.user_b, self.user_c],
            [self.user_d, self.user_c],
        ]:
            room_id = self.user_a_create_room(
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"{label} room incorrectly created with invites to:[{invitee_list}]"


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
        self.user_d = self.register_user("d", "password")
        self.access_token = self.login("d", "password")

        self.user_e = self.register_user("e", "password")
        self.user_f = self.register_user("f", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        return conf

    def user_d_create_room(
        self,
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
                self.user_d,
                is_public=is_public,
                tok=self.access_token,
                extra_content=construct_extra_content(self.user_d, invitee_list),
            )
        return None

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_fails(self, label: str, is_public: bool) -> None:
        """Tests room creation with a local user will be denied"""
        for invitee in [
            self.user_e,
            self.user_f,
        ]:
            room_id = self.user_d_create_room(
                [invitee],
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"{label} room incorrectly created with invite to:[{invitee}]"

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_with_two_invites_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests that a room can NOT be created when more than one additional member is
        invited during creation
        """
        invitee_list = [self.user_e, self.user_f]
        room_id = self.user_d_create_room(
            invitee_list,
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"{label} room incorrectly created with invites to:[{invitee_list}]"
