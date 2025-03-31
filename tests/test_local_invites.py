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
from http import HTTPStatus
from typing import Any

from parameterized import parameterized
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from synapse_invite_checker.types import PermissionConfig, PermissionDefaultSetting
from tests.base import FederatingModuleApiTestCase
from tests.test_utils import INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL


class LocalProModeInviteTest(FederatingModuleApiTestCase):
    """
    These PRO server tests are for invites that happen after the room creation process
    has completed
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.user_b = self.register_user("b", "password")
        self.user_c = self.register_user("c", "password")
        self.user_d = self.register_user("d", "password")

        self.access_token = self.login("a", "password")
        self.login("b", "password")
        self.login("c", "password")
        self.login("d", "password")

    @parameterized.expand(
        [
            (
                "allow_all_public",
                PermissionDefaultSetting.ALLOW_ALL,
                True,
                HTTPStatus.OK,
            ),
            (
                "allow_all_private",
                PermissionDefaultSetting.ALLOW_ALL,
                False,
                HTTPStatus.OK,
            ),
            (
                "block_all_public",
                PermissionDefaultSetting.BLOCK_ALL,
                True,
                HTTPStatus.FORBIDDEN,
            ),
            (
                "block_all_private",
                PermissionDefaultSetting.BLOCK_ALL,
                False,
                HTTPStatus.FORBIDDEN,
            ),
        ]
    )
    def test_global_permissions(
        self,
        label: str,
        default_setting: PermissionDefaultSetting,
        is_public: bool,
        expected_result: int,
    ) -> None:
        room_id = self.create_local_room(
            self.user_b,
            [],
            is_public=is_public,
        )
        assert room_id is not None, "Room should have been created"

        # Set the perms
        self.set_permissions_for_user(
            self.user_a,
            PermissionConfig(defaultSetting=default_setting),
        )

        # invite the test user to the other users room
        self.helper.invite(
            room_id,
            self.user_b,
            self.user_a,
            expect_code=expected_result,
            tok=self.map_user_id_to_token[self.user_b],
        )

    @parameterized.expand(
        [
            (
                "allow_all_public",
                PermissionDefaultSetting.ALLOW_ALL,
                True,
                HTTPStatus.FORBIDDEN,
            ),
            (
                "allow_all_private",
                PermissionDefaultSetting.ALLOW_ALL,
                False,
                HTTPStatus.FORBIDDEN,
            ),
            (
                "block_all_public",
                PermissionDefaultSetting.BLOCK_ALL,
                True,
                HTTPStatus.OK,
            ),
            (
                "block_all_private",
                PermissionDefaultSetting.BLOCK_ALL,
                False,
                HTTPStatus.OK,
            ),
        ]
    )
    def test_server_exceptions(
        self,
        label: str,
        default_setting: PermissionDefaultSetting,
        is_public: bool,
        expected_result: int,
    ) -> None:
        room_id = self.create_local_room(
            self.user_b,
            [],
            is_public=is_public,
        )
        assert room_id is not None, "Room should have been created"

        # Set the perms
        self.set_permissions_for_user(
            self.user_a,
            PermissionConfig(
                defaultSetting=default_setting,
                serverExceptions={self.server_name_for_this_server: {}},
            ),
        )

        # invite the test user to the other users room
        self.helper.invite(
            room_id,
            self.user_b,
            self.user_a,
            expect_code=expected_result,
            tok=self.map_user_id_to_token[self.user_b],
        )

    @parameterized.expand(
        [
            (
                "allow_all_public",  # just a label for test output, ignore
                PermissionDefaultSetting.ALLOW_ALL,  # the global default
                True,  # if the room is public
                # if the expected result should succeed, we use the invert to
                # test the opposite case on the same test run
                # (if "b" would succeed, "c" should fail)
                False,
            ),
            (
                "allow_all_private",
                PermissionDefaultSetting.ALLOW_ALL,
                False,
                False,
            ),
            (
                "block_all_public",
                PermissionDefaultSetting.BLOCK_ALL,
                True,
                True,
            ),
            (
                "block_all_private",
                PermissionDefaultSetting.BLOCK_ALL,
                False,
                True,
            ),
        ]
    )
    def test_user_exceptions(
        self,
        label: str,
        default_setting: PermissionDefaultSetting,
        is_public: bool,
        expected_result: bool,
    ) -> None:
        # Our test user "a" will be invited to two different rooms, one from user "b"
        # and one from user "c". Since we will have a global default permission that
        # differs, and we are testing userExceptions, the results should be opposite of
        # each other.
        user_exceptions = {self.user_b: {}}

        user_b_expectation = HTTPStatus.OK if expected_result else HTTPStatus.FORBIDDEN
        user_c_expectation = HTTPStatus.FORBIDDEN if expected_result else HTTPStatus.OK
        # Set the perms. By setting them before the invite takes place, it should
        # prevent cross-contamination between other test runs
        self.set_permissions_for_user(
            self.user_a,
            PermissionConfig(
                defaultSetting=default_setting,
                userExceptions=user_exceptions,
            ),
        )

        room_b = self.create_local_room(
            self.user_b,
            [],
            is_public=is_public,
        )
        assert room_b is not None, "Room should have been created"

        # invite the test user to the users rooms that has permission
        self.helper.invite(
            room_b,
            self.user_b,
            self.user_a,
            expect_code=user_b_expectation,
            tok=self.map_user_id_to_token[self.user_b],
        )
        room_c = self.create_local_room(
            self.user_c,
            [],
            is_public=is_public,
        )
        assert room_c is not None, "Room should have been created"

        # invite the test user to the user room that doesn't have permissions
        self.helper.invite(
            room_c,
            self.user_c,
            self.user_a,
            expect_code=user_c_expectation,
            tok=self.map_user_id_to_token[self.user_c],
        )

    def test_invite_to_dm(self) -> None:
        """Tests that a dm with a local user can be created, but nobody else invited"""
        room_id = self.create_local_room(self.user_a, [], is_public=False)
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
        room_id = self.create_local_room(self.user_a, [], is_public=False)
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
        room_id = self.create_local_room(self.user_a, [], is_public=False)
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


class LocalEpaModeInviteTest(FederatingModuleApiTestCase):
    """
    These EPA server tests are for invites that happen after the room creation process
    has completed
    """

    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_d = self.register_user("d", "password")
        self.user_e = self.register_user("e", "password")
        self.user_f = self.register_user("f", "password")
        self.access_token = self.login("d", "password")
        self.login("e", "password")
        self.login("f", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        return conf

    @parameterized.expand(
        [
            (
                "allow_all_private",
                PermissionDefaultSetting.ALLOW_ALL,
                HTTPStatus.FORBIDDEN,
            ),
            (
                "block_all_private",
                PermissionDefaultSetting.BLOCK_ALL,
                HTTPStatus.FORBIDDEN,
            ),
        ]
    )
    def test_global_permissions(
        self,
        label: str,
        default_setting: PermissionDefaultSetting,
        expected_result: int,
    ) -> None:
        room_id = self.create_local_room(
            self.user_e,
            [],
            is_public=False,
        )
        assert room_id is not None, "Room should have been created"

        # Set the perms
        self.set_permissions_for_user(
            self.user_d,
            PermissionConfig(defaultSetting=default_setting),
        )

        # invite the test user to the other users room
        self.helper.invite(
            room_id,
            self.user_e,
            self.user_d,
            expect_code=expected_result,
            tok=self.map_user_id_to_token[self.user_e],
        )

    @parameterized.expand(
        [
            (
                "allow_all_private",
                PermissionDefaultSetting.ALLOW_ALL,
                HTTPStatus.FORBIDDEN,
            ),
            (
                "block_all_private",
                PermissionDefaultSetting.BLOCK_ALL,
                HTTPStatus.FORBIDDEN,
            ),
        ]
    )
    def test_server_exceptions(
        self,
        label: str,
        default_setting: PermissionDefaultSetting,
        expected_result: int,
    ) -> None:
        room_id = self.create_local_room(
            self.user_e,
            [],
            is_public=False,
        )
        assert room_id is not None, "Room should have been created"

        # Set the perms
        self.set_permissions_for_user(
            self.user_d,
            PermissionConfig(
                defaultSetting=default_setting,
                serverExceptions={self.server_name_for_this_server: {}},
            ),
        )

        # invite the test user to the other users room
        self.helper.invite(
            room_id,
            self.user_e,
            self.user_d,
            expect_code=expected_result,
            tok=self.map_user_id_to_token[self.user_e],
        )

    @parameterized.expand(
        [
            (
                "allow_all_private",  # just a label for test output, ignore
                PermissionDefaultSetting.ALLOW_ALL,  # the global default
                HTTPStatus.FORBIDDEN,  # the expected return code
            ),
            (
                "block_all_private",
                PermissionDefaultSetting.BLOCK_ALL,
                HTTPStatus.FORBIDDEN,
            ),
        ]
    )
    def test_user_exceptions(
        self,
        label: str,
        default_setting: PermissionDefaultSetting,
        expected_result: int,
    ) -> None:
        # Our test user "d" will be invited to two different rooms, one from user "e"
        # and one from user "f". For an EPA server, this shouldn't matter as any local
        # invites are denied
        user_exceptions = {self.user_e: {}}

        # Set the perms. By setting them before the invite takes place, it should
        # prevent cross-contamination between other test runs
        self.set_permissions_for_user(
            self.user_d,
            PermissionConfig(
                defaultSetting=default_setting,
                userExceptions=user_exceptions,
            ),
        )

        room_e = self.create_local_room(
            self.user_e,
            [],
            is_public=False,
        )
        assert room_e is not None, "Room should have been created"

        # invite the test user to the users rooms that has permission
        self.helper.invite(
            room_e,
            self.user_e,
            self.user_d,
            expect_code=expected_result,
            tok=self.map_user_id_to_token[self.user_e],
        )
        room_f = self.create_local_room(
            self.user_f,
            [],
            is_public=False,
        )
        assert room_f is not None, "Room should have been created"

        # invite the test user to the user room that doesn't have permissions
        self.helper.invite(
            room_f,
            self.user_f,
            self.user_d,
            expect_code=expected_result,
            tok=self.map_user_id_to_token[self.user_f],
        )

    def test_invite_to_dm_post_room_creation(self) -> None:
        """Tests that a private room as a dm will deny inviting any local users"""
        room_id = self.create_local_room(self.user_d, [], is_public=False)
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
        room_id = self.create_local_room(self.user_d, [], is_public=False)
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
        room_id = self.create_local_room(self.user_d, [], is_public=False)
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


class DisabledDMCheckInviteTest(FederatingModuleApiTestCase):
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
        room_id = self.create_local_room(self.user_a, [], is_public=False)
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
