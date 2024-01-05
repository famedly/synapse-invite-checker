# Copyright (C) 2020 Famedly
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
from unittest.mock import AsyncMock, Mock

from synapse.rest import admin
from synapse.rest.client import login, notifications, presence, profile, room
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor
from typing_extensions import override

import tests.unittest as synapsetest


class ModuleApiTestCase(synapsetest.HomeserverTestCase):
    servlets = [
        admin.register_servlets,
        login.register_servlets,
        room.register_servlets,
        presence.register_servlets,
        profile.register_servlets,
        notifications.register_servlets,
    ]

    # Ignore ARG001
    @override
    def prepare(
        self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer
    ) -> None:
        self.store = homeserver.get_datastores().main
        self.module_api = homeserver.get_module_api()
        self.event_creation_handler = homeserver.get_event_creation_handler()
        self.sync_handler = homeserver.get_sync_handler()
        self.auth_handler = homeserver.get_auth_handler()

    @override
    def make_homeserver(self, reactor: MemoryReactor, clock: Clock) -> HomeServer:
        # Mock out the calls over federation.
        self.fed_transport_client = Mock(spec=["send_transaction"])
        self.fed_transport_client.send_transaction = AsyncMock(return_value={})

        return self.setup_test_homeserver(
            federation_transport_client=self.fed_transport_client,
        )

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        if "modules" not in conf:
            conf["modules"] = [
                {
                    "module": "synapse_invite_checker.InviteChecker",
                    "config": {},
                }
            ]
        return conf

    def test_can_register_user(self) -> None:
        """Tests that an external module can register a user"""
        # Register a new user
        user_id, access_token = self.get_success(
            self.module_api.register(
                "bob", displayname="Bobberino", emails=["bob@bobinator.bob"]
            )
        )

        # Check that the new user exists with all provided attributes
        assert user_id == "@bob:test"
        assert access_token
        assert self.get_success(self.store.get_user_by_id(user_id))

    def test_registered_default_info_resource(self) -> None:
        """Tests that the registered info resource is accessible"""

        channel = self.make_request(
            method="GET",
            path="/_synapse/client/com.famedly/tim/v1",
        )

        assert channel.code == 200, channel.result
        assert channel.json_body["title"] == "Invite Checker module by Famedly"
        assert channel.json_body["description"] == "Invite Checker module by Famedly"
        assert channel.json_body["contact"] == "info@famedly.com"
        assert channel.json_body["version"], "Version returned"

    @synapsetest.override_config(
        {
            "modules": [
                {
                    "module": "synapse_invite_checker.InviteChecker",
                    "config": {
                        "api_prefix": "/_synapse/client/test",
                        "title": "abc",
                        "description": "def",
                        "contact": "ghi",
                    },
                }
            ]
        }
    )
    def test_registered_custom_info_resource(self) -> None:
        """Tests that the registered info resource is accessible and has the configured values"""

        channel = self.make_request(
            method="GET",
            path="/_synapse/client/test",
        )

        assert channel.code == 200, channel.result
        assert channel.json_body["title"] == "abc"
        assert channel.json_body["description"] == "def"
        assert channel.json_body["contact"] == "ghi"
        assert channel.json_body["version"], "Version returned"


