# Copyright (C) 2020, 2024 Famedly
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
from typing import Any

from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import ModuleApiTestCase
from tests.test_utils import INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL


class LocalProModeInviteTest(ModuleApiTestCase):
    """
    These tests do not cover invites during room creation.
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        #  @a:test is a practitioner
        #  @b:test is an organization
        #  @c:test is an 'orgPract'
        self.user_a = self.register_user("a", "password")
        self.access_token = self.login("a", "password")
        self.user_b = self.register_user("b", "password")
        self.user_c = self.register_user("c", "password")

        # @d:test is none of those types of actor and should be just a 'User'. For
        # context, this could be a chatbot or an office manager
        self.user_d = self.register_user("d", "password")

        # authenticated as user_a
        self.helper.auth_user_id = self.user_a

    def test_invite_to_dm(self) -> None:
        """Tests that a dm with a local user can be created, but nobody else invited"""
        room_id = self.helper.create_room_as(
            self.user_a, is_public=False, tok=self.access_token
        )
        assert room_id, "Room not created"

        # create DM event
        channel = self.make_request(
            "PUT",
            f"/user/{self.user_a}/account_data/m.direct",
            {
                self.user_b: [room_id],
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result

        # Can't invite other users
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_c,
            tok=self.access_token,
            expect_code=403,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_d,
            tok=self.access_token,
            expect_code=403,
        )
        # But can invite the dm user
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_b,
            tok=self.access_token,
            expect_code=200,
        )

    def test_invite_to_group(self) -> None:
        """Tests that a group with local users works normally"""
        room_id = self.helper.create_room_as(
            self.user_a, is_public=False, tok=self.access_token
        )
        assert room_id, "Room not created"

        # create DM event
        channel = self.make_request(
            "PUT",
            f"/user/{self.user_a}/account_data/m.direct",
            {
                self.user_b: ["!not:existing.example.com"],
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result

        # Can invite other users
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_c,
            tok=self.access_token,
            expect_code=200,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_b,
            tok=self.access_token,
            expect_code=200,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_d,
            tok=self.access_token,
            expect_code=200,
        )

    def test_invite_to_group_without_dm_event(self) -> None:
        """Tests that a group with local users works normally in case the user has no m.direct set"""
        room_id = self.helper.create_room_as(
            self.user_a, is_public=False, tok=self.access_token
        )
        assert room_id, "Room not created"

        # Can invite other users
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_c,
            tok=self.access_token,
            expect_code=200,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_b,
            tok=self.access_token,
            expect_code=200,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_d,
            tok=self.access_token,
            expect_code=200,
        )


class LocalEpaModeInviteTest(ModuleApiTestCase):
    """
    These tests do not cover invites during room creation.

        NOTE: This should not be allowed to work. Strictly speaking, a server that is
    in 'epa' mode should always appear on the federation list as an 'isInsurance'.
    For the moment, all we do is log a warning. This will be changed in the future
    which will require assuming the identity of an insurance domain to test with.

    """

    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        # Can't use any of:
        #  @a:test is a practitioner
        #  @b:test is an organization
        #  @c:test is an 'orgPract'
        # as they should not exist on an 'ePA' mode server backend

        # 'd', 'e' and 'f' is none of those types of actor and should be just regular 'User's
        self.user_d = self.register_user("d", "password")
        self.user_e = self.register_user("e", "password")
        self.user_f = self.register_user("f", "password")
        self.access_token = self.login("d", "password")

        # authenticated as user_d
        self.helper.auth_user_id = self.user_d

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        return conf

    def test_invite_to_dm_post_room_creation(self) -> None:
        """Tests that a private room as a dm will deny inviting any local users"""
        room_id = self.helper.create_room_as(
            self.user_d, is_public=False, tok=self.access_token
        )
        assert room_id, "Room not created"

        # create DM event
        channel = self.make_request(
            "PUT",
            f"/user/{self.user_d}/account_data/m.direct",
            {
                self.user_e: [room_id],
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result

        # Can't invite other users
        self.helper.invite(
            room=room_id,
            src=self.user_d,
            targ=self.user_f,
            tok=self.access_token,
            expect_code=403,
        )

        self.helper.invite(
            room=room_id,
            src=self.user_d,
            targ=self.user_e,
            tok=self.access_token,
            expect_code=403,
        )

    def test_invite_to_group_post_room_creation(self) -> None:
        """Tests that a private room for a group will deny inviting any local users, with an unrelated m.direct tag"""
        room_id = self.helper.create_room_as(
            self.user_d, is_public=False, tok=self.access_token
        )
        assert room_id, "Room not created"

        # create DM event
        channel = self.make_request(
            "PUT",
            f"/user/{self.user_d}/account_data/m.direct",
            {
                self.user_e: ["!not:existing.example.com"],
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result

        # Can't invite other users
        self.helper.invite(
            room=room_id,
            src=self.user_d,
            targ=self.user_f,
            tok=self.access_token,
            expect_code=403,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_d,
            targ=self.user_e,
            tok=self.access_token,
            expect_code=403,
        )

    def test_invite_to_group_without_dm_event_post_room_creation(self) -> None:
        """Tests that a group with local users is denied when the user has no m.direct set"""
        room_id = self.helper.create_room_as(
            self.user_d, is_public=False, tok=self.access_token
        )
        assert room_id, "Room not created"

        # Can't invite other users
        self.helper.invite(
            room=room_id,
            src=self.user_d,
            targ=self.user_f,
            tok=self.access_token,
            expect_code=403,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_d,
            targ=self.user_e,
            tok=self.access_token,
            expect_code=403,
        )


class DisabledDMCheckInviteTest(ModuleApiTestCase):
    """
    This tests to make sure the DM check can be disabled
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.access_token = self.login("a", "password")
        self.user_b = self.register_user("b", "password")
        self.user_c = self.register_user("c", "password")
        self.user_d = self.register_user("d", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update(
            {"block_invites_into_dms": False}
        )
        return conf

    def test_invite_to_dm(self) -> None:
        """Tests that a dm with a local user can be created, and others can be invited"""
        # This just copies the test from LocalProModeInviteTest but adjusts the expect_code to 200
        room_id = self.helper.create_room_as(
            self.user_a, is_public=False, tok=self.access_token
        )
        assert room_id, "Room not created"

        # create DM event
        channel = self.make_request(
            "PUT",
            f"/user/{self.user_a}/account_data/m.direct",
            {
                self.user_b: [room_id],
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result

        # Other users can be invited
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_c,
            tok=self.access_token,
            expect_code=200,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_d,
            tok=self.access_token,
            expect_code=200,
        )
        self.helper.invite(
            room=room_id,
            src=self.user_a,
            targ=self.user_b,
            tok=self.access_token,
            expect_code=200,
        )
