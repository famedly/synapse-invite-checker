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

from synapse.module_api import NOT_SPAM, errors
from synapse.server import HomeServer
from synapse.types import UserID
from synapse.util import Clock
from twisted.internet import defer
from twisted.internet.testing import MemoryReactor

from synapse_invite_checker.types import (
    GroupName,
    PermissionConfig,
    PermissionDefaultSetting,
)
from tests.base import FederatingModuleApiTestCase
from tests.test_utils import (
    DOMAIN3_IN_LIST,
    DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL,
)


class RemoteProModeInviteTest(FederatingModuleApiTestCase):
    """
    These PRO server tests are for invites that happen after the room creation process
    has completed
    """

    # SERVER_NAME_FROM_LIST = "tim.test.gematik.de"

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.pro_user_a = self.register_user("a", "password")
        self.pro_user_b = self.register_user("b", "password")
        self.pro_user_c = self.register_user("c", "password")
        self.pro_user_d = self.register_user("d", "password")
        self.login("a", "password")
        self.login("b", "password")
        self.login("c", "password")
        self.login("d", "password")

    def may_invite(self, inviter: str, invitee: str, roomid: str):
        req = defer.ensureDeferred(
            self.hs.get_module_api()._callbacks.spam_checker.user_may_invite(
                inviter, invitee, roomid
            )
        )
        self.wait_on_thread(req)
        ret = self.get_success(req)
        if ret == NOT_SPAM:
            return NOT_SPAM
        return ret[0]  # return first code instead of all of them to make assert easier

    def test_invite_from_remote_user(self) -> None:
        """
        Tests that an invite from a remote user.
        """
        for remote_user_id in [
            f"@example:{DOMAIN_IN_LIST}",
            f"@example:{DOMAIN3_IN_LIST}",
            f"@mxid404:{DOMAIN_IN_LIST}",
        ]:
            for local_user in [
                self.pro_user_a,
                self.pro_user_b,
                self.pro_user_c,
                self.pro_user_d,
            ]:
                # default
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {local_user}"

                # Explicit allow all
                self.set_permissions_for_user(
                    local_user,
                    PermissionConfig(defaultSetting=PermissionDefaultSetting.ALLOW_ALL),
                )
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {local_user} (explicit all)"

                # Explicit block all
                self.set_permissions_for_user(
                    local_user,
                    PermissionConfig(defaultSetting=PermissionDefaultSetting.BLOCK_ALL),
                )
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == errors.Codes.FORBIDDEN
                ), f"'{remote_user_id}' should be BLOCKED from inviting {local_user} (explicit all)"

                # Explicit allow single
                self.set_permissions_for_user(
                    local_user,
                    PermissionConfig(
                        defaultSetting=PermissionDefaultSetting.BLOCK_ALL,
                        userExceptions={remote_user_id: dict()},
                    ),
                )
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {local_user} (explicit single)"

                # Explicit block single
                self.set_permissions_for_user(
                    local_user,
                    PermissionConfig(
                        defaultSetting=PermissionDefaultSetting.ALLOW_ALL,
                        userExceptions={remote_user_id: dict()},
                    ),
                )
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == errors.Codes.FORBIDDEN
                ), f"'{remote_user_id}' should be BLOCKED from inviting {local_user} (explicit single)"

                # Explicit allow server
                self.set_permissions_for_user(
                    local_user,
                    PermissionConfig(
                        defaultSetting=PermissionDefaultSetting.BLOCK_ALL,
                        serverExceptions={
                            UserID.from_string(remote_user_id).domain: dict()
                        },
                    ),
                )
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {local_user} (explicit server)"

                # Explicit block server
                self.set_permissions_for_user(
                    local_user,
                    PermissionConfig(
                        defaultSetting=PermissionDefaultSetting.ALLOW_ALL,
                        serverExceptions={
                            UserID.from_string(remote_user_id).domain: dict()
                        },
                    ),
                )
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == errors.Codes.FORBIDDEN
                ), f"'{remote_user_id}' should be BLOCKED from inviting {local_user} (explicit server)"

    def test_invite_from_remote_outside_of_fed_list(self) -> None:
        """Tests that an invite from a remote server not in the federation list gets denied"""
        for remote_user_id in [
            f"@example:not-{DOMAIN_IN_LIST}",
            f"@example2:not-{DOMAIN_IN_LIST}",
            "@madeupuser:thecornerstore.de",
            "@unknown:not.in.fed",
        ]:
            for local_user in [
                self.pro_user_a,
                self.pro_user_b,
                self.pro_user_c,
                self.pro_user_d,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == errors.Codes.FORBIDDEN
                ), f"'{remote_user_id}' should be FORBIDDEN to invite {local_user}(before permission)"

            for local_user in [
                self.pro_user_a,
                self.pro_user_b,
                self.pro_user_c,
                self.pro_user_d,
            ]:
                # Add permissions, but it shouldn't matter
                self.add_permission_to_a_user(remote_user_id, local_user)
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == errors.Codes.FORBIDDEN
                ), f"'{remote_user_id}' should be FORBIDDEN to invite {local_user}(after permission)"

    def test_remote_invite_from_an_insurance_domain(self) -> None:
        """
        Test that an insured user can invite a publicly listed practitioner or organization
        (but not a user who blocked the insurance group)
        """
        for remote_user_id in (
            f"@unknown:{INSURANCE_DOMAIN_IN_LIST}",
            f"@rando-32-b52:{INSURANCE_DOMAIN_IN_LIST}",
        ):
            assert (
                self.may_invite(remote_user_id, self.pro_user_b, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {self.pro_user_b}"
            assert (
                self.may_invite(remote_user_id, self.pro_user_c, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {self.pro_user_c}"

            self.set_permissions_for_user(
                self.pro_user_d,
                PermissionConfig(
                    defaultSetting=PermissionDefaultSetting.ALLOW_ALL,
                    groupExceptions=[{"groupName": GroupName.isInsuredPerson.value}],
                ),
            )
            assert (
                self.may_invite(remote_user_id, self.pro_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.pro_user_d} without contact details"


class RemoteEpaModeInviteTest(FederatingModuleApiTestCase):
    """
    These Epa server tests are for invites that happen after the room creation process
    has completed

    Note that if the local server is in 'epa' mode, it means the server 'isInsurance'.
    Therefore, it is the responsibility of the remote server to deny *our* invites.
    Likewise, it is our responsibility to deny *theirs* if they are also 'isInsurance'.

    The second behavior is what we test here
    """

    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.epa_user_d = self.register_user("d", "password")
        self.login("d", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        return conf

    def may_invite(self, inviter: str, invitee: str, room_id: str):
        req = defer.ensureDeferred(
            self.hs.get_module_api()._callbacks.spam_checker.user_may_invite(
                inviter, invitee, room_id
            )
        )
        self.wait_on_thread(req)
        ret = self.get_success(req)
        if ret == NOT_SPAM:
            return NOT_SPAM
        return ret[0]  # return first code instead of all of them to make assert easier

    def test_invite_from_remote_not_on_fed_list(self) -> None:
        """Tests that an invite from a remote server not in the federation list gets denied"""
        # Add in permissions for one of them, it doesn't work anyway
        self.add_permission_to_a_user(f"@example:not-{DOMAIN_IN_LIST}", self.epa_user_d)

        for remote_user_id in (
            f"@example:not-{DOMAIN_IN_LIST}",
            f"@example2:not-{DOMAIN_IN_LIST}",
        ):
            assert (
                self.may_invite(remote_user_id, self.epa_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.epa_user_d}"

    def test_invite_from_remote_users(self) -> None:
        """
        Tests that an invite from a remote server gets accepted when in the federation
        list.
        """
        for remote_user_id in (
            f"@mxid:{DOMAIN_IN_LIST}",
            f"@matrixuri:{DOMAIN_IN_LIST}",
        ):
            local_user = self.epa_user_d

            self.set_permissions_for_user(local_user, PermissionConfig())

            # default
            assert (
                self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {local_user}"

            # Explicit allow all
            self.set_permissions_for_user(
                local_user,
                PermissionConfig(defaultSetting=PermissionDefaultSetting.ALLOW_ALL),
            )
            assert (
                self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {local_user} (explicit all)"

            # Explicit block all
            self.set_permissions_for_user(
                local_user,
                PermissionConfig(defaultSetting=PermissionDefaultSetting.BLOCK_ALL),
            )
            assert (
                self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be BLOCKED from inviting {local_user} (explicit all)"

            # Explicit allow single
            self.set_permissions_for_user(
                local_user,
                PermissionConfig(
                    defaultSetting=PermissionDefaultSetting.BLOCK_ALL,
                    userExceptions={remote_user_id: dict()},
                ),
            )
            assert (
                self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {local_user} (explicit single)"

            # Explicit block single
            self.set_permissions_for_user(
                local_user,
                PermissionConfig(
                    defaultSetting=PermissionDefaultSetting.ALLOW_ALL,
                    userExceptions={remote_user_id: dict()},
                ),
            )
            assert (
                self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be BLOCKED from inviting {local_user} (explicit single)"

            # Explicit allow server
            self.set_permissions_for_user(
                local_user,
                PermissionConfig(
                    defaultSetting=PermissionDefaultSetting.BLOCK_ALL,
                    serverExceptions={
                        UserID.from_string(remote_user_id).domain: dict()
                    },
                ),
            )
            assert (
                self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {local_user} (explicit server)"

            # Explicit block server
            self.set_permissions_for_user(
                local_user,
                PermissionConfig(
                    defaultSetting=PermissionDefaultSetting.ALLOW_ALL,
                    serverExceptions={
                        UserID.from_string(remote_user_id).domain: dict()
                    },
                ),
            )
            assert (
                self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be BLOCKED from inviting {local_user} (explicit server)"

    def test_remote_invite_from_an_insured_domain_fails(self) -> None:
        """
        Test that invites from another insurance domain are rejected with or without
        contact permissions
        """
        for remote_user_id in (
            f"@unknown:{INSURANCE_DOMAIN_IN_LIST}",
            f"@rando-32-b52:{INSURANCE_DOMAIN_IN_LIST}",
        ):
            assert (
                self.may_invite(remote_user_id, self.epa_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.epa_user_d}"

            # Add in permissions
            self.add_permission_to_a_user(remote_user_id, self.epa_user_d)

            # ...and try again
            assert (
                self.may_invite(remote_user_id, self.epa_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.epa_user_d}"
