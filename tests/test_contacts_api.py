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

from synapse_invite_checker.types import (
    GroupName,
    PermissionConfig,
    PermissionConfigType,
    PermissionDefaultSetting,
)
from tests.base import ModuleApiTestCase


class ContactsApiTest(ModuleApiTestCase):
    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.access_token = self.login("a", "password")
        self.user_b = self.register_user("b", "password")
        self.user_c = self.register_user("c", "password")

        # authenticated as user_a
        self.helper.auth_user_id = self.user_a

    async def test_contact_management_info_resource(self) -> None:
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

    def test_list_contacts(self) -> None:
        # Requires authentication
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
        )
        assert channel.code == 401, channel.result

        # Test for a reasonable return value
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "contacts" in channel.json_body, "Result contains contacts"
        assert len(channel.json_body["contacts"]) == 0, "List is empty initially"

    def test_add_contact(self) -> None:
        """See if we can add a new contact"""
        # Requires authentication
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:other.example.com",
                "inviteSettings": {"start": 0},
            },
        )
        assert channel.code == 401, channel.result

        # Test missing field validation
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 400, channel.result

        # Test for a reasonable return value
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:other.example.com",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "mxid" in channel.json_body, "Result contains contact"

        # check for 1 contact
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "contacts" in channel.json_body, "Result contains contacts"
        assert len(channel.json_body["contacts"]) == 1, "List is not empty anymore"

        # see if overwriting a contact is idempotent
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:other.example.com",
                "inviteSettings": {
                    "start": 500,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "mxid" in channel.json_body, "Result contains contact"

        # check for 1 contact
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "contacts" in channel.json_body, "Result contains contacts"
        assert len(channel.json_body["contacts"]) == 1, "List is not empty anymore"
        assert (
            channel.json_body["contacts"][0]["mxid"] == "@test:other.example.com"
        ), "Same MXID"

        # And post works as well
        channel = self.make_request(
            "POST",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:other.example.com",
                "inviteSettings": {
                    "start": 400,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "mxid" in channel.json_body, "Result contains contact"

        # check for 1 contact
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "contacts" in channel.json_body, "Result contains contacts"
        assert len(channel.json_body["contacts"]) == 1, "List is not empty anymore"
        assert (
            channel.json_body["contacts"][0]["mxid"] == "@test:other.example.com"
        ), "Same MXID"

        # And we can add a second user
        channel = self.make_request(
            "POST",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User2",
                "mxid": "@test2:other.example.com",
                "inviteSettings": {
                    "start": 300,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "mxid" in channel.json_body, "Result contains contact"

        # check for 2 contacts
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "contacts" in channel.json_body, "Result contains contacts"
        assert len(channel.json_body["contacts"]) == 2, "List is not empty anymore"
        self.assertIn(
            "@test:other.example.com",
            [item["mxid"] for item in channel.json_body["contacts"]],
        )
        self.assertIn(
            "@test2:other.example.com",
            [item["mxid"] for item in channel.json_body["contacts"]],
        )

    def test_get_contact(self) -> None:
        """See if we can retrieve a specific contact"""
        # Requires authentication
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:other.example.com",
        )
        assert channel.code == 401, channel.result

        # 404 on unknown contact
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:other.example.com",
            access_token=self.access_token,
        )
        assert channel.code == 404, channel.result

        # Test for a reasonable return value
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:other.example.com",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "mxid" in channel.json_body, "Result contains contact"

        # 200 after adding
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:other.example.com",
            access_token=self.access_token,
        )

        # Verify that adding another still returns a value
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test2:other.example.com",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "mxid" in channel.json_body, "Result contains contact"

        # 200 after adding
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:other.example.com",
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result

        # Unknown user still returns 404 after adding
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test3:other.example.com",
            access_token=self.access_token,
        )
        assert channel.code == 404, channel.result

    def test_del_contact(self) -> None:
        """See if we can delete a contact"""
        # Requires authentication
        channel = self.make_request(
            "DELETE",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:other.example.com",
        )
        assert channel.code == 401, channel.result

        # 404 on unknown contact
        channel = self.make_request(
            "DELETE",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:other.example.com",
            access_token=self.access_token,
        )
        assert channel.code == 404, channel.result

        # Test for a reasonable return value
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:other.example.com",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token,
        )
        assert channel.code == 200, channel.result
        assert "mxid" in channel.json_body, "Result contains contact"

        # 200 after adding
        channel = self.make_request(
            "DELETE",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:other.example.com",
            access_token=self.access_token,
        )
        assert channel.code == 204, channel.result

        # 404 on unknown contact
        channel = self.make_request(
            "DELETE",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:other.example.com",
            access_token=self.access_token,
        )
        assert channel.code == 404, channel.result


class ContactsApiPostMigrationTest(ModuleApiTestCase):
    """
    Test using the Contact API after migration has occurred will block if permissions
    are set to "allow all" or contains anything except "userExceptions"
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.access_token_a = self.login("a", "password")
        self.user_b = self.register_user("b", "password")
        self.access_token_b = self.login("b", "password")
        self.user_c = self.register_user("c", "password")
        self.access_token_c = self.login("c", "password")

        self.get_success_or_raise(self.inject_test_account_data())

    async def inject_test_account_data(self) -> None:
        user_a_permissions = PermissionConfig(
            defaultSetting=PermissionDefaultSetting.ALLOW_ALL
        )

        user_b_permissions = PermissionConfig(
            defaultSetting=PermissionDefaultSetting.BLOCK_ALL
        )
        user_b_permissions.serverExceptions.setdefault("example.com", {})

        user_c_permissions = PermissionConfig(
            defaultSetting=PermissionDefaultSetting.BLOCK_ALL
        )
        user_c_permissions.groupExceptions.append(
            {"groupName": GroupName.isInsuredPerson.value}
        )

        # The tests using this below should fail because of "allow all"
        await self.module_api.account_data_manager.put_global(
            self.user_a,
            PermissionConfigType.PRO_ACCOUNT_DATA_TYPE.value,
            user_a_permissions.dump(),
        )

        # The tests using this below should fail because there is a serverException
        await self.module_api.account_data_manager.put_global(
            self.user_b,
            PermissionConfigType.PRO_ACCOUNT_DATA_TYPE.value,
            user_b_permissions.dump(),
        )

        # The tests using this below should fail because there is a groupException,
        # ignoring the concept that having "block all" but excepting "isInsuredPerson"
        # may be wrong/odd
        await self.module_api.account_data_manager.put_global(
            self.user_c,
            PermissionConfigType.PRO_ACCOUNT_DATA_TYPE.value,
            user_c_permissions.dump(),
        )

    def test_list_contacts(self) -> None:
        # Requires authentication
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
        )
        assert channel.code == 401, channel.result

        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            access_token=self.access_token_a,
        )
        assert channel.code == 400, channel.result

        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            access_token=self.access_token_b,
        )
        assert channel.code == 400, channel.result

        assert channel.code == 400, channel.result

        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            access_token=self.access_token_c,
        )
        assert channel.code == 400, channel.result

    def test_add_contact(self) -> None:
        """See if adding a new contact is blocked"""
        # Requires authentication
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:example.com",
                "inviteSettings": {"start": 0},
            },
        )
        assert channel.code == 401, channel.result

        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:example.com",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token_a,
        )
        assert channel.code == 400, channel.result

        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:example.com",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token_b,
        )
        assert channel.code == 400, channel.result
        channel = self.make_request(
            "PUT",
            "/_synapse/client/com.famedly/tim/v1/contacts",
            {
                "displayName": "Test User",
                "mxid": "@test:example.com",
                "inviteSettings": {
                    "start": 0,
                },
            },
            access_token=self.access_token_c,
        )
        assert channel.code == 400, channel.result

    def test_get_contact(self) -> None:
        """See if retrieving a specific contact is blocked"""
        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:example.com",
        )
        assert channel.code == 401, channel.result

        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:example.com",
            access_token=self.access_token_a,
        )
        assert channel.code == 400, channel.result

        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:example.com",
            access_token=self.access_token_b,
        )
        assert channel.code == 400, channel.result

        channel = self.make_request(
            "GET",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:example.com",
            access_token=self.access_token_c,
        )
        assert channel.code == 400, channel.result

    def test_del_contact(self) -> None:
        """See if we can delete a contact"""
        # Requires authentication
        channel = self.make_request(
            "DELETE",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:example.com",
        )
        assert channel.code == 401, channel.result

        channel = self.make_request(
            "DELETE",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:example.com",
            access_token=self.access_token_a,
        )
        assert channel.code == 400, channel.result
        channel = self.make_request(
            "DELETE",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:example.com",
            access_token=self.access_token_b,
        )
        assert channel.code == 400, channel.result
        channel = self.make_request(
            "DELETE",
            "/_synapse/client/com.famedly/tim/v1/contacts/@test:example.com",
            access_token=self.access_token_b,
        )
        assert channel.code == 400, channel.result
