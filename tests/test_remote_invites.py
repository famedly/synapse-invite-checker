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
from synapse.module_api import NOT_SPAM, errors
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet import defer
from twisted.internet.testing import MemoryReactor

from tests.base import ModuleApiTestCase
from tests.test_utils import DOMAIN_IN_LIST


class RemoteInviteTest(ModuleApiTestCase):
    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.access_token = self.login("a", "password")
        self.user_b = self.register_user("b", "password")
        self.user_c = self.register_user("c", "password")

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

        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": f"@example:{DOMAIN_IN_LIST}",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result

        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": f"@example:not-{DOMAIN_IN_LIST}",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result

        assert (
            await self.may_invite(
                f"@example:not-{DOMAIN_IN_LIST}", self.user_a, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        )
        # currently not testing modifying the fed list atm
        assert (
            await self.may_invite(
                "@example:messenger.spilikin.dev", self.user_a, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        )
        assert (
            await self.may_invite(
                f"@example:{DOMAIN_IN_LIST}", self.user_a, "!madeup:example.com"
            )
            == NOT_SPAM
        )
        assert (
            await self.may_invite(
                f"@example2:not-{DOMAIN_IN_LIST}", self.user_a, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        )
        assert (
            await self.may_invite(
                f"@example2:{DOMAIN_IN_LIST}", self.user_a, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        )

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
            )
            assert (
                await self.may_invite(inviter, self.user_c, "!madeup:example.com")
                == NOT_SPAM
            )

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
            )

    async def test_invite_from_remote_to_local_org(self) -> None:
        """Tests that an invite from a remote server gets accepted when in the federation list and the invite is to an orgPract"""
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
                await self.may_invite(inviter, self.user_b, "!madeup:example.com")
                == NOT_SPAM
            )
            assert (
                await self.may_invite(inviter, self.user_c, "!madeup:example.com")
                == NOT_SPAM
            )

        assert (
            await self.may_invite(
                "@unknown:not.in.fed", self.user_b, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        )
        assert (
            await self.may_invite(
                "@unknown:not.in.fed", self.user_c, "!madeup:example.com"
            )
            == errors.Codes.FORBIDDEN
        )
