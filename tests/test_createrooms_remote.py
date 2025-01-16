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
    remote_user = f"@mxidorg:{DOMAIN_IN_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    remote_non_fed_list_user = "@rando:fake-website.com"

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

    @parameterized.expand([("public", True), ("private", False)])
    def test_hba_to_hba_create_room(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local User-HBA to a remote User-HBA behaves as expected
        """
        room_id = self.user_a_create_room(
            [self.remote_pro_user],
            is_public=is_public,
        )
        assert room_id, f"User-HBA {label} room with remote User-HBA not created"

    @parameterized.expand([("public", True), ("private", False)])
    def test_user_and_hba_create_room(self, label: str, is_public: bool) -> None:
        """
        Tests room creation between a User and a User-HBA where either can be remote
        """
        # this one should fail, a User cannot contact another organization's User-HBA
        # without contact details
        room_id = self.user_b_create_room(
            [self.remote_pro_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"Local User {label} room with remote User-HBA incorrectly created"

        # this one should fail, no contact details
        room_id = self.user_d_create_room(
            [self.remote_pro_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"Local unlisted User {label} room with remote User-HBA incorrectly created"

        # this one should fail, this user is not in the VZD Directory
        room_id = self.user_a_create_room(
            [self.remote_unlisted_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"Local User-HBA {label} room with remote unlisted User incorrectly created"

        # this one should pass, as it's an organization User
        room_id = self.user_a_create_room(
            [self.remote_user],
            is_public=is_public,
        )
        assert room_id, f"Local User-HBA {label} room with remote User not created"

    @parameterized.expand([("public", True), ("private", False)])
    def test_hba_to_epa_create_room(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local User-HBA to a remote insured User behaves as expected
        """
        room_id = self.user_a_create_room(
            [self.remote_epa_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-HBA {label} room with remote insured incorrectly created"

        # Need to add in contact permission
        self.add_a_contact_to_user_by_token(self.remote_epa_user, self.access_token_a)

        room_id = self.user_a_create_room(
            [self.remote_epa_user],
            is_public=is_public,
        )
        assert room_id, f"User-HBA {label} room with remote insured not created"

    @parameterized.expand([("public", True), ("private", False)])
    def test_any_user_to_non_fed_domain_create_room_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests room creation fails from any local User to a remote domain not on the fed list
        """
        room_id = self.user_a_create_room(
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-HBA {label} room with remote non-fed-list domain incorrectly created"

        room_id = self.user_b_create_room(
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User {label} room with remote non-fed-list domain incorrectly created"

        room_id = self.user_d_create_room(
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"Non-VZD listed user {label} room with remote non-fed-list domain incorrectly created"

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
            [self.user_b, self.remote_pro_user],
            [self.user_b, self.remote_epa_user],
            [self.user_b, self.remote_non_fed_list_user],
            # Try with the remote user first too
            [self.remote_pro_user, self.user_b],
            [self.remote_epa_user, self.user_b],
            [self.remote_non_fed_list_user, self.user_b],
        ]:
            room_id = self.user_a_create_room(
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-HBA {label} room incorrectly created with invites to:[{invitee_list}]"

        for remote_user_to_add in (
            self.remote_pro_user,
            self.remote_epa_user,
            self.remote_non_fed_list_user,
            self.user_b,
        ):
            self.add_a_contact_to_user_by_token(remote_user_to_add, self.access_token_a)

        # Then try with contact permissions added
        for invitee_list in [
            [self.user_b, self.remote_pro_user],
            [self.user_b, self.remote_epa_user],
            [self.user_b, self.remote_non_fed_list_user],
            [self.remote_pro_user, self.user_b],
            [self.remote_epa_user, self.user_b],
            [self.remote_non_fed_list_user, self.user_b],
        ]:
            room_id = self.user_a_create_room(
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-HBA {label} room incorrectly created with invites to:[{invitee_list}] with contact permissions"


class RemoteEpaModeCreateRoomTest(ModuleApiTestCase):
    """
    These tests are for invites during room creation. Invites after room creation will
    be tested separately

    ePA mode servers should only have insured Users

    Per https://gemspec.gematik.de/docs/gemSpec/gemSpec_TI-M_ePA/latest/#AF_10233 and
    its two additions(A_20704 and A_20704)
    an invitation to a room where both parties are insured should be denied.
    """

    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    remote_non_fed_list_user = "@rando:fake-website.com"
    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        # Can't use any of:
        #  @a:test is a practitioner
        #  @b:test is an organization
        #  @c:test is an 'orgPract'
        # as they should not exist on an 'ePA' mode server backend

        # @d:test is none of these things and should be just a 'User'
        self.user_d = self.register_user("d", "password")
        self.user_e = self.register_user("e", "password")
        self.access_token_d = self.login("d", "password")

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
                tok=self.access_token_d,
                extra_content=construct_extra_content(self.user_d, invitee_list),
            )
        return None

    @parameterized.expand([("public", True), ("private", False)])
    def test_epa_to_hba_create_room(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local insured User to a remote User-HBA behaves as expected
        """
        room_id = self.user_d_create_room(
            [self.remote_pro_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote User-HBA incorrectly created"

        self.add_a_contact_to_user_by_token(self.remote_pro_user, self.access_token_d)

        room_id = self.user_d_create_room(
            [self.remote_pro_user],
            is_public=is_public,
        )
        assert room_id, f"User-ePA {label} room with remote User-HBA not created"

    @parameterized.expand([("public", True), ("private", False)])
    def test_epa_to_epa_create_room_fails(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local insured User to a remote insured User
        fails as expected.
        """
        room_id = self.user_d_create_room(
            [self.remote_epa_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote insured incorrectly created"

    @parameterized.expand([("public", True), ("private", False)])
    def test_epa_to_non_fed_domain_create_any_room_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests room creation from a local insured User to a remote domain not on the fed list fails
        """
        room_id = self.user_d_create_room(
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote non-fed-list domain incorrectly created"

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_with_two_invites_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests that room creation fails with more than one included invite
        """
        for invitee_list in [
            [self.user_e, self.remote_pro_user],
            [self.user_e, self.remote_epa_user],
            [self.user_e, self.remote_non_fed_list_user],
        ]:
            room_id = self.user_d_create_room(
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-ePA {label} room incorrectly created with invites to:[{invitee_list}]"

        # Add in contact permissions and try again
        for remote_user_to_add in (
            self.remote_pro_user,
            self.remote_epa_user,
            self.remote_non_fed_list_user,
            self.user_e,
        ):
            self.add_a_contact_to_user_by_token(remote_user_to_add, self.access_token_d)

        for invitee_list in [
            [self.user_e, self.remote_pro_user],
            [self.user_e, self.remote_epa_user],
            [self.user_e, self.remote_non_fed_list_user],
        ]:
            room_id = self.user_d_create_room(
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-ePA {label} room incorrectly created with invites to:[{invitee_list}] with contact permissions"
