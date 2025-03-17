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
from unittest.mock import AsyncMock, Mock

from parameterized import parameterized
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor
from typing_extensions import override

from synapse_invite_checker import InviteChecker
from synapse_invite_checker.types import PermissionConfig, PermissionDefaultSetting
from tests.base import (
    FederatingModuleApiTestCase,
    construct_extra_content,
)
from tests.test_utils import DOMAIN_IN_LIST, INSURANCE_DOMAIN_IN_LIST

logger = logging.getLogger(__name__)


class IncomingRemoteJoinTestCase(FederatingModuleApiTestCase):
    """
    Test incoming remote joins(from federation) behave as expected.
    Unlike tests in test_createrooms_remote.py, these have rooms created with no invites
    """

    # By default, we are SERVER_NAME_FROM_LIST
    # server_name_for_this_server = "tim.test.gematik.de"
    # This test case will model being an PRO server on the federation list

    # Test with two remote PRO user(one hba and one unlisted) and one EPA user
    remote_hba_user = f"@mxid:{DOMAIN_IN_LIST}"
    # remote_pro_user = f"unlisted:{DOMAIN_IN_LIST}"
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

    def user_create_room(
        self,
        creating_user: str,
        invitee_list: list[str],
        is_public: bool,
        expected_code: int = HTTPStatus.OK,
    ) -> str | None:
        """
        Helper to send an api request with a full set of required additional room state
        to the room creation matrix endpoint.
        """
        return self.helper.create_room_as(
            creating_user,
            is_public=is_public,
            tok=self.user_id_to_token.get(creating_user),
            expect_code=expected_code,
            extra_content=construct_extra_content(creating_user, invitee_list),
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_epa_no_invites(self, _: str, is_public: bool) -> None:
        """
        Test _with no invites_ behavior for public and private rooms when there is an
        incoming remote user
        """
        room_id = self.user_create_room(self.user_a, [], is_public=is_public)
        assert room_id is not None, "Room should have been created"

        # public should not succeed
        # private should also not succeed
        # Since no invites occurred, we never get past make_join
        self.send_join(
            self.remote_epa_user,
            room_id,
            make_join_expected_code=HTTPStatus.FORBIDDEN,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_epa_with_invites(self, _: str, is_public: bool) -> None:
        """
        Test _with invites_ behavior for public and private rooms when there is an
        incoming remote user
        """
        # Try with user "d", make a fresh room
        room_id = self.user_create_room(self.user_d, [], is_public=is_public)
        assert room_id is not None, "Room should have been created"

        # for a public room this should fail
        # for a private room this should succeed
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
            make_join_expected_code=(
                HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK
            ),
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_pro_no_invites(self, _: str, is_public: bool) -> None:
        """
        Test with no invites behavior for public and private rooms when there is an
        incoming remote user
        """
        room_id = self.user_create_room(self.user_a, [], is_public=is_public)
        assert room_id is not None, "Room should have been created"

        # public should not succeed
        # private should also not succeed
        # Since no invites occurred, we never get past make_join
        self.send_join(
            self.remote_hba_user,
            room_id,
            make_join_expected_code=HTTPStatus.FORBIDDEN,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_pro_with_invites_pract_visibility(
        self, _: str, is_public: bool
    ) -> None:
        """
        Test with invites behavior for public and private rooms when there is an
        incoming remote user
        """
        room_id = self.user_create_room(self.user_a, [], is_public=is_public)
        assert room_id is not None, "Room should have been created"

        # Private rooms, this should be allowed without permission
        # Public rooms, should be denied because public room
        # Note: both users are 'pract'
        self.helper.invite(
            room_id,
            self.user_a,
            self.remote_hba_user,
            expect_code=HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK,
            tok=self.access_token_a,
        )

        # make_join should only succeed for private rooms, and be forbidden for public
        # send_join should only succeed for private rooms
        self.send_join(
            self.remote_hba_user,
            room_id,
            make_join_expected_code=(
                HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK
            ),
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_local_room_remote_pro_with_invites_no_permission(
        self, _: str, is_public: bool
    ) -> None:
        """
        Test with invites behavior for public and private rooms when inviting a remote user.
        """
        room_id = self.user_create_room(self.user_d, [], is_public=is_public)
        assert room_id is not None, "Room should have been created"

        # Inviting a remote user is allowed by default
        self.helper.invite(
            room_id,
            self.user_d,
            self.remote_hba_user,
            expect_code=HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK,
            tok=self.access_token_d,
        )

        self.send_join(
            self.remote_hba_user,
            room_id,
            make_join_expected_code=(
                HTTPStatus.FORBIDDEN if is_public else HTTPStatus.OK
            ),
        )


class DisableOverridePublicRoomFederationTestCase(FederatingModuleApiTestCase):
    """
    Test that disabling 'override_public_room_federation' allows federation to function
    Unlike tests in test_createrooms_remote.py, these have rooms created with no invites
    """

    # By default, we are SERVER_NAME_FROM_LIST
    # server_name_for_this_server = "tim.test.gematik.de"
    # This test case will model being an PRO server on the federation list

    # Test with two remote PRO user(one hba and one unlisted) and one EPA user
    remote_hba_user = f"@mxid:{DOMAIN_IN_LIST}"
    # remote_pro_user = f"unlisted:{DOMAIN_IN_LIST}"
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
        # self.user_b = self.register_user("b", "password")
        # self.access_token_b = self.login("b", "password")
        # self.user_c = self.register_user("c", "password")
        # self.access_token_c = self.login("c", "password")

        # "d" is none of those types of actor and should be just a 'User'. For
        # context, this could be a chatbot or an office manager
        self.user_d = self.register_user("d", "password")
        self.access_token_d = self.login("d", "password")

        self.user_id_to_token = {
            self.user_a: self.access_token_a,
            # self.user_b: self.access_token_b,
            # self.user_c: self.access_token_c,
            self.user_d: self.access_token_d,
        }

        self.inv_checker: InviteChecker = self.hs.mockmod

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

    def user_create_room(
        self,
        creating_user: str,
        invitee_list: list[str],
        is_public: bool,
        expected_code: int = HTTPStatus.OK,
    ) -> str | None:
        """
        Helper to send an api request with a full set of required additional room state
        to the room creation matrix endpoint.
        """
        return self.helper.create_room_as(
            creating_user,
            is_public=is_public,
            tok=self.user_id_to_token.get(creating_user),
            expect_code=expected_code,
            extra_content=construct_extra_content(creating_user, invitee_list),
        )

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()

        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update(
            {"override_public_room_federation": False}
        )

        return conf

    def test_room_federation(self) -> None:
        """
        Test that the local server can successfully allow joining a remote room when
        there are no invites
        """
        room_id = self.user_create_room(self.user_a, [], is_public=True)
        assert room_id is not None, "Room should have been created"

        # make_join should succeed, as the override was blocked
        self.send_join(
            self.remote_hba_user,
            room_id,
        )


class OutgoingRemoteJoinTestCase(FederatingModuleApiTestCase):
    """
    Test for behavior when joining a remote room
    """

    # server_name_for_this_server = "tim.test.gematik.de"
    # This test case will model being an PRO server on the federation list
    # By default we are SERVER_NAME_FROM_LIST

    # Test with one other remote PRO server and one EPA server
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
        )
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

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_pro_no_invites(self, _: str, is_public: bool) -> None:
        """
        Test that the local server can successfully block joining a remote room when
        there are no invites
        """
        remote_room_id = self.create_remote_room(self.remote_pro_user, "10", is_public)
        assert remote_room_id is not None

        # Public rooms should fail.
        # Private rooms should also fail because no invite. Should be a 403
        self.do_remote_join(
            remote_room_id, self.user_a, expected_code=HTTPStatus.FORBIDDEN
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_pro_with_invites(self, _: str, is_public: bool) -> None:
        """
        Test that the local server can successfully join a remote PRO server room, when
        appropriate, if there are invites
        """
        remote_room_id = self.create_remote_room(self.remote_pro_user, "10", is_public)
        assert remote_room_id is not None

        # This should be enough to inject the "fact" we got an invite, and should
        # allow private room joining. Both users are 'pract'
        self.do_remote_invite(self.user_a, self.remote_pro_user, remote_room_id)

        # Public rooms should fail with a 403. Private rooms should succeed, because of
        # the invite
        self.do_remote_join(
            remote_room_id,
            self.user_a,
            expected_code=HTTPStatus.FORBIDDEN if is_public else None,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_epa_no_invites(self, _: str, is_public: bool) -> None:
        """
        Test that the local server can successfully block a remote EPA server room when
        there are no invites
        """
        remote_room_id = self.create_remote_room(self.remote_epa_user, "10", is_public)
        assert remote_room_id is not None

        # In both cases, this raises. Neither private nor public rooms are allowed.
        # Public, because they are denied without invites, and private because the
        # there was no invite
        self.do_remote_join(
            remote_room_id,
            self.user_a,
            expected_code=HTTPStatus.FORBIDDEN,
        )

        # Try with a different local user, one with no visibility
        # Public rooms should fail. Private rooms should also fail because no invite
        self.do_remote_join(
            remote_room_id,
            self.user_d,
            expected_code=HTTPStatus.FORBIDDEN,
        )

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_epa_with_invites_blocked(
        self, _: str, is_public: bool
    ) -> None:
        """
        Test that the local server can successfully block a remote EPA server room, when
        an invite is blocked from lack of permissions
        """
        remote_room_id = self.create_remote_room(self.remote_epa_user, "10", is_public)
        assert remote_room_id is not None

        self.set_permissions_for_user(
            self.user_a,
            PermissionConfig(defaultSetting=PermissionDefaultSetting.BLOCK_ALL),
        )

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
        self.do_remote_join(
            remote_room_id,
            self.user_a,
            expected_code=HTTPStatus.FORBIDDEN,
        )

        # Re-using this room exposed a flaw. The FakeRoom thinks that the last event
        # in the room is the invite for 'a'. Our local copy of the room denied that
        # event, so it doesn't exist. The next invite to occur just below will have that
        # denied invite as it's prev_event, which will then deny that next invite(since
        # the event doesn't exist as far as the local room is concerned). In theory,
        # this is bad. In practice, I don't think it will happen unless a public room
        # experiences an invite that is denied over federation(which is also not allowed).
        # Just create a new fake room to test with instead.

    @parameterized.expand([("public", True), ("private", False)])
    def test_remote_room_epa_with_invites_allowed(
        self, _: str, is_public: bool
    ) -> None:
        """
        Test that the local server can successfully join a remote EPA server room, when
        an invite is allowed
        """
        remote_room_id = self.create_remote_room(self.remote_epa_user, "10", is_public)
        assert remote_room_id is not None

        # User 'd' must grant their permission
        self.set_permissions_for_user(
            self.user_d,
            PermissionConfig(
                defaultSetting=PermissionDefaultSetting.BLOCK_ALL,
                userExceptions={self.remote_epa_user: dict()},
            ),
        )

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
        self.do_remote_join(
            remote_room_id,
            self.user_d,
            expected_code=HTTPStatus.FORBIDDEN if is_public else None,
        )
