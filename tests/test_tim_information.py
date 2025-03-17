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

import tests.unittest as synapse_test
from tests.base import ModuleApiTestCase


class MessengerInfoTestCase(ModuleApiTestCase):
    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.access_token = self.login("a", "password")

    def test_no_access_token_is_denied(self) -> None:
        channel = self.make_request(
            method="GET",
            path="/tim-information",
            shorthand=False,
        )

        assert channel.code == 401, "Request should fail with no access token"

    def test_default_operator_contact_info_resource(self) -> None:
        """Tests that the messenger operator contact info resource is accessible"""

        channel = self.make_request(
            method="GET",
            path="/tim-information",
            access_token=self.access_token,
            shorthand=False,
        )

        assert channel.code == 200, channel.result
        assert channel.json_body["title"] == "Invite Checker module by Famedly"
        assert channel.json_body["description"] == "Invite Checker module by Famedly"
        assert channel.json_body["contact"] == "info@famedly.com"
        assert channel.json_body["version"], "Version returned"

    @synapse_test.override_config(
        {
            "modules": [
                {
                    "module": "synapse_invite_checker.InviteChecker",
                    "config": {
                        "title": "abc",
                        "description": "def",
                        "contact": "ghi",
                        "federation_list_url": "https://localhost:8080",
                        "federation_list_client_cert": "tests/certs/client.pem",
                        "gematik_ca_baseurl": "https://download-ref.tsl.ti-dienste.de/",
                        "allowed_room_versions": ["9", "10"],
                    },
                }
            ]
        }
    )
    def test_custom_operator_contact_info_resource(self) -> None:
        """Tests that the registered info resource is accessible and has the configured values"""

        channel = self.make_request(
            method="GET",
            path="/tim-information",
            access_token=self.access_token,
            shorthand=False,
        )

        assert channel.code == 200, channel.result
        assert channel.json_body["title"] == "abc"
        assert channel.json_body["description"] == "def"
        assert channel.json_body["contact"] == "ghi"
        assert channel.json_body["version"], "Version returned"


class MessengerIsInsuranceResourceTest(ModuleApiTestCase):
    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.access_token = self.login("a", "password")

    def test_pro_isInsurance_returns_expected(self) -> None:
        """Tests that Pro mode returns expected response"""
        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/isInsurance?serverName=cirosec.de",
            shorthand=False,
        )

        assert channel.code == 401, "Request should fail with no access token"

        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/isInsurance",
            access_token=self.access_token,
            shorthand=False,
        )

        assert channel.code == 400, "Request should have a parameter missing"

        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/isInsurance?serverName=cirosec.de",
            access_token=self.access_token,
            shorthand=False,
        )

        assert channel.code == 200, channel.result
        assert channel.json_body[
            "isInsurance"
        ], "isInsurance is FALSE when it should be TRUE"

        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/isInsurance?serverName=timo.staging.famedly.de",
            access_token=self.access_token,
            shorthand=False,
        )

        assert channel.code == 200, channel.result
        assert not channel.json_body[
            "isInsurance"
        ], "isInsurance is TRUE when it should be FALSE"

    @synapse_test.override_config(
        {
            "modules": [
                {
                    "module": "synapse_invite_checker.InviteChecker",
                    "config": {
                        "tim-type": "epa",
                        "title": "abc",
                        "description": "def",
                        "contact": "ghi",
                        "federation_list_url": "https://localhost:8080",
                        "federation_list_client_cert": "tests/certs/client.pem",
                        "gematik_ca_baseurl": "https://download-ref.tsl.ti-dienste.de/",
                        "allowed_room_versions": ["9", "10"],
                    },
                }
            ]
        }
    )
    def test_epa_isInsurance_returns_expected(self) -> None:
        """Tests that ePA mode returns expected response"""

        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/isInsurance?serverName=cirosec.de",
            shorthand=False,
        )

        assert channel.code == 404, "Endpoint shouldn't exist"

        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/isInsurance?serverName=timo.staging.famedly.de",
            shorthand=False,
        )

        assert channel.code == 404, "Endpoint shouldn't exist"


class MessengerFindByIkResourceTestCase(ModuleApiTestCase):
    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.access_token = self.login("a", "password")

    def test_no_auth(self) -> None:
        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/findByIk?ikNumber=1",
            shorthand=False,
        )

        assert channel.code == 401, channel.result

    def test_not_found(self) -> None:
        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/findByIk?ikNumber=1",
            access_token=self.access_token,
            shorthand=False,
        )

        assert channel.code == 404, channel.result

    def test_no_parameter(self) -> None:
        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/findByIk",
            access_token=self.access_token,
            shorthand=False,
        )

        assert channel.code == 400, channel.result

    @synapse_test.override_config(
        {
            "modules": [
                {
                    "module": "synapse_invite_checker.InviteChecker",
                    "config": {
                        "tim-type": "epa",
                        "title": "abc",
                        "description": "def",
                        "contact": "ghi",
                        "federation_list_url": "https://localhost:8080",
                        "federation_list_client_cert": "tests/certs/client.pem",
                        "gematik_ca_baseurl": "https://download-ref.tsl.ti-dienste.de/",
                        "allowed_room_versions": ["9", "10"],
                    },
                }
            ]
        }
    )
    def test_unavailable_for_epa(self) -> None:
        # In EPA mode, it shouldn't matter what we do, should always be a 404
        channel = self.make_request(
            method="GET",
            path="/tim-information/v1/server/findByIk?ikNumber=1",
            access_token=self.access_token,
            shorthand=False,
        )

        assert channel.code == 404, channel.result
