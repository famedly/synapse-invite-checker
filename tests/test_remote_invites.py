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

from synapse_invite_checker.types import PermissionDefaultSetting
from tests.base import ModuleApiTestCase
from tests.test_utils import (
    DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL,
)


class RemoteProModeInviteTest(ModuleApiTestCase):
    """Test remote invites in the default 'pro' mode behave as expected."""

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
        self.access_token_d = self.login("d", "password")

        # authenticated as user_a
        self.helper.auth_user_id = self.user_a

        # Tweak user 'a' to have 'allow all' as their permissions
        self.inv_checker = self.hs.mockmod
        permissions = self.get_success_or_raise(
            self.inv_checker.permissions_handler.get_permissions(self.user_a)
        )
        permissions.defaultSetting = PermissionDefaultSetting.ALLOW_ALL
        self.get_success_or_raise(
            self.inv_checker.permissions_handler.update_permissions(
                self.user_a, permissions
            )
        )

    def may_invite(self, inviter: str, invitee: str):
        # construct a room id appropriate to the inviter's remote server
        room_id = f"!madeup:{UserID.from_string(inviter).domain}"
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

    def test_invite_from_remote_pro_server(self) -> None:
        """
        Test that a remote user on the fed list that is not publicly listed acts as expected.
        """
        # User "a" is publicly listed, and has "allow all" as permissions
        # User "b" is publicly listed, and has "block all" as permissions
        # User "d" is not publicly listed, and has "block all" as permissions
        # No remote users are publicly listed
        for remote_user_id in [
            "@example:messenger.spilikin.dev",
            f"@example:{DOMAIN_IN_LIST}",
            f"@example2:{DOMAIN_IN_LIST}",
            f"@mxid404:{DOMAIN_IN_LIST}",
            f"@matrixuri404:{DOMAIN_IN_LIST}",
            f"@matrixuri2404:{DOMAIN_IN_LIST}",
            f"@gematikuri404:{DOMAIN_IN_LIST}",
            f"@gematikuri2404:{DOMAIN_IN_LIST}",
        ]:
            assert (
                self.may_invite(remote_user_id, self.user_a) == NOT_SPAM
            ), f"inviter '{remote_user_id}' should be ALLOWED to invite {self.user_a}"

            assert (
                self.may_invite(remote_user_id, self.user_b) == NOT_SPAM
            ), f"inviter '{remote_user_id}' should be ALLOWED to invite {self.user_b}"

            assert (
                self.may_invite(remote_user_id, self.user_d) == errors.Codes.FORBIDDEN
            ), f"inviter '{remote_user_id}' should be FORBIDDEN to invite {self.user_d}"

        # Special extra: Invite works after adding permission via contact
        # User "d" is using a 'block all', so has to selectively add a permission
        self.add_a_contact_to_user_by_token(
            f"@example:{DOMAIN_IN_LIST}", self.access_token_d
        )

        # Now it should work
        assert (
            self.may_invite(f"@example:{DOMAIN_IN_LIST}", self.user_d) == NOT_SPAM
        ), f"inviter '@example:{DOMAIN_IN_LIST}' should be ALLOWED to invite {self.user_d} after adding permission"

    def test_invite_from_remote_not_on_fed_list(self) -> None:
        """Tests that an invite from a remote server not in the federation list gets denied"""
        # User "a" is publicly listed, and has "allow all" as permissions
        # User "b" is publicly listed, and has "block all" as permissions
        # User "d" is not publicly listed, and has "block all" as permissions
        for remote_user_id in [
            f"@example:not-{DOMAIN_IN_LIST}",
            f"@example2:not-{DOMAIN_IN_LIST}",
            "@madeup:example.com",
            "@unknown:not.in.fed",
        ]:
            assert (
                self.may_invite(remote_user_id, self.user_a) == errors.Codes.FORBIDDEN
            ), f"inviter '{remote_user_id}' should be FORBIDDEN to invite {self.user_a}"

            assert (
                self.may_invite(remote_user_id, self.user_b) == errors.Codes.FORBIDDEN
            ), f"inviter '{remote_user_id}' should be FORBIDDEN to invite {self.user_b}"

            assert (
                self.may_invite(remote_user_id, self.user_d) == errors.Codes.FORBIDDEN
            ), f"inviter '{remote_user_id}' should be FORBIDDEN to invite {self.user_d}"

    def test_invite_from_publicly_listed_practitioners(self) -> None:
        """
        Tests that an invite from a remote server gets accepted when in the
        federation list and both practitioners are public
        """
        for inviter in {
            f"@mxid:{DOMAIN_IN_LIST}",
            f"@matrixuri:{DOMAIN_IN_LIST}",
            f"@matrixuri2:{DOMAIN_IN_LIST}",
            f"@gematikuri:{DOMAIN_IN_LIST}",
            f"@gematikuri2:{DOMAIN_IN_LIST}",
            f"@mxidorgpract:{DOMAIN_IN_LIST}",
            f"@matrixuriorgpract:{DOMAIN_IN_LIST}",
            f"@matrixuri2orgpract:{DOMAIN_IN_LIST}",
            f"@gematikuriorgpract:{DOMAIN_IN_LIST}",
            f"@gematikuri2orgpract:{DOMAIN_IN_LIST}",
        }:
            # These two are publicly listed
            assert (
                self.may_invite(inviter, self.user_a) == NOT_SPAM
            ), f"inviter {inviter} should be ALLOWED to invite {self.user_a}"
            assert (
                self.may_invite(inviter, self.user_c) == NOT_SPAM
            ), f"inviter {inviter} should be ALLOWED to invite {self.user_c}"
            # Not publicly listed
            assert (
                self.may_invite(inviter, self.user_d) == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} should be FORBIDDEN to invite {self.user_d}"

    def test_remote_invite_from_an_insurance_domain(self) -> None:
        """
        Test that an insured user can invite a publicly listed practitioner or organization
        (but not a regular user on the practitioner's domain)
        """
        for inviter in {
            f"@unknown:{INSURANCE_DOMAIN_IN_LIST}",
            f"@rando-32-b52:{INSURANCE_DOMAIN_IN_LIST}",
        }:
            assert (
                self.may_invite(inviter, self.user_b) == NOT_SPAM
            ), f"inviter {inviter} should be ALLOWED to invite {self.user_b}"
            assert (
                self.may_invite(inviter, self.user_c) == NOT_SPAM
            ), f"inviter {inviter} should be ALLOWED to invite {self.user_b}"
            assert (
                self.may_invite(inviter, self.user_d) == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} should be FORBIDDEN to invite {self.user_d}"


class RemoteEpaModeInviteTest(ModuleApiTestCase):
    """
    Test remote invites in 'epa' mode have expected behavior.

    Note that if the local server is in 'epa' mode, it means the server 'isInsurance'.
    Therefore, it is the responsibility of the remote server to deny *our* invites.
    Likewise, it is our responsibility to deny *theirs* if they are also 'isInsurance'.

    The second behavior is one thing we test here
    """

    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        # Can't use any of:
        #  @a:test is a practitioner
        #  @b:test is an organization
        #  @c:test is an 'orgPract'
        # as they should not exist on an 'ePA' mode server backend

        # These two are none of those types of actor and should be just regular 'User's
        # with the added detail they are insured
        self.user_allowing = self.register_user("allowing", "password")
        self.access_token_allowing = self.login("allowing", "password")
        self.user_blocking = self.register_user("blocking", "password")
        self.access_token_blocking = self.login("blocking", "password")

        # 'allowing' will have his permissions set to 'allow all'
        self.inv_checker = self.hs.mockmod
        permissions = self.get_success_or_raise(
            self.inv_checker.permissions_handler.get_permissions(self.user_allowing)
        )
        permissions.defaultSetting = PermissionDefaultSetting.ALLOW_ALL
        self.get_success_or_raise(
            self.inv_checker.permissions_handler.update_permissions(
                self.user_allowing, permissions
            )
        )

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        return conf

    def may_invite(self, inviter: str, invitee: str):
        # construct a room id appropriate to the inviter's remote server
        room_id = f"!madeup:{UserID.from_string(inviter).domain}"
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
        for inviter in {
            f"@example:not-{DOMAIN_IN_LIST}",
            f"@example2:not-{DOMAIN_IN_LIST}",
            "@bob:example.com",
        }:
            assert (
                self.may_invite(inviter, self.user_allowing) == errors.Codes.FORBIDDEN
            ), f"inviter '{inviter}' should be FORBIDDEN to invite {self.user_allowing}"

            assert (
                self.may_invite(inviter, self.user_blocking) == errors.Codes.FORBIDDEN
            ), f"inviter '{inviter}' should be FORBIDDEN to invite {self.user_blocking}"

    def test_invite_from_remote_non_practitioners(self) -> None:
        """Test that a remote user invite from a domain on the fed list only succeeds with permission"""
        for remote_user_id in [
            "@example:messenger.spilikin.dev",
            f"@example:{DOMAIN_IN_LIST}",
            f"@mxid404:{DOMAIN_IN_LIST}",
            f"@matrixuri404:{DOMAIN_IN_LIST}",
            f"@matrixuri2404:{DOMAIN_IN_LIST}",
            f"@gematikuri404:{DOMAIN_IN_LIST}",
            f"@gematikuri2404:{DOMAIN_IN_LIST}",
        ]:
            assert (
                self.may_invite(remote_user_id, self.user_allowing) == NOT_SPAM
            ), f"inviter '{remote_user_id}' should be ALLOWED to invite {self.user_allowing}"

            assert (
                self.may_invite(remote_user_id, self.user_blocking)
                == errors.Codes.FORBIDDEN
            ), f"inviter '{remote_user_id}' should be FORBIDDEN to invite {self.user_blocking}"

    def test_invite_from_remote_practitioners(self) -> None:
        """
        Tests that an invite from a remote practitioner gets accepted when in the
        federation list, is not an insurance server and that permissions are allowed.
        (Aka: practitioners are not allowed to brute force their way in)
        """
        for inviter in {
            f"@mxid:{DOMAIN_IN_LIST}",
            f"@matrixuri:{DOMAIN_IN_LIST}",
            f"@matrixuri2:{DOMAIN_IN_LIST}",
            f"@gematikuri:{DOMAIN_IN_LIST}",
            f"@gematikuri2:{DOMAIN_IN_LIST}",
            f"@mxidorgpract:{DOMAIN_IN_LIST}",
            f"@matrixuriorgpract:{DOMAIN_IN_LIST}",
            f"@matrixuri2orgpract:{DOMAIN_IN_LIST}",
            f"@gematikuriorgpract:{DOMAIN_IN_LIST}",
            f"@gematikuri2orgpract:{DOMAIN_IN_LIST}",
            f"@mxid404:{DOMAIN_IN_LIST}",
            f"@matrixuri404:{DOMAIN_IN_LIST}",
            f"@matrixuri2404:{DOMAIN_IN_LIST}",
            f"@gematikuri404:{DOMAIN_IN_LIST}",
            f"@gematikuri2404:{DOMAIN_IN_LIST}",
        }:
            assert (
                self.may_invite(inviter, self.user_allowing) == NOT_SPAM
            ), f"inviter {inviter} should be ALLOWED to invite {self.user_allowing}"
            assert (
                self.may_invite(inviter, self.user_blocking) == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} should be FORBIDDEN to invite {self.user_blocking}"

    def test_remote_invite_from_an_insured_domain_fails(self) -> None:
        """
        Test that invites from another insurance domain are rejected with or without
        contact permissions
        """
        for inviter in {
            f"@unknown:{INSURANCE_DOMAIN_IN_LIST}",
            f"@rando-32-b52:{INSURANCE_DOMAIN_IN_LIST}",
        }:
            assert (
                self.may_invite(inviter, self.user_allowing) == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} should be FORBIDDEN to invite {self.user_allowing}"
            assert (
                self.may_invite(inviter, self.user_blocking) == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} should be FORBIDDEN to invite {self.user_blocking}"
