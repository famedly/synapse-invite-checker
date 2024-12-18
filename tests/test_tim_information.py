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
import tests.unittest as synapse_test
from tests.base import ModuleApiTestCase


class MessengerInfoTestCase(ModuleApiTestCase):
    async def test_default_operator_contact_info_resource(self) -> None:
        """Tests that the messenger operator contact info resource is accessible"""

        channel = self.make_request(
            method="GET",
            path="/_synapse/client/com.famedly/tim/tim-information",
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
                        "federation_localization_url": "https://localhost:8000/localization",
                        "federation_list_client_cert": "tests/certs/client.pem",
                        "gematik_ca_baseurl": "https://download-ref.tsl.ti-dienste.de/",
                    },
                }
            ]
        }
    )
    def test_custom_operator_contact_info_resource(self) -> None:
        """Tests that the registered info resource is accessible and has the configured values"""

        channel = self.make_request(
            method="GET",
            path="/_synapse/client/com.famedly/tim/tim-information",
        )

        assert channel.code == 200, channel.result
        assert channel.json_body["title"] == "abc"
        assert channel.json_body["description"] == "def"
        assert channel.json_body["contact"] == "ghi"
        assert channel.json_body["version"], "Version returned"
