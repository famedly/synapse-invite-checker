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
from typing_extensions import override
from unittest.mock import AsyncMock, Mock

from parameterized import parameterized
from synapse.api.errors import SynapseError
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from synapse_invite_checker import InviteChecker
from synapse_invite_checker.types import PermissionDefaultSetting
from tests.base import (
    FederatingModuleApiTestCase,
    construct_extra_content,
)
from tests.test_utils import DOMAIN_IN_LIST, INSURANCE_DOMAIN_IN_LIST


logger = logging.getLogger(__name__)


class IncomingRemoteJoinTestCase(FederatingModuleApiTestCase):
    # server_name_for_this_server = "tim.test.gematik.de"
    # This test case will model being an PRO server on the federation list
    # By default we are SERVER_NAME_FROM_LIST

    # Test with one other remote PRO server and one EPA server
    # The inactive grace period is going to be 6 hours, room scans run each hour
    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    # The default "fake" remote server name that has its server signing keys auto-injected
    OTHER_SERVER_NAME = DOMAIN_IN_LIST

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

        self.inv_checker: InviteChecker = self.hs.mockmod

        # Bump user "d" to 'allow all'
        permissions = self.get_success_or_raise(
            self.inv_checker.permissions_handler.get_permissions(self.user_d)
        )
        permissions.defaultSetting = PermissionDefaultSetting.ALLOW_ALL
        self.get_success_or_raise(
            self.inv_checker.permissions_handler.update_permissions(
                self.user_d, permissions
            )
        )

        # OTHER_SERVER_NAME already has it's signing key injected into our database so
        # our server doesn't have to make that request. Add the other servers we will be
        # using as well
        self.map_server_name_to_signing_key.update(
            {
                INSURANCE_DOMAIN_IN_LIST: self.inject_servers_signing_key(
                    INSURANCE_DOMAIN_IN_LIST
                ),
            },
        )

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

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_epa_no_invites(self, _: str, is_public: bool) -> None:
        """
        Test with no invites behavior for public and private rooms when there is an
        incoming remote user
        """
        room_id = self.user_create_room(self.user_a, [], is_public=False)

        # public should not succeed
        # private should also not succeed
        # Since no invites occurred, we never get past make_join
        self.send_join(
            self.remote_epa_user,
            room_id,
            make_expected_code=HTTPStatus.FORBIDDEN,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_epa_with_invites(self, _: str, is_public: bool) -> None:
        """
        Test with invites behavior for public and private rooms when there is an
        incoming remote user
        """
        if is_public:
            self.skipTest(
                "No API hook to deny [outgoing invite|incoming join] based only on join_rule/public-ness"
            )
        room_id = self.user_create_room(self.user_a, [], is_public=False)

        # Test first with user 'a' who is using permission of 'block all'
        # for a public room this should fail
        # for a private room this will fail because permissions
        self.helper.invite(
            room_id,
            self.user_a,
            self.remote_epa_user,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_a,
        )

        # public room should be forbidden
        # private room should be forbidden, because invite was denied
        self.send_join(
            self.remote_epa_user,
            room_id,
            make_expected_code=HTTPStatus.FORBIDDEN,
            join_expected_code=HTTPStatus.FORBIDDEN,
        )

        # Make a fresh room
        room_id = self.user_create_room(self.user_d, [], is_public=False)

        # Then test with user 'd' who is using permission of 'allow all'
        # for a public room this should fail
        # for a private room this should succeed because user 'd' has permission of 'allow all'
        self.helper.invite(
            room_id,
            self.user_d,
            self.remote_epa_user,
            expect_code=HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK,
            tok=self.access_token_d,
        )

        # public room should be forbidden
        # private room should be allowed, because invite
        self.send_join(
            self.remote_epa_user,
            room_id,
            make_expected_code=HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK,
            join_expected_code=HTTPStatus.OK,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_pro_no_invites(self, _: str, is_public: bool) -> None:
        """
        Test with no invites behavior for public and private rooms when there is an
        incoming remote user
        """
        room_id = self.user_create_room(self.user_a, [], is_public=False)

        # public should not succeed
        # private should also not succeed
        # Since no invites occurred, we never get past make_join
        self.send_join(
            self.remote_pro_user,
            room_id,
            make_expected_code=HTTPStatus.FORBIDDEN,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_pro_with_invites_block_all(
        self, _: str, is_public: bool
    ) -> None:
        """
        Test with invites behavior for public and private rooms when there is an
        incoming remote user
        """
        if is_public:
            self.skipTest(
                "No API hook to deny incoming remote join based only on join_rule/public-ness"
            )
        room_id = self.user_create_room(self.user_a, [], is_public=False)

        # for both private and public rooms this should succeed(both users are 'pract')
        # TODO: try with a user that is not 'pract' and not visible
        self.helper.invite(
            room_id,
            self.user_a,
            self.remote_pro_user,
            expect_code=HTTPStatus.OK,
            tok=self.access_token_a,
        )

        # make_join should always succeed, as the invite will not be blocked
        # send_join should only succeed for private rooms
        self.send_join(
            self.remote_pro_user,
            room_id,
            make_expected_code=HTTPStatus.OK,
            join_expected_code=HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_pro_with_invites_allow_all(
        self, _: str, is_public: bool
    ) -> None:
        """
        Test with invites behavior for public and private rooms when there is an
        incoming remote user
        """
        if is_public:
            self.skipTest(
                "No API hook to deny incoming remote join based only on join_rule/public-ness"
            )
        room_id = self.user_create_room(self.user_d, [], is_public=False)

        # for both private and public rooms this should succeed(both users are 'pract')
        self.helper.invite(
            room_id,
            self.user_d,
            self.remote_pro_user,
            expect_code=HTTPStatus.OK,
            tok=self.access_token_d,
        )

        # make_join should always succeed, as the invite will not be blocked
        # send_join should only succeed for private rooms
        self.send_join(
            self.remote_pro_user,
            room_id,
            make_expected_code=HTTPStatus.OK,
            join_expected_code=HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK,
        )


class OutgoingRemoteJoinTestCase(FederatingModuleApiTestCase):
    # server_name_for_this_server = "tim.test.gematik.de"
    # This test case will model being an PRO server on the federation list
    # By default we are SERVER_NAME_FROM_LIST

    # Test with one other remote PRO server and one EPA server
    # The inactive grace period is going to be 6 hours, room scans run each hour
    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    # The default "fake" remote server name that has its server signing keys auto-injected
    OTHER_SERVER_NAME = DOMAIN_IN_LIST

    @override
    def make_homeserver(self, reactor: MemoryReactor, clock: Clock) -> HomeServer:
        # Mock out the calls over federation.
        self.fed_transport_client = Mock(spec=["send_transaction"])
        self.fed_transport_client.send_transaction = AsyncMock(return_value={})

        hs = self.setup_test_homeserver(
            # Masquerade as a domain found on the federation list, then we can pass
            # tests that verify that fact
            self.server_name_for_this_server,
            federation_transport_client=self.fed_transport_client,
            # federation_handler=self.fed_handler,
        )
        # Hijack the federation invitation infrastructure in the handler so do not have
        # to do things like check signature validation and event structure. Do this
        # after initialization so the rest of the federation handler infrastructure is
        # intact
        # hs.get_federation_handler().send_invite = AsyncMock(
        #     return_value=FakeInviteResponse()
        # )
        return hs

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

        self.inv_checker: InviteChecker = self.hs.mockmod

        # Bump user "d" to 'allow all'
        permissions = self.get_success_or_raise(
            self.inv_checker.permissions_handler.get_permissions(self.user_d)
        )
        permissions.defaultSetting = PermissionDefaultSetting.ALLOW_ALL
        self.get_success_or_raise(
            self.inv_checker.permissions_handler.update_permissions(
                self.user_d, permissions
            )
        )

        # OTHER_SERVER_NAME already has it's signing key injected into our database so
        # our server doesn't have to make that request. Add the other servers we will be
        # using as well
        self.map_server_name_to_signing_key.update(
            {
                INSURANCE_DOMAIN_IN_LIST: self.inject_servers_signing_key(
                    INSURANCE_DOMAIN_IN_LIST
                ),
            },
        )

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

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_pro_no_invites(self, _: str, is_public: bool) -> None:
        """
        Test that the local server can successfully join a remote room, including a full
        send join response
        """
        remote_room_id = self.create_remote_room(self.remote_pro_user, "10", is_public)
        assert remote_room_id is not None

        # Public rooms should fail. Private rooms should also fail because no invite
        self.assertRaises(
            SynapseError, self.do_remote_join, remote_room_id, self.user_a
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_pro_with_invites(self, _: str, is_public: bool) -> None:
        """
        Test that the local server can successfully join a remote room, including a full
        send join response
        """
        if is_public:
            self.skipTest("No API hook to determine state before join")
        remote_room_id = self.create_remote_room(self.remote_pro_user, "10", is_public)
        assert remote_room_id is not None

        # This should be enough to inject the "fact" we got an invite, and should
        # allow private room joining. Both users are 'pract'
        self.do_remote_invite(self.user_a, self.remote_pro_user, remote_room_id)

        # Public rooms should fail. Private rooms should succeed, but only because of
        # the invite
        if is_public:
            self.assertRaises(
                SynapseError, self.do_remote_join, remote_room_id, self.user_a
            )
        else:
            self.do_remote_join(remote_room_id, self.user_a)

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_epa_no_invites(self, _: str, is_public: bool) -> None:
        """
        Test that the local server can successfully join a remote room, including a full
        send join response
        """
        remote_room_id = self.create_remote_room(self.remote_epa_user, "10", is_public)
        assert remote_room_id is not None

        # In both cases, this raises. Neither private nor public rooms are allowed.
        # Public, because they are denied without invites, and private because the
        # invite failed above
        self.assertRaises(
            SynapseError, self.do_remote_join, remote_room_id, self.user_a
        )

        # This is messy, but I don't have a better way yet to reflect a denied invite/join
        # in the fake room. So for now, just toss it
        self.remote_rooms[remote_room_id].map_of_membership_by_mxid.pop(self.user_a)

        # Public rooms should fail. Private rooms should also fail because no invite
        self.assertRaises(
            SynapseError, self.do_remote_join, remote_room_id, self.user_d
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_epa_with_invites(self, _: str, is_public: bool) -> None:
        """
        Test that the local server can successfully join a remote room, including a full
        send join response
        """
        if is_public:
            self.skipTest("No API hook to determine state before join")

        remote_room_id = self.create_remote_room(self.remote_epa_user, "10", is_public)
        assert remote_room_id is not None

        # Use user 'a' first

        # This should be enough to inject the "fact" we got an invite, and should
        # allow private room joining. However, user "a" has 'block all' permissions so
        # the invite should always fail
        self.do_remote_invite(
            self.user_a,
            self.remote_epa_user,
            remote_room_id,
            expect_code=HTTPStatus.FORBIDDEN,
        )

        # In both cases, this raises. Neither private nor public rooms are allowed.
        # Public, because they are denied without invites, and private because the
        # invite failed above
        self.assertRaises(
            SynapseError, self.do_remote_join, remote_room_id, self.user_a
        )

        # This is messy, but I don't have a better way yet to reflect a denied invite/join
        # in the fake room. So for now, just toss it
        self.remote_rooms[remote_room_id].map_of_membership_by_mxid.pop(self.user_a)

        # Try again with user 'd', who has 'allow all' as their permission

        # This should be enough to inject the "fact" we got an invite, and should
        # allow private room joining.
        self.do_remote_invite(
            self.user_d,
            self.remote_epa_user,
            remote_room_id,
            expect_code=HTTPStatus.OK,
        )

        # Public rooms should fail. Private rooms should succeed, but only because of
        # the invite
        if is_public:
            self.assertRaises(
                SynapseError, self.do_remote_join, remote_room_id, self.user_d
            )
        else:
            self.do_remote_join(remote_room_id, self.user_d)
