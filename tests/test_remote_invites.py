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

    async def may_invite(self, inviter: str, invitee: str, roomid: str):
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

    async def test_invite_from_remote_outside_of_fed_list(self) -> None:
        """Tests that an invite from a remote server not in the federation list gets denied"""
        self.add_a_contact_to_user_by_token(
            f"@example:{DOMAIN_IN_LIST}", self.access_token
        )
        self.add_a_contact_to_user_by_token(
            f"@example:not-{DOMAIN_IN_LIST}", self.access_token
        )

        # 'pract' sequence of tests. The practitioner tested is publicly listed and
        # therefore doesn't need to have contact details
        assert (
            await self.may_invite(
                f"@example:not-{DOMAIN_IN_LIST}", self.user_a, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example:not-{DOMAIN_IN_LIST}' incorrectly ALLOWED to invite {self.user_a} when not on fed list but DOES have contact details"
        assert (
            await self.may_invite(
                "@example:messenger.spilikin.dev", self.user_a, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example:messenger.spilikin.dev' incorrectly ALLOWED to invite {self.user_a} without contact details"
        assert (
            await self.may_invite(
                f"@example:{DOMAIN_IN_LIST}", self.user_a, "!madeup:example.com"
            )
            == NOT_SPAM
        ), f"inviter '@example:{DOMAIN_IN_LIST}' incorrectly FORBIDDEN to invite {self.user_a} despite contact details"
        assert (
            await self.may_invite(
                f"@example2:not-{DOMAIN_IN_LIST}", self.user_a, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example2:not-{DOMAIN_IN_LIST}' incorrectly ALLOWED to invite {self.user_a}"
        assert (
            await self.may_invite(
                f"@example2:{DOMAIN_IN_LIST}", self.user_a, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example2:{DOMAIN_IN_LIST}' incorrectly ALLOWED to invite {self.user_a} without contact details"

        # 'User' sequence of tests. Should not succeed without contact details of other
        # party if they are on the fed list
        assert (
            await self.may_invite(
                f"@example:not-{DOMAIN_IN_LIST}", self.user_d, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example:not-{DOMAIN_IN_LIST}' incorrectly ALLOWED to invite {self.user_d} when not on fed list but DOES have contact details"
        assert (
            await self.may_invite(
                "@example:messenger.spilikin.dev", self.user_d, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example:messenger.spilikin.dev' incorrectly ALLOWED to invite {self.user_d}"

        assert (
            await self.may_invite(
                f"@example2:not-{DOMAIN_IN_LIST}", self.user_d, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example2:not-{DOMAIN_IN_LIST}' incorrectly ALLOWED to invite {self.user_d}"
        assert (
            await self.may_invite(
                f"@example2:{DOMAIN_IN_LIST}", self.user_d, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example2:{DOMAIN_IN_LIST}' incorrectly ALLOWED to invite {self.user_d} without contact details"

        # This single test should pass, but doesn't because 'd' has blocked all contacts
        # unless added to their contact permissions. Do this below to test again
        assert (
            await self.may_invite(
                f"@example:{DOMAIN_IN_LIST}", self.user_d, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example:{DOMAIN_IN_LIST}' incorrectly ALLOWED to invite {self.user_d} without contact details"

        self.add_a_contact_to_user_by_token(
            f"@example:{DOMAIN_IN_LIST}", self.access_token_d
        )

        # Now it should work
        assert (
            await self.may_invite(
                f"@example:{DOMAIN_IN_LIST}", self.user_d, "!madeup:example.com"
            )
            == NOT_SPAM
        ), f"inviter '@example:{DOMAIN_IN_LIST}' incorrectly FORBIDDEN to invite {self.user_d} despite contact details"

    async def test_invite_from_publicly_listed_practitioners(self) -> None:
        """Tests that an invite from a remote server gets accepted when in the federation list and both practitioners are public"""
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
            assert (
                await self.may_invite(inviter, self.user_a, "!madeup:example.com")
                == NOT_SPAM
            ), f"inviter {inviter} incorrectly FORBIDDEN to invite {self.user_a}"
            assert (
                await self.may_invite(inviter, self.user_c, "!madeup:example.com")
                == NOT_SPAM
            ), f"inviter {inviter} incorrectly FORBIDDEN to invite {self.user_c}"
            assert (
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} incorrectly ALLOWED to invite {self.user_d} without contact details"

        for inviter in {
            f"@mxid404:{DOMAIN_IN_LIST}",
            f"@matrixuri404:{DOMAIN_IN_LIST}",
            f"@matrixuri2404:{DOMAIN_IN_LIST}",
            f"@gematikuri404:{DOMAIN_IN_LIST}",
            f"@gematikuri2404:{DOMAIN_IN_LIST}",
        }:
            assert (
                await self.may_invite(inviter, self.user_a, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} incorrectly ALLOWED to invite {self.user_a}"
            assert (
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} incorrectly ALLOWED to invite {self.user_d} without contact details"

    async def test_invite_from_remote_to_local_org_various(self) -> None:
        """Tests that an invite from a remote server gets accepted when in the
        federation list and the invite is to an org or orgPract"""
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
            # user 'b' is actually an 'org' not an 'orgPract'
            assert (
                await self.may_invite(inviter, self.user_b, "!madeup:example.com")
                == NOT_SPAM
            ), f"inviter {inviter} incorrectly FORBIDDEN to invite {self.user_b}"
            assert (
                await self.may_invite(inviter, self.user_c, "!madeup:example.com")
                == NOT_SPAM
            ), f"inviter {inviter} incorrectly FORBIDDEN to invite {self.user_c}"
            assert (
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} incorrectly ALLOWED to invite {self.user_d} without contact details"

        assert (
            await self.may_invite(
                "@unknown:not.in.fed", self.user_b, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@unknown:not.in.fed' incorrectly ALLOWED to invite {self.user_b}"
        assert (
            await self.may_invite(
                "@unknown:not.in.fed", self.user_c, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@unknown:not.in.fed' incorrectly ALLOWED to invite {self.user_c}"
        assert (
            await self.may_invite(
                "@unknown:not.in.fed", self.user_d, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@unknown:not.in.fed' incorrectly ALLOWED to invite {self.user_d}"

    async def test_remote_invite_from_an_insurance_domain(self) -> None:
        """
        Test that an insured user can invite a publicly listed practitioner or organization
        (but not a regular user on the practitioner's domain)
        """
        for inviter in {
            f"@unknown:{INSURANCE_DOMAIN_IN_LIST}",
            f"@rando-32-b52:{INSURANCE_DOMAIN_IN_LIST}",
        }:
            assert (
                await self.may_invite(inviter, self.user_b, "!madeup:example.com")
                == NOT_SPAM
            ), f"inviter {inviter} incorrectly FORBIDDEN to invite {self.user_b}"
            assert (
                await self.may_invite(inviter, self.user_c, "!madeup:example.com")
                == NOT_SPAM
            ), f"inviter {inviter} incorrectly FORBIDDEN to invite {self.user_b}"
            assert (
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} incorrectly ALLOWED to invite {self.user_d} without contact details"


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
        # Can't use any of:
        #  @a:test is a practitioner
        #  @b:test is an organization
        #  @c:test is an 'orgPract'
        # as they should not exist on an 'ePA' mode server backend

        # 'd', 'e' and 'f' is none of those types of actor and should be just regular 'User's
        self.user_d = self.register_user("d", "password")
        self.access_token_d = self.login("d", "password")

        # authenticated as user_d
        self.helper.auth_user_id = self.user_d

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        return conf

    async def may_invite(self, inviter: str, invitee: str, roomid: str):
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

    async def test_invite_from_remote_not_on_fed_list(self) -> None:
        """Tests that an invite from a remote server not in the federation list gets denied"""
        self.add_a_contact_to_user_by_token(
            f"@example:{DOMAIN_IN_LIST}", self.access_token_d
        )
        self.add_a_contact_to_user_by_token(
            f"@example:not-{DOMAIN_IN_LIST}", self.access_token_d
        )

        for inviter in {
            f"@example:not-{DOMAIN_IN_LIST}",
            "@example:messenger.spilikin.dev",
            f"@example2:not-{DOMAIN_IN_LIST}",
            f"@example2:{DOMAIN_IN_LIST}",
        }:
            assert (
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter '{inviter}' incorrectly ALLOWED to invite {self.user_d}"

    async def test_invite_from_remote_on_fed_list(self) -> None:
        """Test that a remote user invite from a domain on the fed list only succeeds with contact details"""
        assert (
            await self.may_invite(
                f"@example:{DOMAIN_IN_LIST}", self.user_d, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        ), f"inviter '@example:{DOMAIN_IN_LIST}' incorrectly ALLOWED to invite {self.user_d}"

        # Now add in the contact details and try again
        self.add_a_contact_to_user_by_token(
            f"@example:{DOMAIN_IN_LIST}", self.access_token_d
        )

        assert (
            await self.may_invite(
                f"@example:{DOMAIN_IN_LIST}", self.user_d, "!madeup:example.com"
            )
            == NOT_SPAM
        ), f"inviter '@example:{DOMAIN_IN_LIST}' incorrectly FORBIDDEN to invite {self.user_d}"

    async def test_invite_from_remote_practitioners(self) -> None:
        """
        Tests that an invite from a remote server gets accepted when in the federation
        list, and it is not 'isInsurance'. Borrow our localization setup for this
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
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} incorrectly ALLOWED to invite {self.user_d}(step one)"

            # Now add in the contact details...
            self.add_a_contact_to_user_by_token(inviter, self.access_token_d)

            # ...and try again
            assert (
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == NOT_SPAM
            ), f"inviter {inviter} incorrectly FORBIDDEN to invite {self.user_d}(step two)"

    async def test_remote_invite_from_an_insured_domain_fails(self) -> None:
        """
        Test that invites from another insurance domain are rejected with or without
        contact permissions
        """
        for inviter in {
            f"@unknown:{INSURANCE_DOMAIN_IN_LIST}",
            f"@rando-32-b52:{INSURANCE_DOMAIN_IN_LIST}",
        }:
            assert (
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} incorrectly ALLOWED to invite {self.user_d}"

            # Now add in the contact details...
            self.add_a_contact_to_user_by_token(inviter, self.access_token_d)

            # ...and try again
            assert (
                await self.may_invite(inviter, self.user_d, "!madeup:example.com")
                == errors.Codes.FORBIDDEN
            ), f"inviter {inviter} incorrectly ALLOWED to invite {self.user_d}"
