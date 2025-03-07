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
from synapse.util import Clock
from twisted.internet import defer
from twisted.internet.testing import MemoryReactor

from tests.base import ModuleApiTestCase
from tests.test_utils import (
    DOMAIN_IN_LIST,
    DOMAIN2_IN_LIST,
    DOMAIN3_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL,
)


class RemoteProModeInviteTest(ModuleApiTestCase):
    """Test remote invites in the default 'pro' mode behave as expected."""

    # SERVER_NAME_FROM_LIST = "tim.test.gematik.de"

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        #  "a" is a practitioner
        #  "b" is an organization
        #  "c" is an 'orgPract'
        self.pro_user_a = self.register_user("a", "password")
        self.access_token = self.login("a", "password")
        self.pro_user_b = self.register_user("b", "password")
        self.access_token_b = self.login("b", "password")
        self.pro_user_c = self.register_user("c", "password")
        self.access_token_c = self.login("c", "password")

        # "d" is none of those types of actor and should be just a 'User'. For
        # context, this could be a chatbot or an office manager
        self.pro_user_d = self.register_user("d", "password")
        self.access_token_d = self.login("d", "password")

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

    def test_invite_from_unlisted_user(self) -> None:
        """
        Tests that an invite from a remote user that is on the fed list but is otherwise
        unlisted behaves as expected
        """
        for remote_user_id in [
            f"@example:{DOMAIN_IN_LIST}",
            f"@example:{DOMAIN3_IN_LIST}",
            f"@mxid404:{DOMAIN_IN_LIST}",  # all 'unlisted' Users
            f"@matrixuri404:{DOMAIN_IN_LIST}",
            f"@matrixuri2404:{DOMAIN_IN_LIST}",
            f"@gematikuri404:{DOMAIN_IN_LIST}",
            f"@gematikuri2404:{DOMAIN_IN_LIST}",
        ]:
            # Test against unlisted and 'pract' first
            for local_user in [
                self.pro_user_a,
                self.pro_user_d,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == errors.Codes.FORBIDDEN
                ), f"'{remote_user_id}' should be FORBIDDEN to invite {local_user}(no permissions)"

            # 'org' and 'orgPract' are allowed to receive invites from unlisted persons
            for local_user in [
                self.pro_user_b,
                self.pro_user_c,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {local_user}(no permissions)"

            # Add permissions, don't bother with 'b' and 'c' as they are already allowed
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token)
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token_d)

            for local_user in [
                self.pro_user_a,
                self.pro_user_b,
                self.pro_user_c,
                self.pro_user_d,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {self.pro_user_a}"

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

            # Add permissions, but it shouldn't matter
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token)
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token_b)
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token_c)
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token_d)

            for local_user in [
                self.pro_user_a,
                self.pro_user_b,
                self.pro_user_c,
                self.pro_user_d,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == errors.Codes.FORBIDDEN
                ), f"'{remote_user_id}' should be FORBIDDEN to invite {local_user}(after permission)"

    def test_invite_from_publicly_listed_organizations(self) -> None:
        """Tests that an invite is accepted when the remote users are public orgs"""
        for remote_user_id in [
            f"@mxidorg:{DOMAIN_IN_LIST}",
            f"@matrixuriorg:{DOMAIN_IN_LIST}",
            f"@matrixuri2org:{DOMAIN_IN_LIST}",
            f"@gematikuriorg:{DOMAIN2_IN_LIST}",
            f"@gematikuri2org:{DOMAIN2_IN_LIST}",
        ]:
            # Test against unlisted and 'pract' first
            for local_user in [
                self.pro_user_a,
                self.pro_user_d,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == errors.Codes.FORBIDDEN
                ), f"'{remote_user_id}' should be FORBIDDEN to invite {local_user}(no permissions)"

            # 'org' and 'orgPract' are allowed to receive invites from unlisted persons
            for local_user in [
                self.pro_user_b,
                self.pro_user_c,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {local_user}(no permissions)"

            # Add permissions, don't bother with 'b' and 'c' as they are already allowed
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token)
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token_d)

            for local_user in [
                self.pro_user_a,
                self.pro_user_d,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {local_user}"

    def test_invite_from_publicly_listed_practitioners(self) -> None:
        """Tests that an invite from a remote server gets accepted when in the federation list and both practitioners are public"""
        for remote_user_id in {
            f"@mxid:{DOMAIN_IN_LIST}",  # 'pract' User
            f"@matrixuri:{DOMAIN_IN_LIST}",  # 'pract' User
            f"@matrixuri2:{DOMAIN_IN_LIST}",  # 'pract' User
            f"@gematikuri:{DOMAIN2_IN_LIST}",  # 'pract' User
            f"@gematikuri2:{DOMAIN2_IN_LIST}",  # 'pract' User
            f"@mxidorgpract:{DOMAIN_IN_LIST}",
            f"@matrixuriorgpract:{DOMAIN_IN_LIST}",
            f"@matrixuri2orgpract:{DOMAIN_IN_LIST}",
            f"@gematikuriorgpract:{DOMAIN2_IN_LIST}",
            f"@gematikuri2orgpract:{DOMAIN2_IN_LIST}",
        }:
            assert (
                self.may_invite(remote_user_id, self.pro_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.pro_user_d}(no permissions)"

            # 'pract', 'org' and 'orgPract' are allowed to receive invites from unlisted persons
            for local_user in [
                self.pro_user_a,
                self.pro_user_b,
                self.pro_user_c,
            ]:
                assert (
                    self.may_invite(remote_user_id, local_user, "!madeup:example.com")
                    == NOT_SPAM
                ), f"'{remote_user_id}' should be ALLOWED to invite {local_user}(no permissions)"

            # 'd' is not
            self.add_a_contact_to_user_by_token(remote_user_id, self.access_token_d)
            assert (
                self.may_invite(remote_user_id, self.pro_user_d, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {self.pro_user_d}"

    def test_remote_invite_from_an_insurance_domain(self) -> None:
        """
        Test that an insured user can invite a publicly listed practitioner or organization
        (but not a regular user on the practitioner's domain)
        """
        for remote_user_id in {
            f"@unknown:{INSURANCE_DOMAIN_IN_LIST}",
            f"@rando-32-b52:{INSURANCE_DOMAIN_IN_LIST}",
        }:
            assert (
                self.may_invite(remote_user_id, self.pro_user_b, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {self.pro_user_b}"
            assert (
                self.may_invite(remote_user_id, self.pro_user_c, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {self.pro_user_c}"
            assert (
                self.may_invite(remote_user_id, self.pro_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.pro_user_d} without contact details"


class RemoteEpaModeInviteTest(ModuleApiTestCase):
    """
    Test remote invites in 'epa' mode have expected behavior.

    Note that if the local server is in 'epa' mode, it means the server 'isInsurance'.
    Therefore, it is the responsibility of the remote server to deny *our* invites.
    Likewise, it is our responsibility to deny *theirs* if they are also 'isInsurance'.

    The second behavior is what we test here

        NOTE: This should not be allowed to work. Strictly speaking, a server that is
    in 'epa' mode should always appear on the federation list as an 'isInsurance'.
    For the moment, all we do is log a warning. This will be changed in the future
    which will require assuming the identity of an insurance domain to test with.

    """

    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        # 'd' is just regular insured 'User'
        self.epa_user_d = self.register_user("d", "password")
        self.access_token_d = self.login("d", "password")

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

        for remote_user_id in {
            f"@example:not-{DOMAIN_IN_LIST}",
            f"@example2:not-{DOMAIN_IN_LIST}",
        }:
            assert (
                self.may_invite(remote_user_id, self.epa_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.epa_user_d}"

    def test_invite_from_unlisted_user(self) -> None:
        """Test that a remote user invite from a domain on the fed list only succeeds with contact details"""
        for remote_user_id in [
            f"@example:{DOMAIN_IN_LIST}",
            f"@example:{DOMAIN3_IN_LIST}",
            f"@example2:{DOMAIN_IN_LIST}",
        ]:
            assert (
                self.may_invite(remote_user_id, self.epa_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.epa_user_d}"

            # Add in permissions
            self.add_permission_to_a_user(remote_user_id, self.epa_user_d)

            assert (
                self.may_invite(remote_user_id, self.epa_user_d, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {self.epa_user_d}"

    def test_invite_from_remote_practitioners(self) -> None:
        """
        Tests that an invite from a remote server gets accepted when in the federation
        list, and it is not 'isInsurance'. Borrow our localization setup for this
        """
        for remote_user_id in {
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
                self.may_invite(remote_user_id, self.epa_user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"'{remote_user_id}' should be FORBIDDEN to invite {self.epa_user_d}(step one)"

            # Add in permissions
            self.add_permission_to_a_user(remote_user_id, self.epa_user_d)

            # ...and try again
            assert (
                self.may_invite(remote_user_id, self.epa_user_d, "!madeup:example.com")
                == NOT_SPAM
            ), f"'{remote_user_id}' should be ALLOWED to invite {self.epa_user_d}(step two)"

    def test_remote_invite_from_an_insured_domain_fails(self) -> None:
        """
        Test that invites from another insurance domain are rejected with or without
        contact permissions
        """
        for remote_user_id in {
            f"@unknown:{INSURANCE_DOMAIN_IN_LIST}",
            f"@rando-32-b52:{INSURANCE_DOMAIN_IN_LIST}",
        }:
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
