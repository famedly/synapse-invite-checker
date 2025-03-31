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
from typing import Any

from parameterized import parameterized
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import FederatingModuleApiTestCase
from tests.test_utils import (
    DOMAIN2_IN_LIST,
    DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL,
)


class RemoteProModeCreateRoomTest(FederatingModuleApiTestCase):
    """
    These PRO server tests are for room creation process, to demonstrate that rooms can
    be created when inviting during it's processing.
    NOTE: Event though the server is designated as "block all" the outgoing invites are
    allowed as invites are only checked by the receiving user. This means the room will
    be created, but empty of the other user. Public rooms with invites to a remote user
    will still fail as expected

    Also test special cases that should be allowed or prevented, like trying to invite
    2 users during room creation.
    """

    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_unlisted_user = f"@gematikuri404:{DOMAIN_IN_LIST}"
    remote_org_user = f"@mxidorg:{DOMAIN_IN_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    remote_non_fed_list_user = "@rando:fake-website.com"
    # SERVER_NAME_FROM_LIST = "tim.test.gematik.de"

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.pro_user_a = self.register_user("a", "password")
        self.pro_user_b = self.register_user("b", "password")
        self.login("a", "password")
        self.login("b", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "pro"})
        conf["modules"][0].setdefault("config", {}).update(
            {"default_permissions": {"defaultSetting": "block all"}}
        )
        return conf

    @parameterized.expand([("public", True, False), ("private", False, True)])
    def test_create_room(
        self, label: str, is_public: bool, expect_creation: bool
    ) -> None:
        """
        Tests room creation from a local User to a remote User behaves as expected
        """
        for remote_user in (self.remote_pro_user, self.remote_epa_user):
            room_id = self.create_local_room(
                self.pro_user_a,
                [remote_user],
                is_public=is_public,
            )
            assert (
                room_id is not None
            ) is expect_creation, f"Creating {label} room from {self.pro_user_a} while inviting {remote_user}: {'denied' if expect_creation else 'allowed'}"

    @parameterized.expand([("public", True), ("private", False)])
    def test_any_user_to_non_fed_domain_create_room_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests room creation fails from any local User to a remote domain not on the fed list
        """
        for local_user in (self.pro_user_a, self.pro_user_b):
            room_id = self.create_local_room(
                local_user,
                [self.remote_non_fed_list_user],
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User '{local_user}'s {label} room with remote non-fed-list domain should not be created"

    @parameterized.expand([("public", True), ("private", False)])
    def test_create_room_with_two_invites_fails(
        self, label: str, is_public: bool
    ) -> None:
        """
        Tests that a room can NOT be created when more than one additional member is
        invited during creation
        """
        # First try with no contact permissions in place, the server default is "block all"
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
            room_id = self.create_local_room(
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
            # Grant the exception, but it won't matter
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
            room_id = self.create_local_room(
                self.pro_user_a,
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-HBA {label} room should not be created(after permission) with invites to: {invitee_list}"


class RemoteEpaModeCreateRoomTest(FederatingModuleApiTestCase):
    """
    These EPA server tests are for room creation process, including invite checking for
    REMOTE users and special cases that should be allowed or prevented.

    ePA mode servers should only have insured Users.
    Per https://gemspec.gematik.de/docs/gemSpec/gemSpec_TI-M_ePA/latest/#AF_10233 and
    its two additions(A_20704 and A_20704)
    an invitation to a room where both parties are insured should be denied.
    """

    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_pro_user_2 = f"@gematikuri2org:{DOMAIN2_IN_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    remote_non_fed_list_user = "@rando:fake-website.com"
    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.epa_user_d = self.register_user("d", "password")
        self.epa_user_e = self.register_user("e", "password")
        self.login("d", "password")
        self.login("e", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        conf["modules"][0].setdefault("config", {}).update(
            {"default_permissions": {"defaultSetting": "allow all"}}
        )
        return conf

    @parameterized.expand([("public", True), ("private", False)])
    def test_epa_to_pro_create_room(self, label: str, is_public: bool) -> None:
        """
        Tests room creation from a local insured User to a remote Pro-User behaves as expected
        """
        room_id = self.create_local_room(
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
        room_id = self.create_local_room(
            self.epa_user_d,
            [self.remote_epa_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote insured should not be created(before permissions)"

        # Touching the permission(since the server is "allow all") should not help them
        # get a room made
        self.add_permission_to_a_user(self.remote_epa_user, self.epa_user_d)

        room_id = self.create_local_room(
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
        room_id = self.create_local_room(
            self.epa_user_d,
            [self.remote_non_fed_list_user],
            is_public=is_public,
        )
        assert (
            room_id is None
        ), f"User-ePA {label} room with remote non-fed-list domain should not be created(before permissions)"

        # Touching the permission(since the server is "allow all") should not help them
        # get a room made
        self.add_permission_to_a_user(self.remote_non_fed_list_user, self.epa_user_d)

        room_id = self.create_local_room(
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
            room_id = self.create_local_room(
                self.epa_user_e,
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-ePA {label} room should not be created(before permission) with invites to: {invitee_list}"

        # Touching the permission(since the server is "allow all") should not help them
        # get a room made
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
            room_id = self.create_local_room(
                self.epa_user_e,
                invitee_list,
                is_public=is_public,
            )
            assert (
                room_id is None
            ), f"User-ePA {label} room should not be created(after permission) with invites to: {invitee_list}"
