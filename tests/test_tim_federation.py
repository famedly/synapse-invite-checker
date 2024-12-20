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
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from synapse_invite_checker import InviteChecker
from synapse_invite_checker.types import FederationDomain
from tests.base import ModuleApiTestCase


class FederationDomainSchemaTest(ModuleApiTestCase):
    """
    Test that the required fields for the federation list are present and parsable.
    See:
    https://github.com/gematik/api-vzd/blob/main/src/schema/FederationList.json
    for the schema to use.

    As of the time of this writing, these are fields that are required:
        domain: str
        telematikID: str
        timAnbieter: str
        isInsurance: bool

    """

    def prepare(
        self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer
    ) -> None:
        super().prepare(reactor, clock, homeserver)

        self.invchecker = InviteChecker(
            self.hs.config.modules.loaded_modules[0][1], self.hs.get_module_api()
        )

    async def extract_entry_from_domainList(self, domain: str) -> FederationDomain:
        """
        Search for a specific domain in the federation list
        """
        _, raw_fed_list = await self.invchecker.fetch_federation_allow_list()
        assert len(raw_fed_list.domainList) > 0

        for domain_entry in raw_fed_list.domainList:
            if domain_entry.domain == domain:
                return domain_entry

        assert False, f"Not found in federation list {domain}"

    async def test_federation_list(self) -> None:
        """Ensure we can properly fetch the federation list"""

        domains, _ = await self.invchecker.fetch_federation_allow_list()
        assert "timo.staging.famedly.de" in domains

    async def test_common_fed_domain(self):
        # First test the most common FederationDomain entry
        # {
        #     "domain": "timo.staging.famedly.de",
        #     "telematikID": "1-SMC-B-Testkarte--883110000147435",
        #     "timAnbieter": "ORG-0217:BT-0158",
        #     "isInsurance": false
        # },
        test_entry = await self.extract_entry_from_domainList("timo.staging.famedly.de")
        assert test_entry.domain == "timo.staging.famedly.de"
        assert test_entry.telematikID == "1-SMC-B-Testkarte--883110000147435"
        assert test_entry.timAnbieter == "ORG-0217:BT-0158"
        assert test_entry.isInsurance is False

    async def test_insurance_fed_domain(self):
        # Then test an insurance FederationDomain entry. Want isInsurance to be True
        # {
        #     "domain": "ti-messengertest.dev.ccs.gematik.solutions",
        #     "telematikID": "5-2-KHAUS-Kornfeld01",
        #     "timAnbieter": "ORG-0001:BT-0001",
        #     "isInsurance": true
        # },

        test_entry = await self.extract_entry_from_domainList(
            "ti-messengertest.dev.ccs.gematik.solutions"
        )
        assert test_entry.domain == "ti-messengertest.dev.ccs.gematik.solutions"
        assert test_entry.telematikID == "5-2-KHAUS-Kornfeld01"
        assert test_entry.timAnbieter == "ORG-0001:BT-0001"
        assert test_entry.isInsurance is True

    async def test_illegal_fed_domain(self):
        # This test is against a FederationDomain entry with data that is counter to
        # what the schema says. In this case, 'timAnbieter' should be required but is
        # reflected as `null`
        # {
        #     "domain": "messenger.spilikin.dev",
        #     "telematikID": "1-SMC-B-Testkarte-883110000096089",
        #     "timAnbieter": null,
        #     "isInsurance": false
        # },

        test_entry = await self.extract_entry_from_domainList("messenger.spilikin.dev")
        assert test_entry.domain == "messenger.spilikin.dev"
        assert test_entry.telematikID == "1-SMC-B-Testkarte-883110000096089"
        assert test_entry.timAnbieter is None
        assert test_entry.isInsurance is False
