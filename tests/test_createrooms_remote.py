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
from typing import Any

from parameterized import parameterized
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import ModuleApiTestCase, construct_extra_content
from tests.test_utils import (
    DOMAIN2_IN_LIST,
    DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL,
)

"""
These tests all focus on room creation at the API level. This allows us to test:
* The additional custom state required by gemSpec_TI-M_Basis is not rejected
* The number of additional users invited during room creation

"""


class RemoteProModeCreateRoomTest(ModuleApiTestCase):
    """
    These tests are for invites during room creation. Invites after room creation will
    be tested separately

    Pro mode servers User-HBA, potentially an 'org' User and a user that fills neither
    of these roles.
    """

    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_unlisted_user = f"@gematikuri404:{DOMAIN_IN_LIST}"
    remote_org_user = f"@mxidorg:{DOMAIN_IN_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    remote_non_fed_list_user = "@rando:fake-website.com"
    # SERVER_NAME_FROM_LIST = "tim.test.gematik.de"

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

    @parameterized.expand([("public", True), ("private", False)])
    def test_pro_to_pro_create_room(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local Pro-User to a remote Pro-User behaves as expected
        """
        room_id = self.user_create_room(
            self.pro_user_a,
            [self.remote_pro_user],
            is_public=is_public,
        )
        assert (
            (room_id is None) if is_public else room_id
        ), f"Pro-User {label} room with remote Pro-User should be: {'denied' if is_public else 'allowed'}"

    @parameterized.expand([("public", True), ("private", False)])
    def test_pro_to_epa_create_room(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local Pro-User to a remote insured User behaves as expected
        """
        room_id = self.user_create_room(
            self.pro_user_a,
            [self.remote_epa_user],
            is_public=is_public,
        )
        assert (
            (room_id is None) if is_public else room_id
        ), f"Pro-User {label} room with remote Epa-User should be: {'denied' if is_public else 'allowed'}"

    @parameterized.expand([("public", True), ("private", False)])
    def test_any_user_to_non_fed_domain_create_room_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests room creation fails from any local User to a remote domain not on the fed list
        """
        room_id = self.user_create_room(
            self.pro_user_a,
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-HBA {label} room with remote non-fed-list domain should not be created"

        room_id = self.user_create_room(
            self.pro_user_b,
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User {label} room with remote non-fed-list domain should not be created"

        room_id = self.user_create_room(
            self.pro_user_d,
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"Non-VZD listed user {label} room with remote non-fed-list domain should not be created"

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_with_two_invites_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests that a room can NOT be created when more than one additional member is
        invited during creation
        """
        # First try with no contact permissions in place
        for invitee_list in [
            # Specifically invite the local user first, as that should always
            # have succeeded
            [self.pro_user_b, self.remote_pro_user],
            [self.pro_user_b, self.remote_epa_user],
            [self.pro_user_b, self.remote_non_fed_list_user],
            # Try with the remote user first too
            [self.remote_pro_user, self.pro_user_b],
            [self.remote_epa_user, self.pro_user_b],
            [self.remote_non_fed_list_user, self.pro_user_b],
        ]:
            room_id = self.user_create_room(
                self.pro_user_a,
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-HBA {label} room should not be created(before permission) with invites to: {invitee_list}"

        for remote_user_to_add in (
            self.remote_pro_user,
            self.remote_epa_user,
            self.remote_non_fed_list_user,
            self.pro_user_b,
        ):
            self.add_permission_to_a_user(remote_user_to_add, self.pro_user_a)

        # Then try with contact permissions added
        for invitee_list in [
            [self.pro_user_b, self.remote_pro_user],
            [self.pro_user_b, self.remote_epa_user],
            [self.pro_user_b, self.remote_non_fed_list_user],
            [self.remote_pro_user, self.pro_user_b],
            [self.remote_epa_user, self.pro_user_b],
            [self.remote_non_fed_list_user, self.pro_user_b],
        ]:
            room_id = self.user_create_room(
                self.pro_user_a,
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-HBA {label} room should not be created(after permission) with invites to: {invitee_list}"


class RemoteEpaModeCreateRoomTest(ModuleApiTestCase):
    """
    These tests are for invites during room creation. Invites after room creation will
    be tested separately

    ePA mode servers should only have insured Users

    Per https://gemspec.gematik.de/docs/gemSpec/gemSpec_TI-M_ePA/latest/#AF_10233 and
    its two additions(A_20704 and A_20704)
    an invitation to a room where both parties are insured should be denied.
    """

    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"  # this is a 'pract'
    remote_pro_user_2 = f"@gematikuri2org:{DOMAIN2_IN_LIST}"  # this is an 'org'
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    remote_non_fed_list_user = "@rando:fake-website.com"
    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        # "d" and "e" are just ePA 'User's
        self.epa_user_d = self.register_user("d", "password")
        self.epa_user_e = self.register_user("e", "password")
        self.access_token_d = self.login("d", "password")
        self.access_token_e = self.login("e", "password")

        self.map_user_id_to_token = {
            self.epa_user_d: self.access_token_d,
            self.epa_user_e: self.access_token_e,
        }

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
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

    @parameterized.expand([("public", True), ("private", False)])
    def test_epa_to_pro_create_room(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local insured User to a remote Pro-User behaves as expected
        """
        room_id = self.user_create_room(
            self.epa_user_d,
            [self.remote_pro_user],
            is_public=is_public,
        )
        assert (
            (room_id is None) if is_public else room_id
        ), f"Epa-User {label} room with remote Pro-User should be: {'denied' if is_public else 'allowed'}"

    @parameterized.expand([("public", True), ("private", False)])
    def test_epa_to_epa_create_room_fails(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local insured User to a remote insured User
        fails as expected.
        """
        room_id = self.user_create_room(
            self.epa_user_d,
            [self.remote_epa_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote insured should not be created(before permissions)"

        self.add_permission_to_a_user(self.remote_epa_user, self.epa_user_d)

        room_id = self.user_create_room(
            self.epa_user_d,
            [self.remote_epa_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote insured should not be created(after permissions)"

    @parameterized.expand([("public", True), ("private", False)])
    def test_epa_to_non_fed_domain_create_any_room_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests room creation from a local insured User to a remote domain not on the fed list fails
        """
        room_id = self.user_create_room(
            self.epa_user_d,
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote non-fed-list domain should not be created(before permissions)"

        self.add_permission_to_a_user(self.remote_non_fed_list_user, self.epa_user_d)

        room_id = self.user_create_room(
            self.epa_user_d,
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote non-fed-list domain should not be created(after permissions)"

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_with_two_invites_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests that room creation fails with more than one included invite
        """
        # User "d" got contaminated in other tests with permissions, use a clean user
        # to create rooms
        for invitee_list in [
            [self.remote_pro_user_2, self.remote_pro_user],
            [self.remote_pro_user_2, self.remote_epa_user],
            [self.remote_pro_user_2, self.remote_non_fed_list_user],
        ]:
            room_id = self.user_create_room(
                self.epa_user_e,
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-ePA {label} room should not be created(before permission) with invites to: {invitee_list}"

        # Add in contact permissions and try again
        for remote_user_to_add in (
            self.remote_pro_user,
            self.remote_epa_user,
            self.remote_non_fed_list_user,
            self.remote_pro_user_2,
        ):
            self.add_permission_to_a_user(remote_user_to_add, self.epa_user_e)

        for invitee_list in [
            [self.remote_pro_user_2, self.remote_pro_user],
            [self.remote_pro_user_2, self.remote_epa_user],
            [self.remote_pro_user_2, self.remote_non_fed_list_user],
        ]:
            room_id = self.user_create_room(
                self.epa_user_e,
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-ePA {label} room should not be created(after permission) with invites to: {invitee_list}"
